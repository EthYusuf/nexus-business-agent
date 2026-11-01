"""Tüm entegrasyonları yükler ve kayıt defterini dışa açar."""
from __future__ import annotations

import json
from typing import Any

from .. import db
from ..security import decrypt, encrypt, mask
# İçe aktarma sırası arayüzdeki sıralamayı belirler.
from . import google, communication, finance, commerce, productivity, builtin  # noqa: F401,I001  (kayıt için)
from .base import REGISTRY, Connector, ConnectorError, ToolSpec, to_text

__all__ = ["REGISTRY", "Connector", "ConnectorError", "ToolSpec", "to_text",
           "list_connectors", "get_instance", "save_connection", "delete_connection", "tools_for"]


def _row(cid: str) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM connections WHERE connector_id=?", (cid,))


def list_connectors() -> list[dict[str, Any]]:
    rows = {r["connector_id"]: r for r in db.query("SELECT * FROM connections")}
    out = []
    for cid, cls in REGISTRY.items():
        meta = cls.meta()
        row = rows.get(cid)
        secrets = decrypt(row["secrets"]) if row else {}
        meta["connected"] = bool(row) or cls.builtin
        meta["enabled"] = bool(row["enabled"]) if row else cls.builtin
        meta["status"] = row["status"] if row else ("ok" if cls.builtin else "not_configured")
        meta["status_message"] = row["status_message"] if row else ""
        meta["values"] = {
            f["key"]: (mask(secrets.get(f["key"], "")) if f["type"] == "password" else secrets.get(f["key"], ""))
            for f in meta["fields"]
        }
        out.append(meta)
    return out


def get_instance(cid: str) -> Connector:
    cls = REGISTRY.get(cid)
    if not cls:
        raise ConnectorError(f"Bilinmeyen entegrasyon: {cid}")
    row = _row(cid)
    return cls(decrypt(row["secrets"]) if row else {})


def save_connection(cid: str, values: dict[str, str], enabled: bool = True) -> None:
    cls = REGISTRY[cid]
    row = _row(cid)
    current = decrypt(row["secrets"]) if row else {}
    for f in cls.fields:
        v = values.get(f.key)
        if v is None:
            continue
        # Maskeli değer geri gönderildiyse eski gizli değeri koru
        if f.type == "password" and "••••" in v:
            continue
        current[f.key] = v
    db.execute(
        "INSERT INTO connections(connector_id, enabled, secrets, status, updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(connector_id) DO UPDATE SET enabled=excluded.enabled, secrets=excluded.secrets, "
        "updated_at=excluded.updated_at",
        (cid, int(enabled), encrypt(current), "unknown", db.now()),
    )


def set_status(cid: str, status: str, message: str) -> None:
    if not _row(cid):
        db.execute("INSERT INTO connections(connector_id, enabled, secrets, updated_at) VALUES(?,?,?,?)",
                   (cid, 1, encrypt({}), db.now()))
    db.execute("UPDATE connections SET status=?, status_message=?, updated_at=? WHERE connector_id=?",
               (status, message[:500], db.now(), cid))


def delete_connection(cid: str) -> None:
    db.execute("DELETE FROM connections WHERE connector_id=?", (cid,))


def is_active(cid: str) -> bool:
    cls = REGISTRY.get(cid)
    if not cls:
        return False
    row = _row(cid)
    if row is None:
        return cls.builtin
    return bool(row["enabled"])


def tools_for(connector_ids: list[str]) -> dict[str, ToolSpec]:
    """Bir ajanın erişebileceği aktif araçlar: tam_ad -> ToolSpec."""
    out: dict[str, ToolSpec] = {}
    for cid in connector_ids:
        if not is_active(cid):
            continue
        inst = get_instance(cid)
        for t in inst.tools():
            if cid == "webhook":
                purpose = inst.secrets.get("purpose")
                if purpose:
                    t.description += f" Bu webhook'un amacı: {purpose}"
            out[t.full_name] = t
    return out


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
