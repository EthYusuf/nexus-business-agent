"""Uygulama genel ayarları ve dosya yolları."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Nexus Business Agent"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

# Tüm kullanıcı verisi yerelde, bu klasörde tutulur.
DATA_DIR = Path(os.environ.get("NEXUS_DATA_DIR", ROOT_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "nexus.db"
KEY_PATH = DATA_DIR / "secret.key"
WORKSPACE_DIR = DATA_DIR / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

STATIC_DIR = BASE_DIR / "static"

HOST = os.environ.get("NEXUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("NEXUS_PORT", "8765"))

DEFAULT_MODEL = "claude-opus-5-5"
AVAILABLE_MODELS = [
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5 (önerilen)"},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5 (hızlı)"},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5 (ekonomik)"},
    {"id": "claude-fable-5-1", "label": "Claude Fable 5.1 (en güçlü)"},
]
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]

# Tek bir ajan çalıştırmasında izin verilen azami model turu (sonsuz döngü koruması)
MAX_AGENT_TURNS = 25
