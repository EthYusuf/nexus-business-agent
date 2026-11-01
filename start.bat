@echo off
chcp 65001 >nul
title Nexus Business Agent
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [HATA] Python bulunamadi. https://www.python.org/downloads/ adresinden Python 3.10+ kurun.
  pause
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/3] Sanal ortam olusturuluyor...
  python -m venv backend\.venv || goto :fail
)

echo [2/3] Bagimliliklar kontrol ediliyor...
backend\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r backend\requirements.txt || goto :fail

if not exist "backend\static\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [HATA] Arayuz derlenmemis ve Node.js bulunamadi. https://nodejs.org adresinden Node.js kurun.
    pause
    exit /b 1
  )
  echo Arayuz derleniyor...
  pushd frontend
  call npm install --no-audit --no-fund || goto :fail
  call npm run build || goto :fail
  popd
)

echo [3/3] Nexus baslatiliyor: http://127.0.0.1:8765
echo Kapatmak icin bu pencereyi kapatin.
cd backend
.venv\Scripts\python -m app.main
goto :eof

:fail
echo [HATA] Kurulum basarisiz oldu.
pause
exit /b 1
