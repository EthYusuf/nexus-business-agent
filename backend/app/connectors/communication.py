"""İletişim entegrasyonları: Outlook, IMAP/SMTP, Slack, Telegram, WhatsApp, Twilio SMS."""
from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
from email.header import decode_header, make_header
from email.message import EmailMessage

from .base import Connector, ConnectorError, Field, arr, cached_token, i, register, s, tool


@register
class Outlook(Connector):
    id = "outlook"
    name = "Microsoft 365 / Outlook"
    category = "E-posta & Takvim"
    description = "Outlook e-postalarını ve takvimini Microsoft Graph üzerinden yönetin."
    icon = "inbox"
    color = "#0078d4"
    docs_url = "https://learn.microsoft.com/graph/api/resources/mail-api-overview"
    setup_steps = [
        "portal.azure.com → Microsoft Entra ID → Uygulama kayıtları → Yeni kayıt.",
        "API izinleri: Mail.ReadWrite, Mail.Send, Calendars.ReadWrite, offline_access (Delegated).",
        "Sertifikalar ve gizli diziler → yeni istemci gizli anahtarı oluşturun.",
        "OAuth yetkilendirme kodu akışıyla Refresh Token alın (ör. Postman veya Graph Explorer).",
    ]
    fields = [
        Field("tenant_id", "Tenant ID", default="common", required=False),
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client Secret", "password"),
        Field("refresh_token", "Refresh Token", "password"),
    ]
    API = "https://graph.microsoft.com/v1.0/me"

    def token(self):
        rt = self.secret("refresh_token")

        def fetch():
            d = self.http("POST", f"https://login.microsoftonline.com/{self.secret('tenant_id')}/oauth2/v2.0/token", data={
                "client_id": self.secret("client_id"), "client_secret": self.secret("client_secret"),
                "refresh_token": rt, "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default offline_access"})
            if "access_token" not in d:
                raise ConnectorError(str(d))
            return d["access_token"], d.get("expires_in", 3600)
        return cached_token("ms:" + rt[-16:], fetch)

    def g(self, method, path, **kw):
        return self.http(method, self.API + path, headers={"Authorization": f"Bearer {self.token()}"}, **kw)

    def test(self):
        me = self.g("GET", "")
        return f"Bağlandı: {me.get('mail') or me.get('userPrincipalName')}"

    @tool("Gelen kutusundaki e-postaları listeler/arar.",
          {"search": s("Arama metni"), "unread_only": {"type": "boolean", "description": "Sadece okunmamışlar"},
           "top": i("Sonuç sayısı")})
    def list_emails(self, search="", unread_only=False, top=10):
        params = {"$top": min(top, 50), "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead"}
        if search:
            params["$search"] = f'"{search}"'
        elif unread_only:
            params["$filter"] = "isRead eq false"
        d = self.g("GET", "/messages", params=params)
        return [{"id": m["id"], "subject": m.get("subject"), "from": m.get("from", {}).get("emailAddress"),
                 "date": m.get("receivedDateTime"), "preview": m.get("bodyPreview"), "read": m.get("isRead")}
                for m in d.get("value", [])]

    @tool("E-postanın tam içeriğini okur.", {"message_id": s("E-posta ID")}, ["message_id"])
    def read_email(self, message_id):
        m = self.g("GET", f"/messages/{message_id}", headers={"Prefer": 'outlook.body-content-type="text"'})
        return {"subject": m.get("subject"), "from": m.get("from"), "to": m.get("toRecipients"),
                "date": m.get("receivedDateTime"), "body": m.get("body", {}).get("content", "")[:15000]}

    @tool("Outlook üzerinden e-posta gönderir.",
          {"to": arr("Alıcılar", s("e-posta")), "subject": s("Konu"), "body": s("Metin"),
           "cc": arr("CC", s("e-posta"))}, ["to", "subject", "body"], write=True)
    def send_email(self, to, subject, body, cc=None):
        rec = lambda lst: [{"emailAddress": {"address": a}} for a in (lst or [])]
        self.g("POST", "/sendMail", json={"message": {
            "subject": subject, "body": {"contentType": "Text", "content": body},
            "toRecipients": rec(to), "ccRecipients": rec(cc)}, "saveToSentItems": True})
        return {"sent": True}

    @tool("Takvim etkinliklerini listeler.", {"start": s("Başlangıç ISO 8601"), "end": s("Bitiş ISO 8601")},
          ["start", "end"])
    def list_events(self, start, end):
        d = self.g("GET", "/calendarView", params={"startDateTime": start, "endDateTime": end, "$top": 50})
        return [{"subject": e.get("subject"), "start": e.get("start"), "end": e.get("end"),
                 "location": e.get("location", {}).get("displayName")} for e in d.get("value", [])]


