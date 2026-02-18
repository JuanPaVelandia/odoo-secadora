@echo off
setlocal
cd /d %~dp0

if not exist ".env" (
  echo [ERROR] No existe archivo .env en esta carpeta.
  echo Copia .env.example a .env y configura tus datos.
  pause
  exit /b 1
)

echo ============================================================
echo  BRIDGE BASCULA (MODO PRODUCCION - BASCULA REAL)
echo ============================================================
echo.
echo Este script inicia bascula_bridge.py (NO simulador).
echo Tomara configuracion desde .env
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python no esta instalado o no esta en PATH.
  pause
  exit /b 1
)

if not "%~1"=="" (
  set "BASCULA_PUERTO_SERIAL=%~1"
  echo [INFO] Puerto COM forzado por argumento: %BASCULA_PUERTO_SERIAL%
  echo [INFO] Ejemplo de uso: iniciar_bridge_windows.bat COM3
  echo.
)

python -c "import serial,requests,dotenv" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Instalando dependencias...
  pip install -r requirements.txt
)

echo [INFO] Iniciando bridge real de bascula por puerto serial...
python bascula_bridge.py
if errorlevel 1 (
  echo [ERROR] El bridge termino con error.
  pause
)
