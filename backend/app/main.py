"""Nexus Business Agent — FastAPI uygulaması (REST API + panel arayüzü)."""
from __future__ import annotations

import json
import threading
import webbrowser
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import connectors as conn
from . import db, scheduler
from .agents import engine, presets
from .config import (APP_NAME, APP_VERSION, AVAILABLE_MODELS, DEFAULT_MODEL, EFFORT_LEVELS, HOST, PORT,
                     STATIC_DIR, WORKSPACE_DIR)
from .security import mask


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    presets.seed()
    engine.recover_stuck()
    scheduler.start()
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)


@app.exception_handler(conn.ConnectorError)
async def _ce(_, e: conn.ConnectorError):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(RuntimeError)
async def _re(_, e: RuntimeError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(KeyError)
async def _ke(_, e: KeyError):
    return JSONResponse({"detail": f"Bulunamadı: {e}"}, status_code=404)


# ---- Genel ---------------------------------------------------------------

@app.get("/api/meta")
def meta():
    return {"name": APP_NAME, "version": APP_VERSION, "models": AVAILABLE_MODELS, "efforts": EFFORT_LEVELS,
            "workspace": str(WORKSPACE_DIR)}


@app.get("/api/dashboard")
def dashboard():
    cons = conn.list_connectors()
    since = db.now() - 7 * 86400
    act = db.query_one("SELECT COUNT(*) n, SUM(ok) ok FROM activity WHERE created_at>?", (since,)) or {}
    usage = db.query_one("SELECT SUM(usage_in) i, SUM(usage_out) o FROM conversations") or {}
    daily = db.query(
        "SELECT CAST((created_at - ?) / 86400 AS INTEGER) d, COUNT(*) n FROM activity WHERE created_at>? GROUP BY d",
        (since, since))
    per_day = [0] * 7
    for r in daily:
        if 0 <= r["d"] < 7:
            per_day[r["d"]] = r["n"]
    top = db.query("SELECT connector_id, COUNT(*) n FROM activity WHERE created_at>? GROUP BY connector_id "
                   "ORDER BY n DESC LIMIT 6", (since,))
    return {
        "connectors_total": len([c for c in cons if not c["builtin"]]),
        "connectors_active": len([c for c in cons if c["connected"] and c["enabled"] and not c["builtin"]]),
        "agents": (db.query_one("SELECT COUNT(*) n FROM agents") or {}).get("n", 0),
        "conversations": (db.query_one("SELECT COUNT(*) n FROM conversations") or {}).get("n", 0),
        "pending_approvals": (db.query_one(
            "SELECT COUNT(*) n FROM conversations WHERE status='awaiting_approval'") or {}).get("n", 0),
        "actions_7d": act.get("n") or 0,
        "success_rate": round(100 * (act.get("ok") or 0) / act["n"]) if act.get("n") else 100,
        "tokens_in": usage.get("i") or 0, "tokens_out": usage.get("o") or 0,
        "activity_per_day": per_day, "top_connectors": top,
        "recent": recent_activity(limit=8),
        "api_key_set": bool(db.get_setting("anthropic_api_key")),
    }


# ---- Ayarlar -------------------------------------------------------------

class SettingsIn(BaseModel):
    anthropic_api_key: str | None = None
    company_name: str | None = None
    company_profile: str | None = None
    default_model: str | None = None
    default_effort: str | None = None
    fallback_enabled: bool | None = None


@app.get("/api/settings")
def get_settings():
    return {
        "anthropic_api_key": mask(db.get_setting("anthropic_api_key", "")),
        "company_name": db.get_setting("company_name", ""),
        "company_profile": db.get_setting("company_profile", ""),
        "default_model": db.get_setting("default_model", DEFAULT_MODEL),
        "default_effort": db.get_setting("default_effort", "medium"),
        "fallback_enabled": db.get_setting("fallback_enabled", True),
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "anthropic_api_key" and "••••" in v:
            continue
        db.set_setting(k, v.strip() if isinstance(v, str) else v)
    return get_settings()


@app.post("/api/settings/test")
def test_api_key():
    client = engine.get_client()
    r = client.messages.create(model=db.get_setting("default_model", DEFAULT_MODEL), max_tokens=64,
                               messages=[{"role": "user", "content": "Sadece 'Tamam' yaz."}],
                               output_config={"effort": "low"})
    return {"ok": True, "model": r.model}


# ---- Entegrasyonlar ------------------------------------------------------

class ConnectionIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


@app.get("/api/connectors")
def list_connectors():
    return conn.list_connectors()


@app.put("/api/connectors/{cid}")
def save_connector(cid: str, body: ConnectionIn):
    if cid not in conn.REGISTRY:
        raise HTTPException(404, "Bilinmeyen entegrasyon")
    conn.save_connection(cid, body.values, body.enabled)
    return {"ok": True}


@app.post("/api/connectors/{cid}/test")
def test_connector(cid: str):
    try:
        msg = conn.get_instance(cid).test()
        conn.set_status(cid, "ok", msg)
        return {"ok": True, "message": msg}
    except Exception as e:  # noqa: BLE001
        conn.set_status(cid, "error", str(e))
        return {"ok": False, "message": str(e)}


@app.delete("/api/connectors/{cid}")
def delete_connector(cid: str):
    conn.delete_connection(cid)
    return {"ok": True}


# ---- Ajanlar -------------------------------------------------------------

class AgentIn(BaseModel):
    name: str
    description: str = ""
    icon: str = "bot"
    color: str = "#6366f1"
    system_prompt: str = ""
    model: str = ""
    effort: str = ""
    connectors: list[str] = Field(default_factory=list)
    auto_approve: bool = False


def _agent_out(a: dict[str, Any]) -> dict[str, Any]:
    a["connectors"] = json.loads(a["connectors"] or "[]")
    a["auto_approve"] = bool(a["auto_approve"])
    return a


@app.get("/api/agents")
def list_agents():
    return [_agent_out(a) for a in db.query("SELECT * FROM agents ORDER BY created_at")]


@app.post("/api/agents")
def create_agent(body: AgentIn):
    aid = db.new_id("a_")
    db.execute(
        "INSERT INTO agents(id, name, description, icon, color, system_prompt, model, effort, connectors, auto_approve, "
        "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, body.name, body.description, body.icon, body.color, body.system_prompt, body.model, body.effort,
         json.dumps(body.connectors), int(body.auto_approve), db.now(), db.now()))
    return _agent_out(db.query_one("SELECT * FROM agents WHERE id=?", (aid,)))


@app.put("/api/agents/{aid}")
def update_agent(aid: str, body: AgentIn):
    db.execute(
        "UPDATE agents SET name=?, description=?, icon=?, color=?, system_prompt=?, model=?, effort=?, connectors=?, "
        "auto_approve=?, updated_at=? WHERE id=?",
        (body.name, body.description, body.icon, body.color, body.system_prompt, body.model, body.effort,
         json.dumps(body.connectors), int(body.auto_approve), db.now(), aid))
    return _agent_out(db.query_one("SELECT * FROM agents WHERE id=?", (aid,)))


@app.delete("/api/agents/{aid}")
def delete_agent(aid: str):
    db.execute("DELETE FROM agents WHERE id=?", (aid,))
    return {"ok": True}


# ---- Konuşmalar ----------------------------------------------------------

class ConvIn(BaseModel):
    agent_id: str
    message: str | None = None


class MessageIn(BaseModel):
    text: str


class DecisionIn(BaseModel):
    decisions: dict[str, dict[str, Any]]


def _conv_out(c: dict[str, Any], with_events: bool = False) -> dict[str, Any]:
    out = {k: c[k] for k in ("id", "agent_id", "title", "status", "error", "source", "usage_in", "usage_out",
                             "created_at", "updated_at")}
    out["pending"] = json.loads(c["pending"]) if isinstance(c["pending"], str) else c["pending"]
    if with_events:
        out["events"] = db.list_events(c["id"])
    return out


@app.get("/api/conversations")
def list_conversations(agent_id: str | None = None, limit: int = 100):
    if agent_id:
        rows = db.query("SELECT * FROM conversations WHERE agent_id=? ORDER BY updated_at DESC LIMIT ?",
                        (agent_id, limit))
    else:
        rows = db.query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))
    return [_conv_out(r) for r in rows]


