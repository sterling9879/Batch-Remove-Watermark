from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import gradio as gr
import pandas as pd
import requests


# ---------------------------------------------------------------------------
# WaveSpeed API helpers
# ---------------------------------------------------------------------------


class WaveSpeedError(RuntimeError):
    """Representa um erro retornado pela API do WaveSpeed."""


@dataclass
class WaveSpeedResult:
    request_id: str
    status: str
    result_url: Optional[str] = None
    raw_response: Optional[Dict] = None


class WaveSpeedWatermarkRemover:
    """Cliente simples para enviar vídeos à API de remoção de marca d'água."""

    DEFAULT_BASE_URL = "https://api.wavespeed.ai/api/v3"

    def __init__(
        self,
        api_key: str,
        *,
        api_base: str | None = None,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key:
            raise ValueError("Uma chave de API é obrigatória para usar o cliente WaveSpeed.")
        self.api_key = api_key
        self.api_base = (api_base or self.DEFAULT_BASE_URL).rstrip("/")
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.session = session or requests.Session()

    # ------------------------ API pública ---------------------------------
    def process_video(self, file_path: str, *, filename: Optional[str] = None) -> WaveSpeedResult:
        upload_url = self._upload_video(file_path, filename=filename)
        request_id = self._create_prediction(upload_url)
        return self._poll_for_result(request_id)

    # ------------------------ Auxiliares HTTP ------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _upload_video(self, file_path: str, *, filename: Optional[str] = None) -> str:
        filename = filename or os.path.basename(file_path)
        with open(file_path, "rb") as file_handle:
            files = {"file": (filename, file_handle, "application/octet-stream")}
            response = self.session.post(
                f"{self.api_base}/uploads",
                headers=self._headers(),
                files=files,
                timeout=60,
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise WaveSpeedError(f"Falha no upload: {exc}") from exc
        data = response.json()
        upload_url = data.get("url") or data.get("file_url")
        if not upload_url:
            raise WaveSpeedError("Resposta inesperada no upload — URL não encontrada.")
        return upload_url

    def _create_prediction(self, video_url: str) -> str:
        headers = {**self._headers(), "Content-Type": "application/json"}
        response = self.session.post(
            f"{self.api_base}/wavespeed-ai/video-watermark-remover",
            headers=headers,
            json={"video": video_url},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise WaveSpeedError(f"Falha ao criar predição: {exc}") from exc
        data = response.json()
        request_id = (
            data.get("request_id")
            or data.get("requestId")
            or data.get("id")
            or data.get("prediction_id")
        )
        if not request_id:
            raise WaveSpeedError("A resposta da predição não contém request_id.")
        return request_id

    def _poll_for_result(self, request_id: str) -> WaveSpeedResult:
        start_time = time.time()
        while True:
            response = self.session.get(
                f"{self.api_base}/predictions/{request_id}/result",
                headers=self._headers(),
                timeout=30,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise WaveSpeedError(f"Falha ao consultar resultado: {exc}") from exc
            data = response.json()
            status = data.get("status") or data.get("state") or data.get("result", {}).get("status")
            if status in {"succeeded", "failed", "error"}:
                return WaveSpeedResult(
                    request_id=request_id,
                    status=status,
                    result_url=self._extract_result_url(data),
                    raw_response=data,
                )
            if time.time() - start_time > self.poll_timeout:
                raise WaveSpeedError(
                    f"Tempo limite atingido (>{self.poll_timeout}s) aguardando {request_id}."
                )
            time.sleep(self.poll_interval)

    @staticmethod
    def _extract_result_url(data: Dict) -> Optional[str]:
        result_payload = data.get("result")
        if isinstance(result_payload, str):
            return result_payload
        if isinstance(result_payload, dict):
            for key in ("video", "output", "url", "video_url"):
                value = result_payload.get(key)
                if isinstance(value, str):
                    return value
            for value in result_payload.values():
                if isinstance(value, str) and value.startswith("http"):
                    return value
        return None


def ensure_iterable(files: Iterable | None) -> List:
    if files is None:
        return []
    if isinstance(files, Sequence) and not isinstance(files, (bytes, str)):
        return list(files)
    return [files]


RESULT_COLUMNS = ["Arquivo", "Request ID", "Status", "Mensagem", "Link do Resultado"]


def download_file(url: str, destination_dir: Path, filename: Optional[str] = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    if filename is None:
        filename = url.split("?")[0].rstrip("/").split("/")[-1] or "resultado.mp4"
    file_path = destination_dir / filename
    with open(file_path, "wb") as output:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                output.write(chunk)
    return file_path


def process_videos(
    video_files: List,
    api_key: str,
    poll_interval: float,
    poll_timeout: float,
    progress=gr.Progress(track_tqdm=True),
) -> Tuple[pd.DataFrame, List[str]]:
    if not api_key:
        raise gr.Error("Forneça a chave de API do WaveSpeed (WAVESPEED_API_KEY).")

    normalized_files = [file for file in ensure_iterable(video_files) if file]
    if not normalized_files:
        raise gr.Error("Envie ao menos um vídeo para processar.")

    client = WaveSpeedWatermarkRemover(
        api_key,
        poll_interval=float(poll_interval),
        poll_timeout=float(poll_timeout),
    )

    output_dir = Path(tempfile.mkdtemp(prefix="wavespeed_results_"))
    records = []
    downloaded_paths: List[str] = []

    progress(0, desc="Iniciando processamento em lote...")
    total = len(normalized_files)

    for index, file_info in enumerate(normalized_files, start=1):
        file_path = _resolve_uploaded_path(file_info)
        progress(index / total, desc=f"Processando {file_path.name} ({index}/{total})")

        try:
            result = client.process_video(str(file_path), filename=file_path.name)
            status_message = (
                "Sucesso" if result.status == "succeeded" else "Verifique a resposta retornada"
            )
            record = {
                "Arquivo": file_path.name,
                "Request ID": result.request_id,
                "Status": result.status,
                "Mensagem": status_message,
                "Link do Resultado": result.result_url or "",
            }
            if result.status == "succeeded" and result.result_url:
                try:
                    downloaded_paths.append(
                        str(download_file(result.result_url, output_dir, filename=file_path.name))
                    )
                except Exception as download_error:
                    record["Mensagem"] = f"Falha ao baixar resultado: {download_error}"
            records.append(record)
        except WaveSpeedError as api_error:
            records.append(
                {
                    "Arquivo": file_path.name,
                    "Request ID": "-",
                    "Status": "error",
                    "Mensagem": str(api_error),
                    "Link do Resultado": "",
                }
            )
        except Exception as unexpected_error:
            records.append(
                {
                    "Arquivo": file_path.name,
                    "Request ID": "-",
                    "Status": "error",
                    "Mensagem": str(unexpected_error),
                    "Link do Resultado": "",
                }
            )

    df = pd.DataFrame.from_records(records, columns=RESULT_COLUMNS)
    return df, downloaded_paths


def _resolve_uploaded_path(file_info) -> Path:
    """Compatibilidade com diferentes formatos de retorno do componente File."""
    if isinstance(file_info, dict) and "name" in file_info:
        return Path(file_info["name"])
    if hasattr(file_info, "name"):
        return Path(file_info.name)
    if isinstance(file_info, (str, Path)):
        return Path(file_info)
    raise gr.Error("Não foi possível identificar o caminho do arquivo enviado.")


# ---------------------------------------------------------------------------
# Interface Gradio
# ---------------------------------------------------------------------------


def build_interface(default_api_key: Optional[str] = None) -> gr.Blocks:
    demo = gr.Blocks(title="WaveSpeed Watermark Remover", theme=gr.themes.Soft())
    with demo:
        gr.Markdown(
            """
            # Processamento em lote - WaveSpeed Watermark Remover
            Faça upload de múltiplos vídeos, informe sua chave de API e o aplicativo enviará
            automaticamente cada arquivo para a API do WaveSpeed.
            """
        )

        with gr.Row():
            api_key_input = gr.Textbox(
                label="WAVESPEED_API_KEY",
                placeholder="Cole aqui sua chave de API",
                type="password",
                value=default_api_key or "",
            )
            poll_interval_input = gr.Number(
                label="Intervalo de polling (segundos)", value=5, minimum=1, maximum=30
            )
            poll_timeout_input = gr.Number(
                label="Tempo máximo de espera (segundos)", value=600, minimum=60, maximum=3600
            )

        video_input = gr.File(
            label="Vídeos",
            file_count="multiple",
            file_types=[".mp4", ".mov", ".mkv"],
        )

        with gr.Row():
            submit_button = gr.Button("Iniciar processamento", variant="primary")
            clear_button = gr.Button("Limpar")

        results_output = gr.Dataframe(
            headers=RESULT_COLUMNS,
            datatype=["str", "str", "str", "str", "str"],
            interactive=False,
            label="Resultados do processamento",
        )
        downloads_output = gr.File(
            label="Vídeos sem marca d'água",
            file_count="multiple",
            interactive=False,
        )

        submit_button.click(
            process_videos,
            inputs=[video_input, api_key_input, poll_interval_input, poll_timeout_input],
            outputs=[results_output, downloads_output],
        )
        clear_button.click(
            lambda: (pd.DataFrame(columns=RESULT_COLUMNS), []),
            inputs=None,
            outputs=[results_output, downloads_output],
        )
    return demo


def main() -> None:
    api_key_from_env = os.getenv("WAVESPEED_API_KEY")
    if not api_key_from_env:
        print("Defina a variável de ambiente WAVESPEED_API_KEY ou informe pela interface.")
    interface = build_interface(default_api_key=api_key_from_env)
    interface.queue(concurrency_count=2).launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()