def _dh(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


@register
class EmailImap(Connector):
    id = "email_imap"
    name = "Kurumsal E-posta (IMAP/SMTP)"
    category = "E-posta & Takvim"
    description = "Yandex, Zoho, cPanel, Turkcell vb. herhangi bir IMAP/SMTP e-posta hesabı."
    icon = "at-sign"
    color = "#f59e0b"
    setup_steps = [
        "E-posta sağlayıcınızın IMAP ve SMTP sunucu bilgilerini alın.",
        "2 adımlı doğrulama açıksa 'uygulama şifresi' oluşturun ve onu kullanın.",
    ]
    fields = [
        Field("imap_host", "IMAP Sunucusu", placeholder="imap.yandex.com"),
        Field("imap_port", "IMAP Port", default="993", required=False),
        Field("smtp_host", "SMTP Sunucusu", placeholder="smtp.yandex.com"),
        Field("smtp_port", "SMTP Port", default="465", required=False, help="465 (SSL) veya 587 (STARTTLS)"),
        Field("username", "Kullanıcı adı / e-posta"),
        Field("password", "Şifre / uygulama şifresi", "password"),
        Field("from_name", "Gönderen adı", required=False),
    ]

    def _imap(self):
        m = imaplib.IMAP4_SSL(self.secret("imap_host"), int(self.secret("imap_port")))
        m.login(self.secret("username"), self.secret("password"))
        return m

    def test(self):
        m = self._imap()
        m.select("INBOX", readonly=True)
        m.logout()
        return "IMAP bağlantısı başarılı."

    @tool("Gelen kutusundaki son e-postaları listeler.",
          {"unread_only": {"type": "boolean", "description": "Sadece okunmamış"},
           "search_from": s("Göndereni filtrele"), "search_subject": s("Konuyu filtrele"), "limit": i("Adet")})
    def list_emails(self, unread_only=False, search_from="", search_subject="", limit=10):
        m = self._imap()
        try:
            m.select("INBOX", readonly=True)
            crit = []
            if unread_only:
                crit.append("UNSEEN")
            if search_from:
                crit += ["FROM", f'"{search_from}"']
            if search_subject:
                crit += ["SUBJECT", f'"{search_subject}"']
            typ, data = m.uid("search", None, *(crit or ["ALL"]))
            uids = data[0].split()[-min(limit, 50):][::-1]
            out = []
            for uid in uids:
                _, msg_data = m.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                hdr = email.message_from_bytes(msg_data[0][1])
                out.append({"uid": uid.decode(), "from": _dh(hdr["From"]), "subject": _dh(hdr["Subject"]),
                            "date": hdr["Date"]})
            return out
        finally:
            m.logout()

    @tool("UID ile bir e-postanın içeriğini okur.", {"uid": s("E-posta UID")}, ["uid"])
    def read_email(self, uid):
        m = self._imap()
        try:
            m.select("INBOX", readonly=True)
            _, data = m.uid("fetch", uid.encode(), "(BODY.PEEK[])")
            msg = email.message_from_bytes(data[0][1])
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                        break
            return {"from": _dh(msg["From"]), "to": _dh(msg["To"]), "subject": _dh(msg["Subject"]),
                    "date": msg["Date"], "message_id": msg["Message-ID"], "body": body[:15000],
                    "attachments": [p.get_filename() for p in msg.walk() if p.get_filename()]}
        finally:
            m.logout()

    @tool("SMTP ile e-posta gönderir.",
          {"to": s("Alıcı(lar), virgülle"), "subject": s("Konu"), "body": s("Metin"), "cc": s("CC"),
           "in_reply_to": s("Yanıtlanan Message-ID")}, ["to", "subject", "body"], write=True)
    def send_email(self, to, subject, body, cc="", in_reply_to=""):
        em = EmailMessage()
        user = self.secret("username")
        fn = self.secret("from_name")
        em["From"] = f"{fn} <{user}>" if fn else user
        em["To"] = to
        em["Subject"] = subject
        if cc:
            em["Cc"] = cc
        if in_reply_to:
            em["In-Reply-To"] = in_reply_to
            em["References"] = in_reply_to
        em.set_content(body)
        port = int(self.secret("smtp_port"))
        ctx = ssl.create_default_context()
        if port == 465:
            srv = smtplib.SMTP_SSL(self.secret("smtp_host"), port, context=ctx, timeout=30)
        else:
            srv = smtplib.SMTP(self.secret("smtp_host"), port, timeout=30)
            srv.starttls(context=ctx)
        with srv:
            srv.login(user, self.secret("password"))
            srv.send_message(em)
        return {"sent": True}


@register
class Slack(Connector):
    id = "slack"
    name = "Slack"
    category = "Ekip İletişimi"
    description = "Kanallara mesaj gönderin, kanal geçmişini okuyun."
    icon = "hash"
    color = "#4a154b"
    docs_url = "https://api.slack.com/apps"
    setup_steps = [
        "api.slack.com/apps → Create New App → From scratch.",
        "OAuth & Permissions → Bot Token Scopes: chat:write, channels:read, channels:history, groups:read, users:read.",
        "Install to Workspace → 'Bot User OAuth Token' (xoxb-...) değerini kopyalayın.",
        "Botu kullanılacak kanallara davet edin: /invite @botadı",
    ]
    fields = [Field("bot_token", "Bot Token", "password", placeholder="xoxb-...")]

    def api(self, method, **params):
        d = self.http("POST", f"https://slack.com/api/{method}",
                      headers={"Authorization": f"Bearer {self.secret('bot_token')}"}, json=params)
        if not d.get("ok"):
            raise ConnectorError(f"Slack hatası: {d.get('error')}")
        return d

    def test(self):
        d = self.api("auth.test")
        return f"Bağlandı: {d.get('team')} / {d.get('user')}"

    @tool("Slack kanallarını listeler.")
    def list_channels(self):
        d = self.api("conversations.list", limit=200, types="public_channel,private_channel")
        return [{"id": c["id"], "name": c["name"], "members": c.get("num_members")} for c in d.get("channels", [])]

    @tool("Kanala veya kişiye mesaj gönderir.",
          {"channel": s("Kanal ID'si veya #kanal-adı"), "text": s("Mesaj (Slack mrkdwn)"),
           "thread_ts": s("Konu yanıtı için ts")}, ["channel", "text"], write=True)
    def send_message(self, channel, text, thread_ts=""):
        p = {"channel": channel, "text": text}
        if thread_ts:
            p["thread_ts"] = thread_ts
        d = self.api("chat.postMessage", **p)
        return {"ts": d.get("ts"), "channel": d.get("channel")}

    @tool("Kanalın son mesajlarını okur.", {"channel": s("Kanal ID"), "limit": i("Adet")}, ["channel"])
    def read_channel(self, channel, limit=20):
        d = self.api("conversations.history", channel=channel, limit=min(limit, 100))
        return [{"ts": m.get("ts"), "user": m.get("user"), "text": m.get("text")} for m in d.get("messages", [])]


@register
class Telegram(Connector):
    id = "telegram"
    name = "Telegram Bot"
    category = "Ekip İletişimi"
    description = "Telegram botu üzerinden bildirim ve mesaj gönderin, gelen mesajları okuyun."
    icon = "send"
    color = "#229ed9"
    docs_url = "https://core.telegram.org/bots/api"
    setup_steps = [
        "Telegram'da @BotFather ile konuşun → /newbot → bot token'ını alın.",
        "Botunuza bir mesaj gönderin, ardından 'Son mesajları getir' aracıyla chat_id öğrenebilirsiniz.",
    ]
    fields = [
        Field("bot_token", "Bot Token", "password", placeholder="123456:ABC-..."),
        Field("default_chat_id", "Varsayılan Chat ID", required=False, help="Bildirimlerin gideceği sohbet"),
    ]

    def api(self, method, **params):
        d = self.http("POST", f"https://api.telegram.org/bot{self.secret('bot_token')}/{method}", json=params)
        if not d.get("ok"):
            raise ConnectorError(str(d.get("description")))
        return d["result"]

    def test(self):
        me = self.api("getMe")
        return f"Bağlandı: @{me.get('username')}"

    @tool("Telegram mesajı gönderir.", {"text": s("Mesaj (HTML biçimlendirme desteklenir)"),
                                        "chat_id": s("Chat ID (boşsa varsayılan)")}, ["text"], write=True)
    def send_message(self, text, chat_id=""):
        cid = chat_id or self.secret("default_chat_id")
        if not cid:
            raise ConnectorError("chat_id gerekli.")
        r = self.api("sendMessage", chat_id=cid, text=text, parse_mode="HTML")
        return {"message_id": r.get("message_id")}

    @tool("Bota gelen son mesajları getirir.", {"limit": i("Adet")})
    def get_updates(self, limit=20):
        res = self.api("getUpdates", limit=min(limit, 100))
        out = []
        for u in res:
            m = u.get("message") or u.get("channel_post") or {}
            out.append({"chat_id": m.get("chat", {}).get("id"), "from": m.get("from", {}).get("username"),
                        "text": m.get("text"), "date": m.get("date")})
        return out


@register
class WhatsApp(Connector):
    id = "whatsapp"
    name = "WhatsApp Business"
    category = "Müşteri İletişimi"
    description = "WhatsApp Cloud API ile müşterilere mesaj ve şablon gönderin."
    icon = "message-circle"
    color = "#25d366"
    docs_url = "https://developers.facebook.com/docs/whatsapp/cloud-api"
    setup_steps = [
        "developers.facebook.com → uygulama oluşturun → WhatsApp ürününü ekleyin.",
        "WhatsApp → API Setup sayfasından Phone Number ID değerini alın.",
        "Kalıcı erişim için Business Settings → System Users → token oluşturun (whatsapp_business_messaging izni).",
        "Not: 24 saat penceresi dışında yalnızca onaylı şablon mesajları gönderilebilir.",
    ]
    fields = [
        Field("phone_number_id", "Phone Number ID"),
        Field("access_token", "Access Token", "password"),
        Field("api_version", "API sürümü", default="v21.0", required=False),
    ]

    def url(self, path=""):
        return f"https://graph.facebook.com/{self.secret('api_version')}/{self.secret('phone_number_id')}{path}"

    def h(self):
        return {"Authorization": f"Bearer {self.secret('access_token')}"}

    def test(self):
        d = self.http("GET", self.url(), headers=self.h())
        return f"Bağlandı: {d.get('display_phone_number')} ({d.get('verified_name')})"

    @tool("WhatsApp metin mesajı gönderir (müşteri son 24 saatte yazmış olmalı).",
          {"to": s("Alıcı telefon (uluslararası, ör. 905551112233)"), "text": s("Mesaj")}, ["to", "text"], write=True)
    def send_text(self, to, text):
        d = self.http("POST", self.url("/messages"), headers=self.h(), json={
            "messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text}})
        return {"message_id": (d.get("messages") or [{}])[0].get("id")}

    @tool("Onaylı WhatsApp şablon mesajı gönderir.",
          {"to": s("Alıcı telefon"), "template_name": s("Şablon adı"), "language": s("Dil kodu (ör. tr)"),
           "parameters": arr("Gövde parametreleri sırasıyla", s("değer"))}, ["to", "template_name"], write=True)
    def send_template(self, to, template_name, language="tr", parameters=None):
        tpl = {"name": template_name, "language": {"code": language}}
        if parameters:
            tpl["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}]
        d = self.http("POST", self.url("/messages"), headers=self.h(), json={
            "messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template", "template": tpl})
        return {"message_id": (d.get("messages") or [{}])[0].get("id")}


@register
class TwilioSMS(Connector):
    id = "twilio_sms"
    name = "Twilio SMS"
    category = "Müşteri İletişimi"
    description = "Müşterilere SMS gönderin ve gönderim geçmişini görün."
    icon = "smartphone"
    color = "#f22f46"
    docs_url = "https://www.twilio.com/docs/sms"
    setup_steps = ["console.twilio.com → Account SID ve Auth Token değerlerini kopyalayın.",
                   "Phone Numbers bölümünden SMS gönderebilen bir numara alın."]
    fields = [
        Field("account_sid", "Account SID"),
        Field("auth_token", "Auth Token", "password"),
        Field("from_number", "Gönderen numara", placeholder="+1..."),
    ]

    def base(self):
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.secret('account_sid')}"

    def auth(self):
        return (self.secret("account_sid"), self.secret("auth_token"))

    def test(self):
        d = self.http("GET", self.base() + ".json", auth=self.auth())
        return f"Bağlandı: {d.get('friendly_name')} ({d.get('status')})"

    @tool("SMS gönderir.", {"to": s("Alıcı (+90...)"), "body": s("Mesaj")}, ["to", "body"], write=True)
    def send_sms(self, to, body):
        d = self.http("POST", self.base() + "/Messages.json", auth=self.auth(),
                      data={"To": to, "From": self.secret("from_number"), "Body": body})
        return {"sid": d.get("sid"), "status": d.get("status")}

    @tool("Son SMS'leri listeler.", {"limit": i("Adet")})
    def list_messages(self, limit=20):
        d = self.http("GET", self.base() + "/Messages.json", auth=self.auth(), params={"PageSize": min(limit, 100)})
        return [{"to": m["to"], "from": m["from"], "body": m["body"], "status": m["status"],
                 "date": m["date_sent"]} for m in d.get("messages", [])]
