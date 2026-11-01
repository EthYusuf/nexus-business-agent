"""Yerleşik araçlar: Web, yerel çalışma klasörü ve genel Webhook (Zapier / Make / n8n)."""
from __future__ import annotations

import csv
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from ..config import WORKSPACE_DIR
from .base import Connector, ConnectorError, Field, arr, register, s, tool


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self.parts, self.links, self._skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href and href.startswith("http") and len(self.links) < 40:
                self.links.append(href)
        if tag in ("p", "br", "li", "h1", "h2", "h3", "tr", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


@register
class Web(Connector):
    id = "web"
    name = "Web Araştırma"
    category = "Yerleşik Araçlar"
    description = "İnternette arama (Claude web arama) ve web sayfası okuma."
    icon = "globe"
    color = "#0ea5e9"
    builtin = True
    fields = []

    def test(self):
        return "Yerleşik araç — kurulum gerekmez."

    @tool("Bir web sayfasını indirip okunabilir metnini döndürür.", {"url": s("Tam URL (https://...)")}, ["url"])
    def fetch_url(self, url):
        if not url.startswith(("http://", "https://")):
            raise ConnectorError("Geçerli bir http(s) adresi girin.")
        html = self.http("GET", url, expect_json=False, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 NexusAgent/1.0"})
        p = _TextExtractor()
        p.feed(html)
        text = re.sub(r"\n\s*\n+", "\n\n", "".join(p.parts))
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        return {"url": url, "title": title.group(1).strip() if title else "", "text": text.strip()[:18000],
                "links": p.links}


def _safe(path: str) -> Path:
    full = (WORKSPACE_DIR / path).resolve()
    if WORKSPACE_DIR.resolve() not in full.parents and full != WORKSPACE_DIR.resolve():
        raise ConnectorError("Çalışma klasörü dışına erişim engellendi.")
    return full


@register
class Files(Connector):
    id = "files"
    name = "Yerel Dosyalar"
    category = "Yerleşik Araçlar"
    description = "Ajanlar rapor, CSV ve belgeleri bilgisayarınızdaki güvenli çalışma klasörüne kaydeder."
    icon = "folder"
    color = "#64748b"
    builtin = True
    fields = []

    def test(self):
        return f"Çalışma klasörü: {WORKSPACE_DIR}"

    @tool("Çalışma klasöründeki dosyaları listeler.", {"subdir": s("Alt klasör (isteğe bağlı)")})
    def list_files(self, subdir=""):
        base = _safe(subdir or ".")
        if not base.exists():
            return []
        return [{"path": str(p.relative_to(WORKSPACE_DIR)).replace("\\", "/"), "size": p.stat().st_size}
                for p in sorted(base.rglob("*")) if p.is_file()][:200]

    @tool("Bir dosyanın içeriğini okur (metin, csv, md, json).", {"path": s("Dosya yolu")}, ["path"])
    def read_file(self, path):
        f = _safe(path)
        if not f.is_file():
            raise ConnectorError("Dosya bulunamadı.")
        return f.read_text(encoding="utf-8", errors="replace")[:20000]

    @tool("Dosya oluşturur veya üzerine yazar (rapor, not, e-posta taslağı...).",
          {"path": s("Dosya yolu, ör. raporlar/kasim.md"), "content": s("İçerik")}, ["path", "content"])
    def write_file(self, path, content):
        f = _safe(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return {"saved": str(f)}

    @tool("Tablo verisini Excel ile açılabilen CSV dosyası olarak kaydeder.",
          {"path": s("Dosya yolu, ör. raporlar/siparisler.csv"), "headers": arr("Başlıklar", s("başlık")),
           "rows": arr("Satırlar", arr("Hücreler", {"type": ["string", "number", "boolean", "null"]}))},
          ["path", "headers", "rows"])
    def write_csv(self, path, headers, rows):
        f = _safe(path if path.endswith(".csv") else path + ".csv")
        f.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(headers)
        w.writerows(rows)
        f.write_text("﻿" + buf.getvalue(), encoding="utf-8")  # BOM: Excel Türkçe karakterleri doğru gösterir
        return {"saved": str(f), "rows": len(rows)}


@register
class Webhook(Connector):
    id = "webhook"
    name = "Webhook (Zapier / Make / n8n)"
    category = "Otomasyon"
    description = "Herhangi bir sisteme JSON gönderin: Zapier, Make, n8n veya kendi ERP/API'niz. 5000+ uygulamaya köprü."
    icon = "webhook"
    color = "#ff4a00"
    setup_steps = ["Zapier/Make/n8n'de 'Webhook' tetikleyicisi oluşturun ve URL'yi buraya yapıştırın.",
                   "Ajana bu webhook'un ne işe yaradığını 'Açıklama' alanında anlatın."]
    fields = [
        Field("url", "Webhook URL", "url"),
        Field("purpose", "Açıklama", "textarea", required=False,
              help="Ör: 'Gönderilen veriyle Logo ERP'de cari kart açar. Alanlar: unvan, vkn, telefon'"),
        Field("auth_header", "Authorization başlığı", "password", required=False, placeholder="Bearer ..."),
    ]

    def test(self):
        self.secret("url")
        return "Webhook adresi kaydedildi."

    @tool("Yapılandırılmış webhook'a JSON veri gönderir. Webhook'un amacı entegrasyon açıklamasında belirtilir.",
          {"payload": {"type": "object", "description": "Gönderilecek JSON nesnesi"}}, ["payload"], write=True)
    def send(self, payload):
        headers = {"Content-Type": "application/json"}
        if self.secret("auth_header"):
            headers["Authorization"] = self.secret("auth_header")
        res = self.http("POST", self.secret("url"), headers=headers, content=json.dumps(payload, ensure_ascii=False),
                        expect_json=False)
        return {"ok": True, "response": res[:2000]}
