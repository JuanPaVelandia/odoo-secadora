@echo off
setlocal
cd /d %~dp0

if not exist ".env" (
  echo [ERROR] No existe archivo .env en esta carpeta.
  echo Copia .env.example a .env y configura tus datos.
  pause
  exit /b 1
)

python bascula_bridge.py
if errorlevel 1 (
  echo [ERROR] El bridge termino con error.
  pause
)
