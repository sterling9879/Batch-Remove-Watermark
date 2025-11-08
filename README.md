# WaveSpeed Watermark Remover - Processamento em Lote

Aplicação Gradio para remover marcas d'água de múltiplos vídeos simultaneamente usando a API do WaveSpeed.

## 🚀 Características

- ⚡ **Processamento Paralelo**: Processa múltiplos vídeos ao mesmo tempo
- 🎯 **Suporte a Tiers**: Bronze (3), Silver (20) ou Gold (100) vídeos simultâneos
- 📊 **Progress Tracking**: Acompanhe o progresso em tempo real
- 💾 **Download Automático**: Baixa automaticamente os vídeos processados
- 🔄 **Upload Automático**: Faz upload para serviços temporários (0x0.st, tmpfiles.org)

## 📋 Requisitos

- Python 3.9 ou superior
- Chave de API do WaveSpeed (obtenha em https://wavespeed.ai)

## 🔧 Instalação e Execução

### Primeira Vez (Instalação + Execução)

1. Execute o arquivo `install_and_run.bat`
2. O script irá:
   - Criar o ambiente virtual Python
   - Instalar todas as dependências
   - Iniciar automaticamente a aplicação
3. Acesse: http://127.0.0.1:7860

### Execuções Seguintes

- Execute o arquivo `run.bat` para iniciar rapidamente a aplicação

## 📝 Como Usar

1. **Cole sua API Key**: Insira sua chave da API do WaveSpeed
2. **Selecione o Tier**: Escolha Bronze, Silver ou Gold conforme sua conta
3. **Faça Upload**: Selecione múltiplos vídeos (.mp4, .mov, .mkv)
4. **Clique em "Iniciar processamento"**
5. **Aguarde**: Os vídeos serão processados em paralelo
6. **Baixe**: Os resultados estarão disponíveis para download

## 🎯 Tiers de Conta

| Tier | Tarefas Simultâneas | Vídeos/Minuto | Uso Recomendado |
|------|---------------------|---------------|-----------------|
| 🥉 Bronze | 3 | 5 | Testes e uso pessoal |
| 🥈 Silver | 20 | 30 | Projetos profissionais |
| 🥇 Gold | 100 | 60 | Produção em larga escala |

## ⚙️ Configurações Avançadas

- **Intervalo de Polling**: Tempo entre verificações de status (padrão: 5s)
- **Tempo Máximo de Espera**: Timeout para processamento (padrão: 600s)

## 🔑 Variável de Ambiente (Opcional)

Para não precisar digitar a API key toda vez:

```bash
# Windows (CMD)
set WAVESPEED_API_KEY=sua_chave_aqui

# Windows (PowerShell)
$env:WAVESPEED_API_KEY="sua_chave_aqui"
```

Ou crie um arquivo `.env`:
```
WAVESPEED_API_KEY=sua_chave_aqui
```

## 📦 Estrutura do Projeto

```
.
├── app.py                    # Aplicação principal
├── install_and_run.bat      # Instalação + execução
├── run.bat                  # Execução rápida
├── requirements.txt         # Dependências Python
└── README.md               # Este arquivo
```

## 🐛 Solução de Problemas

### "Falha no upload do vídeo"
- O vídeo está sendo enviado para um serviço de hospedagem temporária
- Tente novamente ou use um vídeo menor
- Verifique sua conexão com a internet

### "Too Many Requests"
- Você atingiu o limite do seu tier
- Aguarde alguns segundos ou reduza o número de vídeos simultâneos
- Considere fazer upgrade do seu plano

### "Erro 404"
- Verifique se sua API key está correta
- Confirme que sua conta WaveSpeed está ativa

## 📄 Licença

Este projeto é fornecido como está, sem garantias.

## 🤝 Suporte

Para problemas com a API WaveSpeed:
- Email: support@wavespeed.ai
- Docs: https://wavespeed.ai/docs

## 🔗 Links Úteis

- [WaveSpeed API](https://wavespeed.ai)
- [Documentação da API](https://wavespeed.ai/docs)
- [Watermark Remover Model](https://wavespeed.ai/models/wavespeed-ai/video-watermark-remover)
