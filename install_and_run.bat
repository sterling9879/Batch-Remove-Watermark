@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change directory to the script location to ensure relative paths work
pushd %~dp0

echo ========================================
echo  WaveSpeed Watermark Remover - Setup
echo ========================================
echo.

REM Check if virtual environment exists
if not exist venv (
    echo [1/4] Criando ambiente virtual Python...
    python -m venv venv
    if errorlevel 1 (
        echo ERRO: Falha ao criar ambiente virtual. Certifique-se de que Python 3.9+ esta instalado e no PATH.
        pause
        exit /b 1
    )
    echo [OK] Ambiente virtual criado com sucesso!
    echo.
) else (
    echo [1/4] Ambiente virtual ja existe, pulando criacao...
    echo.
)

REM Activate virtual environment
echo [2/4] Ativando ambiente virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERRO: Falha ao ativar o ambiente virtual.
    pause
    exit /b 1
)
echo [OK] Ambiente virtual ativado!
echo.

REM Upgrade pip
echo [3/4] Atualizando pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo AVISO: Falha ao atualizar pip, continuando mesmo assim...
) else (
    echo [OK] pip atualizado!
)
echo.

REM Install requirements
echo [4/4] Instalando dependencias do projeto...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar pacotes necessarios.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas com sucesso!
echo.

echo ========================================
echo  Iniciando aplicacao...
echo ========================================
echo.
echo A aplicacao sera aberta em: http://127.0.0.1:7860
echo Pressione Ctrl+C para encerrar a aplicacao
echo.

REM Run the application
python app.py

REM If app.py exits, pause to show any error messages
if errorlevel 1 (
    echo.
    echo ========================================
    echo  A aplicacao encerrou com erros
    echo ========================================
    pause
)

popd
endlocal
