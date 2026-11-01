"""Gerçek Claude API ile canlı uçtan uca testler.

Ayarlar sayfasına kaydedilen API anahtarını (veya ANTHROPIC_API_KEY) kullanır.
Dış hesap gerektirmez: yerel dosyalar, web okuma ve yerel bir webhook alıcısıyla
onay / ret akışlarını gerçek modelle dener. Çalıştırma (backend klasöründen):

    .venv\\Scripts\\python -m tests.live_test
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from app import connectors as conn
from app import db
from app.agents import engine, presets
from app.config import WORKSPACE_DIR

received: list[dict] = []


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        received.append(json.loads(body or b"{}"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *_):
        pass


def wait(cid: str, timeout: int = 240) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        c = engine.load_conv(cid)
        if c["status"] != "running":
            return c
        time.sleep(1)
    raise TimeoutError("Ajan zamanında bitmedi")


def last_text(cid: str) -> str:
    ev = [e for e in db.list_events(cid) if e["kind"] == "assistant"]
    return ev[-1]["payload"]["text"] if ev else ""


def tools_used(cid: str) -> list[str]:
    return [e["payload"]["tool"] for e in db.list_events(cid) if e["kind"] == "tool_call"]


results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    print(f"{'✅' if ok else '❌'} {name}" + (f"\n   {info}" if info else ""), flush=True)


def main() -> int:
    db.init_db()
    presets.seed()
    if not (db.get_setting("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")):
        print("API anahtarı yok. Önce Ayarlar sayfasından ekleyin.")
        return 2

    srv = HTTPServer(("127.0.0.1", 8799), Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    conn.save_connection("webhook", {"url": "http://127.0.0.1:8799/hook",
                                     "purpose": "Sipariş durumunu depo sistemine bildirir. Alanlar: siparis_no, durum."})

    aid = "a_livetest"
    db.execute("DELETE FROM agents WHERE id=?", (aid,))
    db.execute("INSERT INTO agents(id,name,description,icon,color,system_prompt,model,effort,connectors,auto_approve,"
               "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (aid, "Canlı Test Ajanı", "Otomatik test", "bot", "#334155",
                "Sen bir test asistanısın. Kısa yanıt ver.", "", "low",
                json.dumps(["files", "web", "webhook"]), 0, db.now(), db.now()))

    # 1) Basit sohbet
    cid = engine.create_conversation(aid)
    engine.send_message(cid, "Tek cümleyle kendini tanıt.", background=False)
    c = wait(cid)
    check("1. Basit yanıt", c["status"] == "idle" and bool(last_text(cid)), last_text(cid)[:150] or c["error"] or "")

    # 2) Dosya aracı (onaysız)
    target = WORKSPACE_DIR / "test" / "stok.csv"
    target.unlink(missing_ok=True)
    engine.send_message(cid, "3 ürünlük örnek stok tablosu (Ürün, Adet, Fiyat) oluştur ve test/stok.csv olarak "
                             "CSV kaydet. Sonra dosyayı okuyup doğrula.", background=False)
    c = wait(cid)
    check("2. CSV dosyası oluşturma + okuma", target.exists() and c["status"] == "idle",
          f"araçlar: {tools_used(cid)} | dosya: {target.read_text('utf-8-sig')[:120] if target.exists() else 'YOK'}")

    # 3) Web okuma
    cid3 = engine.create_conversation(aid)
    engine.send_message(cid3, "https://example.com sayfasını fetch_url ile oku ve sayfa başlığını söyle.", background=False)
    c = wait(cid3)
    check("3. Web sayfası okuma", "web__fetch_url" in tools_used(cid3) and "example" in last_text(cid3).lower(),
          last_text(cid3)[:150])

    # 4) Onay → kabul
    cid4 = engine.create_conversation(aid)
    engine.send_message(cid4, "Webhook ile 1234 numaralı siparişin durumunu 'hazir' olarak bildir.", background=False)
    c = wait(cid4)
    pend = [p for p in c["pending"] if p["needs_approval"]]
    check("4a. Yazma işlemi onaya düştü", c["status"] == "awaiting_approval" and bool(pend),
          json.dumps([p["input"] for p in pend], ensure_ascii=False))
    if pend:
        engine.decide(cid4, {p["id"]: {"approve": True} for p in pend}, background=False)
        c = wait(cid4)
        check("4b. Onay sonrası gönderildi", c["status"] == "idle" and len(received) == 1,
              f"alınan: {received} | yanıt: {last_text(cid4)[:120]}")

    # 5) Onay → ret
    before = len(received)
    cid5 = engine.create_conversation(aid)
    engine.send_message(cid5, "Webhook ile 999 numaralı siparişi 'iptal' olarak bildir.", background=False)
    c = wait(cid5)
    pend = [p for p in c["pending"] if p["needs_approval"]]
    if pend:
        engine.decide(cid5, {p["id"]: {"approve": False} for p in pend}, background=False)
        c = wait(cid5)
    check("5. Ret edilen işlem çalışmadı", bool(pend) and len(received) == before and c["status"] == "idle",
          last_text(cid5)[:150])

    # 6) Web araması (sunucu tarafı araç)
    cid6 = engine.create_conversation(aid)
    engine.send_message(cid6, "Web'de ara: Türkiye'nin başkenti neresi? Tek kelime yanıt ver.", background=False)
    c = wait(cid6)
    check("6. Claude web araması", c["status"] == "idle" and "ankara" in last_text(cid6).lower(),
          f"araçlar: {tools_used(cid6)} | {last_text(cid6)[:80]} {c['error'] or ''}")

    usage = db.query_one("SELECT SUM(usage_in) i, SUM(usage_out) o FROM conversations WHERE agent_id=?", (aid,))
    print(f"\nToken kullanımı: girdi {usage['i']}, çıktı {usage['o']}")

    # temizlik
    for r in db.query("SELECT id FROM conversations WHERE agent_id=?", (aid,)):
        db.execute("DELETE FROM events WHERE conversation_id=?", (r["id"],))
    db.execute("DELETE FROM conversations WHERE agent_id=?", (aid,))
    db.execute("DELETE FROM activity WHERE agent_id=?", (aid,))
    db.execute("DELETE FROM agents WHERE id=?", (aid,))
    conn.delete_connection("webhook")
    srv.shutdown()

    passed = sum(ok for _, ok, _ in results)
    print(f"\nSONUÇ: {passed}/{len(results)} test geçti")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
