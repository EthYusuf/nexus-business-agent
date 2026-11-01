"""Ajan çalışma motoru.

Claude API + araç kullanımı ile manuel ajan döngüsü. Döngünün manuel olmasının nedeni
insan onayıdır: yazma yetkili bir araç (e-posta gönder, fatura kes...) çağrıldığında
konuşma 'awaiting_approval' durumunda bekletilir, kullanıcı panelden onayladığında
aynı noktadan devam edilir. Mesaj geçmişi yalnızca sona ekleme ile büyür (append-only),
böylece düşünce blokları ve önbellek geçerli kalır.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import traceback
from typing import Any

import anthropic

from .. import db
from ..config import DEFAULT_MODEL, MAX_AGENT_TURNS
from ..connectors import ToolSpec, to_text, tools_for

FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5"}
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

_running: set[str] = set()
_run_lock = threading.Lock()


# ---- yardımcılar ---------------------------------------------------------

def get_client() -> anthropic.Anthropic:
    key = db.get_setting("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Anthropic API anahtarı ayarlanmamış. Ayarlar sayfasından ekleyin.")
    return anthropic.Anthropic(api_key=key, max_retries=3)


def load_conv(conv_id: str) -> dict[str, Any]:
    c = db.query_one("SELECT * FROM conversations WHERE id=?", (conv_id,))
    if not c:
        raise KeyError(conv_id)
    c["api_messages"] = json.loads(c["api_messages"] or "[]")
    c["pending"] = json.loads(c["pending"] or "[]")
    return c


def save_conv(conv_id: str, **fields: Any) -> None:
    for k in ("api_messages", "pending"):
        if k in fields:
            fields[k] = json.dumps(fields[k], ensure_ascii=False, default=str)
    fields["updated_at"] = db.now()
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE conversations SET {sets} WHERE id=?", (*fields.values(), conv_id))


def load_agent(agent_id: str) -> dict[str, Any]:
    a = db.query_one("SELECT * FROM agents WHERE id=?", (agent_id,))
    if not a:
        raise KeyError(agent_id)
    a["connectors"] = json.loads(a["connectors"] or "[]")
    return a


def build_system(agent: dict[str, Any], tools: dict[str, ToolSpec]) -> str:
    company = db.get_setting("company_name", "") or "Şirket"
    profile = db.get_setting("company_profile", "")
    today = dt.datetime.now().strftime("%Y-%m-%d (%A)")
    connected = sorted({t.connector_id for t in tools.values()})
    parts = [
        agent.get("system_prompt") or "Sen yardımsever bir iş asistanısın.",
        f"\n## Şirket\nAd: {company}\n{profile}".rstrip(),
        f"\n## Bağlam\nBugünün tarihi: {today}. Saat dilimi: Europe/Istanbul. "
        f"Kullanılabilir entegrasyonlar: {', '.join(connected) or 'yok'}.",
        "\n## Çalışma kuralları\n"
        "- Türkçe, net ve profesyonel yanıt ver. Kullanıcının dilinde yaz.\n"
        "- Bir işlem için gereken bilgileri önce okuma araçlarıyla topla; tahmin etme.\n"
        "- E-posta göndermek, fatura kesmek, stok/fiyat değiştirmek gibi dış dünyayı etkileyen "
        "araçlar kullanıcı onayından geçebilir; kullanıcı reddederse alternatif öner, ısrar etme.\n"
        "- Araç hatası alırsan hatayı açıkça bildir ve olası çözümü söyle.\n"
        "- İşin sonunda ne yaptığını kısa bir özetle bildir (gönderilenler, oluşturulan kayıtlar, ID'ler).",
    ]
    return "\n".join(parts)


def _text_of(content: list[dict[str, Any]]) -> str:
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


# ---- dış API -------------------------------------------------------------

def create_conversation(agent_id: str, title: str = "", source: str = "chat") -> str:
    cid = db.new_id("c_")
    db.execute(
        "INSERT INTO conversations(id, agent_id, title, status, api_messages, pending, source, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (cid, agent_id, title or "Yeni sohbet", "idle", "[]", "[]", source, db.now(), db.now()),
    )
    return cid


def send_message(conv_id: str, text: str, background: bool = True) -> None:
    conv = load_conv(conv_id)
    if conv["status"] in ("running", "awaiting_approval"):
        raise RuntimeError("Ajan şu anda meşgul veya onay bekliyor.")
    msgs = conv["api_messages"]
    dangling = _close_dangling(msgs)
    if dangling:
        msgs.append({"role": "user", "content": [*dangling, {"type": "text", "text": text}]})
    else:
        msgs.append({"role": "user", "content": text})
    title = conv["title"]
    if title in ("", "Yeni sohbet"):
        title = text.strip().split("\n")[0][:60]
    save_conv(conv_id, api_messages=msgs, status="running", error=None, title=title)
    db.add_event(conv_id, "user", {"text": text})
    _spawn(conv_id, background)


def decide(conv_id: str, decisions: dict[str, dict[str, Any]], background: bool = True) -> None:
    """decisions: {tool_use_id: {"approve": bool, "input": {...isteğe bağlı düzenlenmiş girdi}}}"""
    conv = load_conv(conv_id)
    if conv["status"] != "awaiting_approval":
        raise RuntimeError("Bu konuşmada onay bekleyen işlem yok.")
    pending = conv["pending"]
    for p in pending:
        d = decisions.get(p["id"])
        if p["needs_approval"] and d is None:
            raise RuntimeError("Tüm işlemler için karar verilmelidir.")
        if d:
            p["decision"] = "approved" if d.get("approve") else "rejected"
            if d.get("approve") and isinstance(d.get("input"), dict):
                p["input"] = d["input"]
        db.add_event(conv_id, "approval", {"tool_use_id": p["id"], "tool": p["name"],
                                           "decision": p.get("decision", "auto")})
    save_conv(conv_id, pending=pending, status="running")
    _spawn(conv_id, background, resume=True)


def stop(conv_id: str) -> None:
    conv = load_conv(conv_id)
    db.set_setting(f"stop:{conv_id}", True)
    if conv["status"] in ("awaiting_approval", "error"):
        save_conv(conv_id, pending=[], status="idle")
        db.add_event(conv_id, "system", {"text": "Kullanıcı tarafından durduruldu."})


def _close_dangling(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Son asistan mesajında yanıtlanmamış araç çağrısı kaldıysa iptal sonucu üretir."""
    if not msgs or msgs[-1]["role"] != "assistant" or not isinstance(msgs[-1]["content"], list):
        return []
    return [{"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
             "content": "Bu işlem iptal edildi; çalıştırılmadı."}
            for b in msgs[-1]["content"] if b.get("type") == "tool_use"]


