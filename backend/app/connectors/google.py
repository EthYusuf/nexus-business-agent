"""Google Workspace entegrasyonları: Gmail, Takvim, Drive, E-Tablolar."""
from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from urllib.parse import quote

from .base import Connector, ConnectorError, Field, arr, cached_token, i, register, s, tool

GOOGLE_FIELDS = [
    Field("client_id", "OAuth Client ID", placeholder="xxxx.apps.googleusercontent.com"),
    Field("client_secret", "OAuth Client Secret", "password"),
    Field("refresh_token", "Refresh Token", "password",
          help="Google OAuth Playground veya kendi OAuth akışınızla alınır."),
]

GOOGLE_STEPS = [
    "console.cloud.google.com → yeni proje oluşturun ve ilgili API'yi etkinleştirin (Gmail / Calendar / Drive / Sheets).",
    "API'ler ve Hizmetler → Kimlik Bilgileri → 'OAuth istemci kimliği' (Web uygulaması) oluşturun. Yönlendirme URI'si: https://developers.google.com/oauthplayground",
    "developers.google.com/oauthplayground → sağ üstteki ayarlardan 'Use your own OAuth credentials' seçip Client ID/Secret girin.",
    "Gerekli kapsamları (scope) seçip yetkilendirin, 'Exchange authorization code for tokens' ile Refresh Token'ı alın.",
    "Aynı Client ID / Secret / Refresh Token'ı tüm Google entegrasyonlarında kullanabilirsiniz.",
]


class GoogleBase(Connector):
    category = "Google Workspace"
    fields = GOOGLE_FIELDS
    setup_steps = GOOGLE_STEPS

    def token(self) -> str:
        rt = self.secret("refresh_token")

        def fetch():
            data = self.http("POST", "https://oauth2.googleapis.com/token", data={
                "client_id": self.secret("client_id"),
                "client_secret": self.secret("client_secret"),
                "refresh_token": rt,
                "grant_type": "refresh_token",
            })
            if "access_token" not in data:
                raise ConnectorError(f"Google token alınamadı: {data}")
            return data["access_token"], data.get("expires_in", 3600)

        return cached_token("google:" + rt[-16:], fetch)

    def g(self, method: str, url: str, **kw):
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token()}"
        return self.http(method, url, headers=headers, **kw)


def _b64url_decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    if payload.get("mimeType", "").startswith("text/plain") and payload.get("body", {}).get("data"):
        return _b64url_decode(payload["body"]["data"])
    html = ""
    for part in payload.get("parts", []) or []:
        text = _extract_body(part)
        if text and part.get("mimeType") == "text/plain":
            return text
        if text:
            html = html or text
    if not html and payload.get("body", {}).get("data"):
        html = _b64url_decode(payload["body"]["data"])
    return html


