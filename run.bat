@echo off
setlocal

REM Change to script directory
pushd %~dp0

echo ========================================
echo  WaveSpeed Watermark Remover
echo ========================================
echo.

REM Check if venv exists
if not exist venv (
    echo ERRO: Ambiente virtual nao encontrado!
    echo Execute o arquivo "install_and_run.bat" primeiro para instalar as dependencias.
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERRO: Falha ao ativar ambiente virtual.
    pause
    exit /b 1
)

echo Iniciando aplicacao...
echo.
echo Acesse: http://127.0.0.1:7860
echo Pressione Ctrl+C para encerrar
echo.

REM Run the application
python app.py

popd
endlocal
