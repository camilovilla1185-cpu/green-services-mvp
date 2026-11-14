@echo off
REM Abre el tablero de Operaciones de Green Services.
REM Funciona con Anaconda/Miniconda (entorno "green") o con Python normal (.venv).
REM La primera vez instala las librerias; despues abre en segundos.
title Tablero de Operaciones - Green Services
cd /d "%~dp0"

set "CONDA_DIR="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3") do (
    if not defined CONDA_DIR if exist "%%~D\Scripts\activate.bat" set "CONDA_DIR=%%~D"
)

if defined CONDA_DIR (
    echo Usando Anaconda en %CONDA_DIR%
    call "%CONDA_DIR%\Scripts\activate.bat" base
    if not exist "%CONDA_DIR%\envs\green\python.exe" (
        echo Creando el entorno "green" con Python 3.11 ^(solo la primera vez^)...
        call conda create -n green python=3.11 -y
    )
    call conda activate green
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo No se encontro Python ni Anaconda.
        echo Instale Python 3.11 desde https://www.python.org/downloads/
        echo y en la primera pantalla marque "Add python.exe to PATH".
        pause
        exit /b 1
    )
    if not exist .venv (
        echo Creando entorno virtual...
        python -m venv .venv
    )
    call .venv\Scripts\activate.bat
)

if not exist .instalado (
    echo Instalando librerias ^(la primera vez tarda unos minutos^)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Error instalando librerias. Revise su conexion a internet.
        pause
        exit /b 1
    )
    echo ok> .instalado
)

if not exist data\processed\metricas.json (
    echo Generando datos de prueba y procesando...
    python -m src.pipeline --demo
)

echo.
echo Abriendo el tablero en el navegador: http://localhost:8501
echo Para cerrarlo, cierre esta ventana.
python -m streamlit run app.py
pause
