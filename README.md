# Batch-Remove-Watermark

Aplicação em Gradio para enviar vários vídeos para a API de remoção de marca d'água do WaveSpeed.

## Pré-requisitos

1. Crie um ambiente virtual Python (opcional, mas recomendado).
2. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```
3. Defina a variável de ambiente `WAVESPEED_API_KEY` com a sua chave de API.
4. Garanta que a sua conta tenha acesso ao endpoint `/api/v3/uploads`, utilizado pelo aplicativo para hospedar temporariamente os vídeos antes de iniciar o processamento.

## Executando o aplicativo

```bash
python app.py
```

A interface ficará disponível em `http://127.0.0.1:7860`.

Na interface:

1. Informe sua chave de API (caso não tenha definido a variável de ambiente).
2. Faça upload de vários arquivos de vídeo.
3. Clique em **Iniciar processamento** para iniciar o envio em lote.

O aplicativo realiza o upload dos arquivos, cria as requisições na API, acompanha o status de cada uma e baixa automaticamente os vídeos processados quando disponíveis.