@app.post("/api/conversations")
def create_conversation(body: ConvIn):
    cid = engine.create_conversation(body.agent_id)
    if body.message:
        engine.send_message(cid, body.message)
    return _conv_out(db.query_one("SELECT * FROM conversations WHERE id=?", (cid,)))


@app.get("/api/conversations/{cid}")
def get_conversation(cid: str, after: int = 0):
    c = db.query_one("SELECT * FROM conversations WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Konuşma bulunamadı")
    out = _conv_out(c)
    out["events"] = db.list_events(cid, after)
    return out


@app.post("/api/conversations/{cid}/messages")
def post_message(cid: str, body: MessageIn):
    engine.send_message(cid, body.text)
    return {"ok": True}


@app.post("/api/conversations/{cid}/decide")
def post_decision(cid: str, body: DecisionIn):
    engine.decide(cid, body.decisions)
    return {"ok": True}


@app.post("/api/conversations/{cid}/stop")
def post_stop(cid: str):
    engine.stop(cid)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    db.execute("DELETE FROM events WHERE conversation_id=?", (cid,))
    db.execute("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


@app.get("/api/approvals")
def approvals():
    rows = db.query("SELECT * FROM conversations WHERE status='awaiting_approval' ORDER BY updated_at DESC")
    return [_conv_out(r) for r in rows]


# ---- Etkinlik günlüğü ----------------------------------------------------

@app.get("/api/activity")
def recent_activity(limit: int = 200, connector_id: str | None = None):
    if connector_id:
        rows = db.query("SELECT * FROM activity WHERE connector_id=? ORDER BY id DESC LIMIT ?", (connector_id, limit))
    else:
        rows = db.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["ok"] = bool(r["ok"])
    return rows


# ---- Otomasyonlar --------------------------------------------------------

class AutomationIn(BaseModel):
    name: str
    agent_id: str
    prompt: str
    interval_minutes: int = 60
    enabled: bool = True


@app.get("/api/automations")
def list_automations():
    return db.query("SELECT * FROM automations ORDER BY created_at")


@app.post("/api/automations")
def create_automation(body: AutomationIn):
    aid = db.new_id("t_")
    # last_run=şimdi: ilk çalışma bir aralık sonra olur (hemen çalıştırmak için 'Şimdi çalıştır').
    db.execute("INSERT INTO automations(id, name, agent_id, prompt, interval_minutes, enabled, last_run, created_at) "
               "VALUES(?,?,?,?,?,?,?,?)",
               (aid, body.name, body.agent_id, body.prompt, max(5, body.interval_minutes), int(body.enabled),
                db.now(), db.now()))
    return db.query_one("SELECT * FROM automations WHERE id=?", (aid,))


@app.put("/api/automations/{tid}")
def update_automation(tid: str, body: AutomationIn):
    db.execute("UPDATE automations SET name=?, agent_id=?, prompt=?, interval_minutes=?, enabled=? WHERE id=?",
               (body.name, body.agent_id, body.prompt, max(5, body.interval_minutes), int(body.enabled), tid))
    return db.query_one("SELECT * FROM automations WHERE id=?", (tid,))


@app.post("/api/automations/{tid}/run")
def run_automation(tid: str):
    a = db.query_one("SELECT * FROM automations WHERE id=?", (tid,))
    if not a:
        raise HTTPException(404, "Otomasyon bulunamadı")
    return {"conversation_id": scheduler.run_automation(a)}


@app.delete("/api/automations/{tid}")
def delete_automation(tid: str):
    db.execute("DELETE FROM automations WHERE id=?", (tid,))
    return {"ok": True}


# ---- Arayüz (derlenmiş React uygulaması) ---------------------------------

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    target = STATIC_DIR / path
    if path and target.is_file() and STATIC_DIR in target.resolve().parents:
        return FileResponse(target)
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Arayüz derlenmemiş. 'frontend' klasöründe 'npm run build' çalıştırın."}, 503)


def run() -> None:
    import uvicorn
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    run()
