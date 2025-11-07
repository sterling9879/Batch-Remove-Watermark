from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import gradio as gr
import pandas as pd
import requests

from wavespeed_client import WaveSpeedError, WaveSpeedWatermarkRemover


RESULT_COLUMNS = ["Arquivo", "Request ID", "Status", "Mensagem", "Link do Resultado"]


def download_file(url: str, destination_dir: Path, filename: Optional[str] = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    if filename is None:
        filename = url.split("?")[0].rstrip("/").split("/")[-1] or "result.mp4"
    file_path = destination_dir / filename
    with open(file_path, "wb") as output:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                output.write(chunk)
    return file_path


def process_videos(
    video_files: List[gr.File],
    api_key: str,
    poll_interval: float,
    poll_timeout: float,
    progress=gr.Progress(track_tqdm=True),
) -> Tuple[pd.DataFrame, List[str]]:
    if not api_key:
        raise gr.Error("Forneça a chave de API do WaveSpeed (WAVESPEED_API_KEY).")
    if not video_files:
        raise gr.Error("Selecione ao menos um vídeo para processar.")

    client = WaveSpeedWatermarkRemover(
        api_key,
        poll_interval=poll_interval,
        poll_timeout=poll_timeout,
    )

    records = []
    downloaded_paths: List[str] = []
    output_dir = Path(tempfile.mkdtemp(prefix="wavespeed_results_"))

    progress(0, desc="Iniciando processamento em lote...")
    valid_files = [video for video in video_files if video is not None]
    if not valid_files:
        raise gr.Error("Nenhum arquivo válido foi enviado.")

    total = len(valid_files)

    for index, video in enumerate(valid_files, start=1):
        file_name = getattr(video, "name", None)
        if not file_name and isinstance(video, dict):  # compatibilidade com versões antigas
            file_name = video.get("name")
        if not file_name:
            raise gr.Error("Não foi possível determinar o caminho do arquivo enviado.")
        file_path = Path(file_name)
        progress(index / total, desc=f"Processando {file_path.name} ({index}/{total})")
        try:
            result = client.process_video(str(file_path), filename=file_path.name)
            if result.status == "succeeded" and result.result_url:
                try:
                    downloaded_paths.append(str(download_file(result.result_url, output_dir)))
                except Exception as download_error:  # pragma: no cover - network error handling
                    records.append(
                        {
                            "Arquivo": file_path.name,
                            "Request ID": result.request_id,
                            "Status": "succeeded",
                            "Mensagem": f"Falha ao baixar resultado: {download_error}",
                            "Link do Resultado": result.result_url or "",
                        }
                    )
                    continue
            records.append(
                {
                    "Arquivo": file_path.name,
                    "Request ID": result.request_id,
                    "Status": result.status,
                    "Mensagem": "Sucesso" if result.status == "succeeded" else "Verifique a resposta",
                    "Link do Resultado": result.result_url or "",
                }
            )
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
        except Exception as unexpected_error:  # pragma: no cover - protective catch
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


def build_interface() -> gr.Blocks:
    with gr.Blocks(title="WaveSpeed Watermark Remover", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # Processamento em lote - WaveSpeed Watermark Remover
            Faça upload de múltiplos vídeos, informe sua chave de API e o aplicativo irá enviar cada vídeo
            para a API do WaveSpeed, aguardando o resultado automaticamente.
            """
        )

        with gr.Row():
            api_key_input = gr.Textbox(
                label="WAVESPEED_API_KEY",
                placeholder="Cole aqui sua chave de API",
                type="password",
            )
            poll_interval_input = gr.Number(
                label="Intervalo de Polling (segundos)", value=5, minimum=1, maximum=30
            )
            poll_timeout_input = gr.Number(
                label="Tempo máximo de espera (segundos)", value=600, minimum=60, maximum=3600
            )

        video_input = gr.File(label="Vídeos", file_count="multiple", file_types=[".mp4", ".mov", ".mkv"])

        with gr.Row():
            submit_button = gr.Button("Iniciar processamento", variant="primary")
            clear_button = gr.Button("Limpar")

        results_output = gr.Dataframe(
            headers=RESULT_COLUMNS,
            datatype=["str", "str", "str", "str", "str"],
            interactive=False,
            label="Resultados do processamento",
        )
        downloads_output = gr.Files(label="Downloads dos vídeos sem marca d'água")

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


if __name__ == "__main__":
    api_key_from_env = os.getenv("WAVESPEED_API_KEY")
    iface = build_interface()
    if api_key_from_env:
        iface.queue(concurrency_count=2).launch(server_name="0.0.0.0", server_port=7860)
    else:
        print("Defina a variável de ambiente WAVESPEED_API_KEY ou informe pela interface.")
        iface.queue(concurrency_count=2).launch(server_name="0.0.0.0", server_port=7860)