@register
class Gmail(GoogleBase):
    id = "gmail"
    name = "Gmail"
    description = "E-postaları arayın, okuyun, yanıtlayın ve taslak oluşturun."
    icon = "mail"
    color = "#ea4335"
    docs_url = "https://developers.google.com/gmail/api"
    API = "https://gmail.googleapis.com/gmail/v1/users/me"

    def test(self) -> str:
        p = self.g("GET", f"{self.API}/profile")
        return f"Bağlandı: {p.get('emailAddress')} ({p.get('messagesTotal')} e-posta)"

    @tool("Gmail'de e-posta arar. Gmail arama sözdizimi desteklenir (ör. 'is:unread', 'from:ali@x.com', 'newer_than:2d', 'subject:fatura').",
          {"query": s("Gmail arama sorgusu"), "max_results": i("En fazla kaç sonuç (varsayılan 10)")})
    def search_emails(self, query: str = "", max_results: int = 10):
        data = self.g("GET", f"{self.API}/messages", params={"q": query, "maxResults": min(max_results, 50)})
        out = []
        for m in data.get("messages", []):
            msg = self.g("GET", f"{self.API}/messages/{m['id']}", params={
                "format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]})
            h = {x["name"]: x["value"] for x in msg.get("payload", {}).get("headers", [])}
            out.append({"id": m["id"], "thread_id": msg.get("threadId"), "from": h.get("From"),
                        "to": h.get("To"), "subject": h.get("Subject"), "date": h.get("Date"),
                        "snippet": msg.get("snippet"), "labels": msg.get("labelIds")})
        return {"count": len(out), "emails": out}

    @tool("Bir e-postanın tam içeriğini okur.", {"message_id": s("E-posta ID'si")}, ["message_id"])
    def read_email(self, message_id: str):
        msg = self.g("GET", f"{self.API}/messages/{message_id}", params={"format": "full"})
        h = {x["name"]: x["value"] for x in msg.get("payload", {}).get("headers", [])}
        return {"id": message_id, "thread_id": msg.get("threadId"), "from": h.get("From"),
                "to": h.get("To"), "subject": h.get("Subject"), "date": h.get("Date"),
                "message_id_header": h.get("Message-ID") or h.get("Message-Id"),
                "body": _extract_body(msg.get("payload", {}))[:15000]}

    def _raw(self, to, subject, body, cc="", in_reply_to="", html=False):
        em = EmailMessage()
        em["To"] = to
        em["Subject"] = subject
        if cc:
            em["Cc"] = cc
        if in_reply_to:
            em["In-Reply-To"] = in_reply_to
            em["References"] = in_reply_to
        if html:
            em.set_content("Bu e-posta HTML içerir.")
            em.add_alternative(body, subtype="html")
        else:
            em.set_content(body)
        return base64.urlsafe_b64encode(em.as_bytes()).decode()

    @tool("E-posta gönderir. Yanıt için thread_id ve in_reply_to (orijinal Message-ID başlığı) verin.",
          {"to": s("Alıcı(lar), virgülle ayrılmış"), "subject": s("Konu"), "body": s("İleti metni"),
           "cc": s("Bilgi (CC)"), "thread_id": s("Yanıtlanan konunun thread ID'si"),
           "in_reply_to": s("Orijinal Message-ID başlığı"), "html": {"type": "boolean", "description": "Gövde HTML mi?"}},
          ["to", "subject", "body"], write=True)
    def send_email(self, to, subject, body, cc="", thread_id="", in_reply_to="", html=False):
        payload = {"raw": self._raw(to, subject, body, cc, in_reply_to, html)}
        if thread_id:
            payload["threadId"] = thread_id
        r = self.g("POST", f"{self.API}/messages/send", json=payload)
        return {"sent": True, "id": r.get("id"), "thread_id": r.get("threadId")}

    @tool("Gönderilmeden önce gözden geçirilmek üzere taslak e-posta oluşturur.",
          {"to": s("Alıcı"), "subject": s("Konu"), "body": s("İleti metni"), "thread_id": s("Thread ID (isteğe bağlı)")},
          ["to", "subject", "body"])
    def create_draft(self, to, subject, body, thread_id=""):
        msg = {"raw": self._raw(to, subject, body)}
        if thread_id:
            msg["threadId"] = thread_id
        r = self.g("POST", f"{self.API}/drafts", json={"message": msg})
        return {"draft_id": r.get("id")}

    @tool("E-postaya etiket ekler/kaldırır (ör. okundu işaretlemek için UNREAD kaldırın).",
          {"message_id": s("E-posta ID"), "add_labels": arr("Eklenecek etiketler", s("etiket")),
           "remove_labels": arr("Kaldırılacak etiketler", s("etiket"))}, ["message_id"], write=True)
    def modify_labels(self, message_id, add_labels=None, remove_labels=None):
        return self.g("POST", f"{self.API}/messages/{message_id}/modify",
                      json={"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []})


@register
class GoogleCalendar(GoogleBase):
    id = "google_calendar"
    name = "Google Takvim"
    description = "Toplantıları listeleyin, yeni etkinlik ve davet oluşturun."
    icon = "calendar"
    color = "#4285f4"
    docs_url = "https://developers.google.com/calendar/api"
    API = "https://www.googleapis.com/calendar/v3/calendars"

    def test(self) -> str:
        cal = self.g("GET", f"{self.API}/primary")
        return f"Bağlandı: {cal.get('summary')} ({cal.get('timeZone')})"

    @tool("Belirli bir zaman aralığındaki takvim etkinliklerini listeler.",
          {"time_min": s("Başlangıç (ISO 8601, ör. 2026-11-01T00:00:00+03:00)"),
           "time_max": s("Bitiş (ISO 8601)"), "query": s("Metin araması"),
           "calendar_id": s("Takvim ID (varsayılan primary)")}, ["time_min"])
    def list_events(self, time_min, time_max="", query="", calendar_id="primary"):
        params = {"timeMin": time_min, "singleEvents": "true", "orderBy": "startTime", "maxResults": 50}
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        data = self.g("GET", f"{self.API}/{quote(calendar_id)}/events", params=params)
        return [{"id": e.get("id"), "summary": e.get("summary"), "start": e.get("start"),
                 "end": e.get("end"), "location": e.get("location"),
                 "attendees": [a.get("email") for a in e.get("attendees", [])],
                 "link": e.get("htmlLink")} for e in data.get("items", [])]

    @tool("Takvime yeni etkinlik ekler; katılımcılara davet gönderebilir.",
          {"summary": s("Başlık"), "start": s("Başlangıç (ISO 8601)"), "end": s("Bitiş (ISO 8601)"),
           "description": s("Açıklama"), "location": s("Konum"),
           "attendees": arr("Katılımcı e-postaları", s("e-posta")),
           "timezone": s("Saat dilimi (varsayılan Europe/Istanbul)"),
           "add_meet": {"type": "boolean", "description": "Google Meet bağlantısı eklensin mi"}},
          ["summary", "start", "end"], write=True)
    def create_event(self, summary, start, end, description="", location="", attendees=None,
                     timezone="Europe/Istanbul", add_meet=False):
        body = {"summary": summary, "description": description, "location": location,
                "start": {"dateTime": start, "timeZone": timezone},
                "end": {"dateTime": end, "timeZone": timezone},
                "attendees": [{"email": a} for a in (attendees or [])]}
        params = {"sendUpdates": "all"}
        if add_meet:
            body["conferenceData"] = {"createRequest": {"requestId": base64.b16encode(summary.encode()[:8]).decode()}}
            params["conferenceDataVersion"] = 1
        e = self.g("POST", f"{self.API}/primary/events", params=params, json=body)
        return {"id": e.get("id"), "link": e.get("htmlLink"), "meet": e.get("hangoutLink")}

    @tool("Etkinliği siler.", {"event_id": s("Etkinlik ID")}, ["event_id"], write=True)
    def delete_event(self, event_id):
        self.g("DELETE", f"{self.API}/primary/events/{event_id}", expect_json=False)
        return {"deleted": True}


@register
class GoogleDrive(GoogleBase):
    id = "google_drive"
    name = "Google Drive"
    description = "Dosyaları arayın, belgelerin içeriğini okuyun, yeni dosya yükleyin."
    icon = "hard-drive"
    color = "#0f9d58"
    docs_url = "https://developers.google.com/drive/api"
    API = "https://www.googleapis.com/drive/v3/files"

    def test(self) -> str:
        about = self.g("GET", "https://www.googleapis.com/drive/v3/about", params={"fields": "user"})
        return f"Bağlandı: {about.get('user', {}).get('emailAddress')}"

    @tool("Drive'da dosya arar.", {"name_contains": s("Dosya adında geçen metin"),
                                   "full_text": s("İçerikte geçen metin"), "max_results": i("Sonuç sayısı")})
    def search_files(self, name_contains="", full_text="", max_results=20):
        q = ["trashed = false"]
        if name_contains:
            q.append(f"name contains '{name_contains.replace(chr(39), '')}'")
        if full_text:
            q.append(f"fullText contains '{full_text.replace(chr(39), '')}'")
        data = self.g("GET", self.API, params={
            "q": " and ".join(q), "pageSize": min(max_results, 100), "orderBy": "modifiedTime desc",
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)"})
        return data.get("files", [])

    @tool("Bir dosyanın metin içeriğini okur (Google Dokümanlar/Tablolar dahil).",
          {"file_id": s("Dosya ID")}, ["file_id"])
    def read_file(self, file_id):
        meta = self.g("GET", f"{self.API}/{file_id}", params={"fields": "name,mimeType"})
        mt = meta.get("mimeType", "")
        if mt.startswith("application/vnd.google-apps"):
            export = "text/csv" if "spreadsheet" in mt else "text/plain"
            text = self.g("GET", f"{self.API}/{file_id}/export", params={"mimeType": export}, expect_json=False)
        else:
            text = self.g("GET", f"{self.API}/{file_id}", params={"alt": "media"}, expect_json=False)
        return {"name": meta.get("name"), "mimeType": mt, "content": text[:20000]}

    @tool("Drive'a metin tabanlı yeni dosya yükler (txt, csv, md, html).",
          {"name": s("Dosya adı"), "content": s("Dosya içeriği"), "mime_type": s("MIME türü (varsayılan text/plain)"),
           "folder_id": s("Klasör ID (isteğe bağlı)"),
           "convert_to_google_doc": {"type": "boolean", "description": "Google Dokümanına dönüştür"}},
          ["name", "content"], write=True)
    def upload_file(self, name, content, mime_type="text/plain", folder_id="", convert_to_google_doc=False):
        meta = {"name": name}
        if folder_id:
            meta["parents"] = [folder_id]
        if convert_to_google_doc:
            meta["mimeType"] = "application/vnd.google-apps.document"
        boundary = "nexusboundary"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{boundary}\r\nContent-Type: {mime_type}; charset=UTF-8\r\n\r\n{content}\r\n--{boundary}--")
        r = self.g("POST", "https://www.googleapis.com/upload/drive/v3/files",
                   params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                   headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                   content=body.encode("utf-8"))
        return r


@register
class GoogleSheets(GoogleBase):
    id = "google_sheets"
    name = "Google E-Tablolar"
    description = "Tablolardan veri okuyun, satır ekleyin, hücreleri güncelleyin."
    icon = "sheet"
    color = "#34a853"
    docs_url = "https://developers.google.com/sheets/api"
    API = "https://sheets.googleapis.com/v4/spreadsheets"

    def test(self) -> str:
        self.token()
        return "Google kimlik doğrulaması başarılı."

    @tool("Tablonun sayfalarını (sekmelerini) listeler.", {"spreadsheet_id": s("Tablo ID (URL'deki /d/ sonrası)")},
          ["spreadsheet_id"])
    def get_sheets(self, spreadsheet_id):
        d = self.g("GET", f"{self.API}/{spreadsheet_id}", params={"fields": "properties.title,sheets.properties"})
        return {"title": d.get("properties", {}).get("title"),
                "sheets": [sh["properties"]["title"] for sh in d.get("sheets", [])]}

    @tool("Bir aralıktaki değerleri okur (ör. 'Sayfa1!A1:F100').",
          {"spreadsheet_id": s("Tablo ID"), "range": s("A1 gösterimiyle aralık")}, ["spreadsheet_id", "range"])
    def read_range(self, spreadsheet_id, range):
        d = self.g("GET", f"{self.API}/{spreadsheet_id}/values/{quote(range)}")
        return {"range": d.get("range"), "values": d.get("values", [])}

    @tool("Tablonun sonuna satır(lar) ekler.",
          {"spreadsheet_id": s("Tablo ID"), "range": s("Sayfa adı veya aralık, ör. 'Sayfa1'"),
           "rows": arr("Eklenecek satırlar", arr("Hücreler", {"type": ["string", "number", "boolean", "null"]}))},
          ["spreadsheet_id", "range", "rows"], write=True)
    def append_rows(self, spreadsheet_id, range, rows):
        return self.g("POST", f"{self.API}/{spreadsheet_id}/values/{quote(range)}:append",
                      params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
                      json={"values": rows})

    @tool("Belirli bir aralığı verilen değerlerle günceller.",
          {"spreadsheet_id": s("Tablo ID"), "range": s("Aralık"),
           "values": arr("Satırlar", arr("Hücreler", {"type": ["string", "number", "boolean", "null"]}))},
          ["spreadsheet_id", "range", "values"], write=True)
    def update_range(self, spreadsheet_id, range, values):
        return self.g("PUT", f"{self.API}/{spreadsheet_id}/values/{quote(range)}",
                      params={"valueInputOption": "USER_ENTERED"}, json={"values": values})