def _spawn(conv_id: str, background: bool, resume: bool = False) -> None:
    if background:
        threading.Thread(target=_run_safe, args=(conv_id, resume), daemon=True).start()
    else:
        _run_safe(conv_id, resume)


def _run_safe(conv_id: str, resume: bool) -> None:
    with _run_lock:
        if conv_id in _running:
            return
        _running.add(conv_id)
    try:
        db.set_setting(f"stop:{conv_id}", False)
        _run(conv_id, resume)
    except Exception as e:  # noqa: BLE001
        msg = _friendly_error(e)
        db.add_event(conv_id, "error", {"message": msg, "trace": traceback.format_exc()[-2000:]})
        save_conv(conv_id, status="error", error=msg)
    finally:
        with _run_lock:
            _running.discard(conv_id)


def _friendly_error(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Anthropic API anahtarı geçersiz. Ayarlar sayfasından kontrol edin."
    if isinstance(e, anthropic.RateLimitError):
        return "API hız sınırına ulaşıldı. Biraz bekleyip tekrar deneyin."
    if isinstance(e, anthropic.BadRequestError):
        return f"API isteği reddedildi: {e.message}"
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API hatası ({e.status_code}): {e.message}"
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude API'ye bağlanılamadı. İnternet bağlantınızı kontrol edin."
    return str(e)


# ---- araç yürütme ---------------------------------------------------------

def _execute(conv: dict[str, Any], agent: dict[str, Any], tools: dict[str, ToolSpec],
             call: dict[str, Any], approved_by: str) -> dict[str, Any]:
    name, args = call["name"], call.get("input") or {}
    spec = tools.get(name)
    started = time.time()
    if not spec:
        ok, text = False, f"Araç bulunamadı veya entegrasyon devre dışı: {name}"
    else:
        try:
            text, ok = to_text(spec.handler(**args)), True
        except TypeError as e:
            text, ok = f"Geçersiz parametre: {e}", False
        except Exception as e:  # noqa: BLE001
            text, ok = f"Hata: {e}", False
    ms = int((time.time() - started) * 1000)
    db.execute(
        "INSERT INTO activity(conversation_id, agent_id, connector_id, tool, input, result, ok, duration_ms, approved_by, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (conv["id"], agent["id"], spec.connector_id if spec else name.split("__")[0], name,
         json.dumps(args, ensure_ascii=False, default=str), text[:4000], int(ok), ms, approved_by, db.now()),
    )
    db.add_event(conv["id"], "tool_result", {"tool_use_id": call["id"], "tool": name, "ok": ok,
                                            "result": text[:3000], "duration_ms": ms})
    res = {"type": "tool_result", "tool_use_id": call["id"], "content": text}
    if not ok:
        res["is_error"] = True
    return res


def _resolve_pending(conv: dict[str, Any], agent: dict[str, Any], tools: dict[str, ToolSpec]) -> list[dict[str, Any]]:
    results = []
    for p in conv["pending"]:
        if p.get("decision") == "rejected":
            db.add_event(conv["id"], "tool_result", {"tool_use_id": p["id"], "tool": p["name"], "ok": False,
                                                    "result": "Kullanıcı reddetti.", "duration_ms": 0})
            results.append({"type": "tool_result", "tool_use_id": p["id"], "is_error": True,
                            "content": "Kullanıcı bu işlemi reddetti. İşlemi yapma; gerekiyorsa kullanıcıya alternatif sor."})
        else:
            by = "user" if p["needs_approval"] else "auto"
            results.append(_execute(conv, agent, tools, p, by))
    return results


