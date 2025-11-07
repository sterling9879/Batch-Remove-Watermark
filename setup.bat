@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change directory to the script location to ensure relative paths work
pushd %~dp0

if not exist venv (
    echo Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Ensure Python 3.9+ is installed and added to PATH.
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate the virtual environment.
    exit /b 1
)

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    exit /b 1
)

echo Installing project requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install required packages.
    exit /b 1
)

echo.
echo Dependencias instaladas com sucesso!
echo Agora voce pode executar "python app.py" (com o ambiente virtual ativo) para iniciar a aplicacao.

echo.
pause

popd
endlocal
