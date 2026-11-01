#!/usr/bin/env bash
# Nexus Business Agent — macOS / Linux başlatıcı
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "Python 3.10+ gerekli."; exit 1; }

if [ ! -x backend/.venv/bin/python ]; then
  echo "[1/3] Sanal ortam oluşturuluyor..."
  "$PY" -m venv backend/.venv
fi

echo "[2/3] Bağımlılıklar kontrol ediliyor..."
backend/.venv/bin/python -m pip install -q --disable-pip-version-check -r backend/requirements.txt

if [ ! -f backend/static/index.html ]; then
  command -v npm >/dev/null || { echo "Arayüz derlenmemiş ve Node.js bulunamadı."; exit 1; }
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

echo "[3/3] Nexus başlatılıyor: http://127.0.0.1:8765"
cd backend && exec .venv/bin/python -m app.main