# ---- ana döngü -----------------------------------------------------------

def _run(conv_id: str, resume: bool) -> None:
    conv = load_conv(conv_id)
    agent = load_agent(conv["agent_id"])
    tools = tools_for(agent["connectors"])
    msgs: list[dict[str, Any]] = conv["api_messages"]

    if resume and conv["pending"]:
        msgs.append({"role": "user", "content": _resolve_pending(conv, agent, tools)})
        save_conv(conv_id, api_messages=msgs, pending=[])

    client = get_client()
    model = agent.get("model") or db.get_setting("default_model", DEFAULT_MODEL)
    effort = agent.get("effort") or db.get_setting("default_effort", "medium")
    api_tools: list[dict[str, Any]] = [t.to_api() for t in sorted(tools.values(), key=lambda t: t.full_name)]
    if "web" in agent["connectors"] and model != "claude-haiku-5-5":
        api_tools.append(WEB_SEARCH_TOOL)
    system = build_system(agent, tools)

    for _ in range(MAX_AGENT_TURNS):
        if db.get_setting(f"stop:{conv_id}"):
            db.add_event(conv_id, "system", {"text": "Kullanıcı tarafından durduruldu."})
            save_conv(conv_id, status="idle")
            return

        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=16000, system=system, messages=msgs,
            thinking={"type": "adaptive"}, output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
        )
        if api_tools:
            kwargs["tools"] = api_tools
        if model in FALLBACK_MODELS and db.get_setting("fallback_enabled", True):
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        resp = client.beta.messages.create(**kwargs)

        content = [blk.model_dump(mode="json", exclude_none=True) for blk in resp.content]
        msgs.append({"role": "assistant", "content": content})
        u = resp.usage
        db.execute("UPDATE conversations SET usage_in=usage_in+?, usage_out=usage_out+? WHERE id=?",
                   ((u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
                    + (getattr(u, "cache_creation_input_tokens", 0) or 0), u.output_tokens or 0, conv_id))

        text = _text_of(content)
        for blk in content:
            if blk.get("type") == "server_tool_use":
                db.add_event(conv_id, "tool_call", {"tool_use_id": blk.get("id"), "tool": "web_search",
                                                   "input": blk.get("input"), "server": True})
        tool_calls = [b for b in content if b.get("type") == "tool_use"]
        if text:
            db.add_event(conv_id, "assistant", {"text": text, "model": resp.model})
        save_conv(conv_id, api_messages=msgs)

        stop_reason = resp.stop_reason
        if stop_reason == "pause_turn":
            continue
        if stop_reason == "refusal":
            db.add_event(conv_id, "error", {"message": "Model bu isteği güvenlik nedeniyle yanıtlamadı."})
            save_conv(conv_id, status="idle")
            return
        if stop_reason == "max_tokens" and not tool_calls:
            db.add_event(conv_id, "system", {"text": "Yanıt uzunluk sınırına ulaştı. 'Devam et' yazabilirsiniz."})
            save_conv(conv_id, status="idle")
            return
        if stop_reason != "tool_use" or not tool_calls:
            save_conv(conv_id, status="idle")
            return

        pending = []
        for call in tool_calls:
            spec = tools.get(call["name"])
            needs = bool(spec and spec.write and not agent["auto_approve"])
            pending.append({"id": call["id"], "name": call["name"], "input": call.get("input") or {},
                            "needs_approval": needs, "write": bool(spec and spec.write),
                            "connector": spec.connector_id if spec else "", "description": spec.description if spec else ""})
            db.add_event(conv_id, "tool_call", {"tool_use_id": call["id"], "tool": call["name"],
                                               "input": call.get("input"), "needs_approval": needs})

        if any(p["needs_approval"] for p in pending):
            save_conv(conv_id, pending=pending, status="awaiting_approval")
            db.add_event(conv_id, "system", {"text": "Onay bekleniyor."})
            return

        conv["pending"] = pending
        msgs.append({"role": "user", "content": _resolve_pending(conv, agent, tools)})
        save_conv(conv_id, api_messages=msgs, pending=[])

    db.add_event(conv_id, "system", {"text": f"Azami adım sayısına ({MAX_AGENT_TURNS}) ulaşıldı. 'Devam et' yazabilirsiniz."})
    save_conv(conv_id, status="idle")


def recover_stuck() -> None:
    """Uygulama yeniden başlatıldığında yarıda kalan çalışmaları işaretler."""
    db.execute("UPDATE conversations SET status='error', error='Uygulama yeniden başlatıldı; mesajı tekrar gönderin.' "
               "WHERE status='running'")
