"""Basit zamanlayıcı: otomasyonları belirlenen aralıklarla çalıştırır."""
from __future__ import annotations

import threading
import time

from . import db
from .agents import engine

_started = False


def run_automation(auto: dict) -> str:
    conv_id = engine.create_conversation(auto["agent_id"], f"⏱ {auto['name']}", source="automation")
    db.execute("UPDATE automations SET last_run=?, last_conversation_id=? WHERE id=?",
               (db.now(), conv_id, auto["id"]))
    engine.send_message(conv_id, auto["prompt"], background=True)
    return conv_id


def _loop() -> None:
    while True:
        try:
            for a in db.query("SELECT * FROM automations WHERE enabled=1"):
                interval = max(int(a["interval_minutes"] or 60), 5) * 60
                if not a["last_run"] or time.time() - a["last_run"] >= interval:
                    run_automation(a)
        except Exception as e:  # noqa: BLE001
            print("[scheduler]", e)
        time.sleep(30)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="nexus-scheduler").start()
