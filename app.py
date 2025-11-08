from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import gradio as gr
import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Configurações de Rate Limits por Tier
# ---------------------------------------------------------------------------

TIER_LIMITS = {
    "Bronze": {
        "max_concurrent": 3,
        "videos_per_minute": 5,
        "description": "Bronze - Básico (3 tarefas simultâneas, 5 vídeos/min)"
    },
    "Silver": {
        "max_concurrent": 20,
        "videos_per_minute": 30,
        "description": "Silver - Pro (20 tarefas simultâneas, 30 vídeos/min)"
    },
    "Gold": {
        "max_concurrent": 100,
        "videos_per_minute": 60,
        "description": "Gold - Enterprise (100 tarefas simultâneas, 60 vídeos/min)"
    }
}


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
        """Upload video to a temporary hosting service and return public URL."""
        filename = filename or os.path.basename(file_path)
        
        # Lista de serviços de hospedagem temporária para tentar
        upload_services = [
            {
                "name": "0x0.st",
                "url": "https://0x0.st",
                "field": "file",
                "response_key": None,  # URL vem direto como texto
            },
            {
                "name": "tmpfiles.org",
                "url": "https://tmpfiles.org/api/v1/upload",
                "field": "file",
                "response_key": "data.url",
            },
        ]
        
        last_error = None
        for service in upload_services:
            try:
                with open(file_path, "rb") as file_handle:
                    files = {service["field"]: (filename, file_handle, "video/mp4")}
                    response = requests.post(
                        service["url"],
                        files=files,
                        timeout=180,
                    )
                response.raise_for_status()
                
                # 0x0.st retorna a URL diretamente como texto
                if service["response_key"] is None:
                    upload_url = response.text.strip()
                    if upload_url.startswith("http"):
                        return upload_url
                else:
                    # Outros serviços retornam JSON
                    data = response.json()
                    # Navega pelo caminho do response_key (ex: "data.url")
                    keys = service["response_key"].split(".")
                    value = data
                    for key in keys:
                        value = value.get(key)
                    if value and isinstance(value, str) and value.startswith("http"):
                        # tmpfiles.org retorna formato: https://tmpfiles.org/123456
                        # Precisamos converter para: https://tmpfiles.org/dl/123456
                        if "tmpfiles.org" in value and "/dl/" not in value:
                            value = value.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                        return value
                        
            except Exception as e:
                last_error = e
                continue
        
        # Se todos os serviços falharem
        raise WaveSpeedError(
            f"Falha no upload do vídeo para todos os serviços testados. "
            f"Último erro: {last_error}. "
            f"A API WaveSpeed requer uma URL pública. "
            f"Você pode hospedar seu vídeo manualmente em um serviço como Dropbox, "
            f"Google Drive (link público), ou S3 e fornecer a URL diretamente."
        ) from last_error

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
        # WaveSpeed retorna: data.id como Task ID
        request_id = data.get("data", {}).get("id") or data.get("id")
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
            # WaveSpeed retorna: data.status (created, processing, completed, failed)
            status = data.get("data", {}).get("status") or data.get("status")
            if status in {"completed", "failed", "error"}:
                return WaveSpeedResult(
                    request_id=request_id,
                    status="succeeded" if status == "completed" else status,
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
        # WaveSpeed retorna: data.outputs como array de URLs
        data_obj = data.get("data", {})
        outputs = data_obj.get("outputs")
        if isinstance(outputs, list) and len(outputs) > 0:
            return outputs[0]
        # Fallback para outros formatos
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
    account_tier: str,
    poll_interval: float,
    poll_timeout: float,
    progress=gr.Progress(track_tqdm=True),
) -> Tuple[pd.DataFrame, List[str]]:
    if not api_key:
        raise gr.Error("Forneça a chave de API do WaveSpeed (WAVESPEED_API_KEY).")

    normalized_files = [file for file in ensure_iterable(video_files) if file]
    if not normalized_files:
        raise gr.Error("Envie ao menos um vídeo para processar.")

    # Configuração do tier
    tier_config = TIER_LIMITS.get(account_tier, TIER_LIMITS["Bronze"])
    max_workers = tier_config["max_concurrent"]

    client = WaveSpeedWatermarkRemover(
        api_key,
        poll_interval=float(poll_interval),
        poll_timeout=float(poll_timeout),
    )

    output_dir = Path(tempfile.mkdtemp(prefix="wavespeed_results_"))
    records = []
    downloaded_paths: List[str] = []

    progress(0, desc=f"Iniciando processamento paralelo ({account_tier}: {max_workers} workers)...")
    total = len(normalized_files)
    completed = 0

    def process_single_video(file_info):
        """Processa um único vídeo e retorna o resultado."""
        file_path = _resolve_uploaded_path(file_info)
        print(f"[INÍCIO] Processando: {file_path.name}")
        
        try:
            print(f"[UPLOAD] Fazendo upload de: {file_path.name}")
            result = client.process_video(str(file_path), filename=file_path.name)
            print(f"[SUCESSO] Vídeo processado: {file_path.name} - Status: {result.status}")
            
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
            
            downloaded_path = None
            if result.status == "succeeded" and result.result_url:
                try:
                    print(f"[DOWNLOAD] Baixando resultado de: {file_path.name}")
                    downloaded_path = str(
                        download_file(result.result_url, output_dir, filename=file_path.name)
                    )
                    print(f"[OK] Download concluído: {file_path.name}")
                except Exception as download_error:
                    print(f"[ERRO DOWNLOAD] {file_path.name}: {download_error}")
                    record["Mensagem"] = f"Falha ao baixar resultado: {download_error}"
            
            return {"success": True, "record": record, "downloaded_path": downloaded_path}
            
        except WaveSpeedError as api_error:
            print(f"[ERRO API] {file_path.name}: {api_error}")
            return {
                "success": False,
                "record": {
                    "Arquivo": file_path.name,
                    "Request ID": "-",
                    "Status": "error",
                    "Mensagem": str(api_error),
                    "Link do Resultado": "",
                },
                "downloaded_path": None,
            }
        except Exception as unexpected_error:
            print(f"[ERRO INESPERADO] {file_path.name}: {unexpected_error}")
            return {
                "success": False,
                "record": {
                    "Arquivo": file_path.name,
                    "Request ID": "-",
                    "Status": "error",
                    "Mensagem": str(unexpected_error),
                    "Link do Resultado": "",
                },
                "downloaded_path": None,
            }

    # Processamento paralelo com ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submete todas as tarefas
        future_to_file = {
            executor.submit(process_single_video, file_info): file_info
            for file_info in normalized_files
        }
        
        # Atualiza progress logo após submissão
        progress(
            0.1,
            desc=f"✓ {total} vídeos enviados para processamento ({account_tier}: {max_workers} workers)"
        )
        
        # Processa resultados conforme completam
        for future in as_completed(future_to_file):
            completed += 1
            file_info = future_to_file[future]
            file_path = _resolve_uploaded_path(file_info)
            
            # Atualiza progresso com mais informações
            progress_pct = completed / total
            progress(
                progress_pct,
                desc=f"✓ {completed}/{total} concluídos ({int(progress_pct * 100)}%) - {account_tier}"
            )
            
            try:
                result = future.result()
                records.append(result["record"])
                if result["downloaded_path"]:
                    downloaded_paths.append(result["downloaded_path"])
            except Exception as exc:
                # Fallback para erros não capturados
                records.append({
                    "Arquivo": file_path.name,
                    "Request ID": "-",
                    "Status": "error",
                    "Mensagem": f"Erro inesperado: {exc}",
                    "Link do Resultado": "",
                })

    progress(1.0, desc=f"✅ Processamento concluído! {total} vídeos processados")
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
    with gr.Blocks(title="WaveSpeed Watermark Remover", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # Processamento em lote - WaveSpeed Watermark Remover
            Faça upload de múltiplos vídeos, informe sua chave de API e o aplicativo enviará
            automaticamente cada arquivo para a API do WaveSpeed **em paralelo**.
            
            ⚡ **Processamento Paralelo Habilitado!** Múltiplos vídeos são processados simultaneamente.
            """
        )

        with gr.Row():
            api_key_input = gr.Textbox(
                label="WAVESPEED_API_KEY",
                placeholder="Cole aqui sua chave de API",
                type="password",
                value=default_api_key or "",
            )
            account_tier_input = gr.Dropdown(
                label="Tier da Conta WaveSpeed",
                choices=["Bronze", "Silver", "Gold"],
                value="Bronze",
                info="Bronze: 3 simultâneos | Silver: 20 simultâneos | Gold: 100 simultâneos"
            )
        
        with gr.Row():
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
        
        gr.Markdown(
            """
            ### 📊 Informações sobre Tiers de Conta
            
            | Tier | Tarefas Simultâneas | Vídeos/Minuto | Ideal Para |
            |------|---------------------|---------------|------------|
            | 🥉 **Bronze** | 3 | 5 | Testes e uso pessoal |
            | 🥈 **Silver** | 20 | 30 | Projetos profissionais |
            | 🥇 **Gold** | 100 | 60 | Produção em larga escala |
            
            💡 **Dica**: Selecione o tier correto da sua conta para otimizar o processamento paralelo!
            """
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
            inputs=[video_input, api_key_input, account_tier_input, poll_interval_input, poll_timeout_input],
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
    interface.queue().launch(server_name="127.0.0.1", server_port=7860, share=False)


if __name__ == "__main__":
    main()
