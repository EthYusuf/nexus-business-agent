"""Entegrasyon (connector) altyapısı.

Her entegrasyon bir `Connector` alt sınıfıdır. `@tool` ile işaretlenen her metot,
yapay zeka ajanlarının çağırabileceği bir araca dönüşür. `write=True` olan araçlar
(e-posta gönderme, fatura kesme vb.) varsayılan olarak kullanıcı onayı gerektirir.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

REGISTRY: dict[str, type["Connector"]] = {}


class ConnectorError(Exception):
    pass


@dataclass
class Field:
    key: str
    label: str
    type: str = "text"  # text | password | url | textarea | select
    required: bool = True
    help: str = ""
    placeholder: str = ""
    default: str = ""
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ToolSpec:
    connector_id: str
    name: str
    description: str
    params: dict[str, Any]
    required: list[str]
    write: bool
    handler: Callable[..., Any]

    @property
    def full_name(self) -> str:
        return f"{self.connector_id}__{self.name}"

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.full_name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": self.required,
            },
        }


def tool(description: str, params: dict[str, Any] | None = None,
         required: list[str] | None = None, write: bool = False):
    """Bir connector metodunu ajan aracı olarak işaretler."""
    def deco(fn):
        fn._tool = {
            "description": description,
            "params": params or {},
            "required": required or [],
            "write": write,
        }
        return fn
    return deco


def register(cls: type["Connector"]) -> type["Connector"]:
    REGISTRY[cls.id] = cls
    return cls


# Kısa JSON şema yardımcıları
def s(desc: str, **kw) -> dict[str, Any]:
    return {"type": "string", "description": desc, **kw}


def i(desc: str, **kw) -> dict[str, Any]:
    return {"type": "integer", "description": desc, **kw}


def n(desc: str, **kw) -> dict[str, Any]:
    return {"type": "number", "description": desc, **kw}


def b(desc: str) -> dict[str, Any]:
    return {"type": "boolean", "description": desc}


def arr(desc: str, items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "description": desc, "items": items}


class Connector:
    id: str = ""
    name: str = ""
    category: str = "Genel"
    description: str = ""
    icon: str = "plug"
    color: str = "#6366f1"
    docs_url: str = ""
    setup_steps: list[str] = []
    fields: list[Field] = []
    builtin: bool = False  # kimlik bilgisi gerektirmeyen yerleşik araçlar

    def __init__(self, secrets: dict[str, Any] | None = None):
        self.secrets = secrets or {}

    # ---- meta -----------------------------------------------------------
    @classmethod
    def meta(cls) -> dict[str, Any]:
        return {
            "id": cls.id,
            "name": cls.name,
            "category": cls.category,
            "description": cls.description,
            "icon": cls.icon,
            "color": cls.color,
            "docs_url": cls.docs_url,
            "setup_steps": cls.setup_steps,
            "fields": [f.to_dict() for f in cls.fields],
            "builtin": cls.builtin,
            "tools": [
                {"name": t.name, "description": t.description, "write": t.write}
                for t in cls({}).tools()
            ],
        }

    def tools(self) -> list[ToolSpec]:
        out = []
        for attr in dir(type(self)):
            fn = getattr(type(self), attr)
            meta = getattr(fn, "_tool", None)
            if meta:
                out.append(ToolSpec(
                    connector_id=self.id, name=attr, handler=getattr(self, attr), **meta,
                ))
        return out

    def test(self) -> str:
        """Bağlantıyı doğrular; başarılıysa açıklayıcı bir mesaj döndürür."""
        return "Bağlantı yapılandırıldı."

    # ---- yardımcılar ----------------------------------------------------
    def secret(self, key: str, default: str = "") -> str:
        val = self.secrets.get(key)
        if val in (None, ""):
            fld = next((f for f in self.fields if f.key == key), None)
            if fld and fld.default:
                return fld.default
            if default:
                return default
            if fld and fld.required:
                raise ConnectorError(f"'{fld.label}' alanı ayarlanmamış.")
            return ""
        return str(val).strip()

    def http(self, method: str, url: str, *, expect_json: bool = True, **kw) -> Any:
        kw.setdefault("timeout", 30)
        try:
            resp = httpx.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise ConnectorError(f"Ağ hatası: {e}") from e
        if resp.status_code >= 400:
            raise ConnectorError(f"HTTP {resp.status_code}: {resp.text[:800]}")
        if not expect_json:
            return resp.text
        if not resp.content:
            return {"ok": True}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text[:5000]}


# ---- OAuth2 erişim belirteci önbelleği -----------------------------------
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def cached_token(cache_key: str, fetch: Callable[[], tuple[str, int]]) -> str:
    """fetch() -> (access_token, expires_in_seconds)"""
    with _token_lock:
        hit = _token_cache.get(cache_key)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
    token, expires_in = fetch()
    with _token_lock:
        _token_cache[cache_key] = (token, time.time() + int(expires_in or 3600))
    return token


def to_text(result: Any, limit: int = 20000) -> str:
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str, indent=1)
    if len(text) > limit:
        text = text[:limit] + f"\n... [çıktı {len(text) - limit} karakter kısaltıldı]"
    return text
