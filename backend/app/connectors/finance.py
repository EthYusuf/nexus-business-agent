"""Finans & muhasebe: Paraşüt (fatura / e-Arşiv / e-Fatura), Stripe."""
from __future__ import annotations

import datetime as dt

from .base import Connector, ConnectorError, Field, arr, cached_token, i, n, register, s, tool


@register
class Parasut(Connector):
    id = "parasut"
    name = "Paraşüt (Fatura & Muhasebe)"
    category = "Finans & Muhasebe"
    description = "Müşteri/ürün yönetimi, satış faturası kesme, e-Arşiv / e-Fatura gönderimi ve tahsilat."
    icon = "receipt"
    color = "#ff6b00"
    docs_url = "https://apidocs.parasut.com"
    setup_steps = [
        "Paraşüt destek ekibinden API erişimi (client_id / client_secret) talep edin.",
        "Firma ID: Paraşüt'e giriş yaptığınızda adres çubuğundaki uygulama.parasut.com/<FIRMA_ID>/ değeridir.",
        "Kullanıcı adı ve şifre Paraşüt hesabınızın giriş bilgileridir (yalnızca bu bilgisayarda şifreli saklanır).",
    ]
    fields = [
        Field("company_id", "Firma ID"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client Secret", "password"),
        Field("username", "Kullanıcı e-postası"),
        Field("password", "Şifre", "password"),
    ]
    BASE = "https://api.parasut.com"

    def token(self):
        def fetch():
            d = self.http("POST", f"{self.BASE}/oauth/token", data={
                "grant_type": "password", "client_id": self.secret("client_id"),
                "client_secret": self.secret("client_secret"), "username": self.secret("username"),
                "password": self.secret("password"), "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"})
            if "access_token" not in d:
                raise ConnectorError(str(d))
            return d["access_token"], d.get("expires_in", 7200)
        return cached_token("parasut:" + self.secret("username") + self.secret("company_id"), fetch)

    def r(self, method, path, **kw):
        return self.http(method, f"{self.BASE}/v4/{self.secret('company_id')}{path}", headers={
            "Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}, **kw)

    @staticmethod
    def _flat(item):
        return {"id": item.get("id"), "type": item.get("type"), **(item.get("attributes") or {})}

    def test(self):
        self.r("GET", "/contacts", params={"page[size]": 1})
        return "Paraşüt bağlantısı başarılı."

    @tool("Müşteri/tedarikçi carilerini arar.", {"name": s("Ad/ünvan içinde geçen"), "tax_number": s("VKN/TCKN"),
                                                  "email": s("E-posta")})
    def search_contacts(self, name="", tax_number="", email=""):
        p = {"page[size]": 25}
        if name:
            p["filter[name]"] = name
        if tax_number:
            p["filter[tax_number]"] = tax_number
        if email:
            p["filter[email]"] = email
        d = self.r("GET", "/contacts", params=p)
        keep = ("id", "name", "email", "tax_number", "tax_office", "city", "phone", "balance", "account_type")
        return [{k: v for k, v in self._flat(c).items() if k in keep} for c in d.get("data", [])]

    @tool("Yeni müşteri (cari) oluşturur.",
          {"name": s("Ad / ünvan"), "contact_type": s("company veya person"), "email": s("E-posta"),
           "tax_number": s("VKN veya TCKN"), "tax_office": s("Vergi dairesi"), "city": s("İl"),
           "district": s("İlçe"), "address": s("Adres"), "phone": s("Telefon")}, ["name"], write=True)
    def create_contact(self, name, contact_type="company", email="", tax_number="", tax_office="",
                       city="", district="", address="", phone=""):
        attrs = {k: v for k, v in dict(name=name, contact_type=contact_type, email=email, tax_number=tax_number,
                                       tax_office=tax_office, city=city, district=district, address=address,
                                       phone=phone, account_type="customer").items() if v}
        d = self.r("POST", "/contacts", json={"data": {"type": "contacts", "attributes": attrs}})
        return self._flat(d["data"])

    @tool("Ürün/hizmet kartlarını listeler.", {"name": s("Ad filtresi")})
    def list_products(self, name=""):
        p = {"page[size]": 50}
        if name:
            p["filter[name]"] = name
        d = self.r("GET", "/products", params=p)
        keep = ("id", "name", "code", "list_price", "currency", "vat_rate", "unit", "stock_count")
        return [{k: v for k, v in self._flat(x).items() if k in keep} for x in d.get("data", [])]

    @tool("Son satış faturalarını listeler.", {"status": s("paid, overdue, unpaid (isteğe bağlı)"),
                                                "limit": i("Adet")})
    def list_invoices(self, status="", limit=20):
        p = {"page[size]": min(limit, 50), "sort": "-issue_date", "include": "contact"}
        if status == "unpaid":
            p["filter[remaining]"] = "positive"
        d = self.r("GET", "/sales_invoices", params=p)
        contacts = {c["id"]: c["attributes"].get("name") for c in d.get("included", []) if c["type"] == "contacts"}
        out = []
        for inv in d.get("data", []):
            a = inv["attributes"]
            cid = (((inv.get("relationships") or {}).get("contact") or {}).get("data") or {}).get("id")
            row = {"id": inv["id"], "no": a.get("invoice_no"), "date": a.get("issue_date"),
                   "due": a.get("due_date"), "customer": contacts.get(cid), "total": a.get("gross_total"),
                   "remaining": a.get("remaining"), "currency": a.get("currency"),
                   "status": a.get("payment_status"), "description": a.get("description")}
            if status in ("paid", "overdue") and row["status"] != status:
                continue
            out.append(row)
        return out

    @tool("Satış faturası (taslak/resmi) oluşturur. Kalemlerde KDV oranı yüzde olarak girilir (ör. 20). "
          "e-Arşiv/e-Fatura olarak göndermek için ardından send_e_invoice aracını kullanın.",
          {"contact_id": s("Cari ID"), "description": s("Fatura açıklaması"),
           "issue_date": s("Düzenleme tarihi YYYY-AA-GG (varsayılan bugün)"),
           "due_date": s("Vade tarihi YYYY-AA-GG"), "currency": s("TRL, USD, EUR, GBP"),
           "items": arr("Fatura kalemleri", {"type": "object", "properties": {
               "description": s("Kalem açıklaması"), "quantity": n("Miktar"), "unit_price": n("Birim fiyat (KDV hariç)"),
               "vat_rate": n("KDV %"), "product_id": s("Ürün ID (isteğe bağlı)")},
               "required": ["description", "quantity", "unit_price"]})},
          ["contact_id", "items"], write=True)
    def create_sales_invoice(self, contact_id, items, description="", issue_date="", due_date="", currency="TRL"):
        today = dt.date.today().isoformat()
        details = []
        for it in items:
            det = {"type": "sales_invoice_details", "attributes": {
                "quantity": it.get("quantity", 1), "unit_price": it["unit_price"],
                "vat_rate": it.get("vat_rate", 20), "description": it.get("description", "")}}
            if it.get("product_id"):
                det["relationships"] = {"product": {"data": {"id": it["product_id"], "type": "products"}}}
            details.append(det)
        body = {"data": {"type": "sales_invoices", "attributes": {
            "item_type": "invoice", "description": description, "issue_date": issue_date or today,
            "due_date": due_date or issue_date or today, "currency": currency},
            "relationships": {"contact": {"data": {"id": contact_id, "type": "contacts"}},
                              "details": {"data": details}}}}
        d = self.r("POST", "/sales_invoices", json=body)
        a = d["data"]["attributes"]
        return {"id": d["data"]["id"], "net_total": a.get("net_total"), "gross_total": a.get("gross_total"),
                "currency": a.get("currency"), "issue_date": a.get("issue_date")}

    @tool("Faturayı resmileştirir: alıcı e-Fatura mükellefi ise e-Fatura, değilse e-Arşiv olarak gönderir.",
          {"invoice_id": s("Satış faturası ID"), "tax_number": s("Alıcının VKN/TCKN'si (mükellef kontrolü için)")},
          ["invoice_id"], write=True)
    def send_e_invoice(self, invoice_id, tax_number=""):
        inbox = None
        if tax_number:
            res = self.r("GET", "/e_invoice_inboxes", params={"filter[vkn]": tax_number})
            if res.get("data"):
                inbox = res["data"][0]["attributes"].get("e_invoice_address")
        rel = {"invoice": {"data": {"id": invoice_id, "type": "sales_invoices"}}}
        if inbox:
            d = self.r("POST", "/e_invoices", json={"data": {"type": "e_invoices", "attributes": {
                "scenario": "commercial", "to": inbox}, "relationships": rel}})
            kind = "e-Fatura"
        else:
            d = self.r("POST", "/e_archives", json={"data": {"type": "e_archives", "relationships": {
                "sales_invoice": {"data": {"id": invoice_id, "type": "sales_invoices"}}}}})
            kind = "e-Arşiv"
        return {"type": kind, "job": d.get("data", {}).get("id"),
                "status": d.get("data", {}).get("attributes", {}).get("status"),
                "note": "Gönderim Paraşüt tarafında arka planda işlenir."}

    @tool("Faturaya tahsilat (ödeme) kaydeder.",
          {"invoice_id": s("Fatura ID"), "account_id": s("Kasa/banka hesap ID (list_accounts ile)"),
           "amount": n("Tutar"), "date": s("Tarih YYYY-AA-GG")}, ["invoice_id", "account_id", "amount"], write=True)
    def record_payment(self, invoice_id, account_id, amount, date=""):
        d = self.r("POST", f"/sales_invoices/{invoice_id}/payments", json={"data": {"type": "payments", "attributes": {
            "account_id": account_id, "amount": amount, "date": date or dt.date.today().isoformat()}}})
        return {"ok": True, "payment": d.get("data", {}).get("id")}

    @tool("Kasa ve banka hesaplarını bakiyeleriyle listeler.")
    def list_accounts(self):
        d = self.r("GET", "/accounts", params={"page[size]": 50})
        keep = ("id", "name", "currency", "balance", "account_type", "bank_name", "iban")
        return [{k: v for k, v in self._flat(x).items() if k in keep} for x in d.get("data", [])]


@register
class Stripe(Connector):
    id = "stripe"
    name = "Stripe"
    category = "Finans & Muhasebe"
    description = "Ödemeleri, müşterileri ve bakiyeyi görün; online fatura gönderin."
    icon = "credit-card"
    color = "#635bff"
    docs_url = "https://docs.stripe.com/api"
    setup_steps = ["dashboard.stripe.com/apikeys → Secret key (veya kısıtlı 'Restricted key') oluşturun.",
                   "Test için sk_test_ ile başlayan anahtarı kullanabilirsiniz."]
    fields = [Field("secret_key", "Secret Key", "password", placeholder="sk_live_... / sk_test_...")]
    API = "https://api.stripe.com/v1"

    def r(self, method, path, **kw):
        return self.http(method, self.API + path, auth=(self.secret("secret_key"), ""), **kw)

    def test(self):
        b = self.r("GET", "/balance")
        return "Bağlandı. Mod: " + ("canlı" if b.get("livemode") else "test")

    @tool("Hesap bakiyesini getirir.")
    def get_balance(self):
        b = self.r("GET", "/balance")
        fmt = lambda xs: [{"amount": x["amount"] / 100, "currency": x["currency"]} for x in xs]
        return {"available": fmt(b.get("available", [])), "pending": fmt(b.get("pending", []))}

    @tool("Son ödemeleri listeler.", {"limit": i("Adet")})
    def list_payments(self, limit=20):
        d = self.r("GET", "/payment_intents", params={"limit": min(limit, 100)})
        return [{"id": p["id"], "amount": p["amount"] / 100, "currency": p["currency"], "status": p["status"],
                 "customer": p.get("customer"), "description": p.get("description"),
                 "created": dt.datetime.fromtimestamp(p["created"]).isoformat()} for p in d.get("data", [])]

    @tool("Müşterileri listeler/arar.", {"email": s("E-posta filtresi"), "limit": i("Adet")})
    def list_customers(self, email="", limit=20):
        p = {"limit": min(limit, 100)}
        if email:
            p["email"] = email
        d = self.r("GET", "/customers", params=p)
        return [{"id": c["id"], "name": c.get("name"), "email": c.get("email")} for c in d.get("data", [])]

    @tool("Yeni müşteri oluşturur.", {"name": s("Ad"), "email": s("E-posta")}, ["email"], write=True)
    def create_customer(self, email, name=""):
        c = self.r("POST", "/customers", data={"email": email, "name": name})
        return {"id": c["id"]}

    @tool("Müşteriye ödeme bağlantılı fatura oluşturup e-postayla gönderir.",
          {"customer_id": s("Stripe müşteri ID"), "currency": s("para birimi, ör. try, usd, eur"),
           "days_until_due": i("Vade (gün)"),
           "items": arr("Kalemler", {"type": "object", "properties": {
               "description": s("Açıklama"), "amount": n("Tutar (ana birim, ör. 150.50)")},
               "required": ["description", "amount"]})},
          ["customer_id", "items"], write=True)
    def create_invoice(self, customer_id, items, currency="try", days_until_due=7):
        inv = self.r("POST", "/invoices", data={"customer": customer_id, "collection_method": "send_invoice",
                                               "days_until_due": days_until_due, "currency": currency})
        for it in items:
            self.r("POST", "/invoiceitems", data={"customer": customer_id, "invoice": inv["id"],
                                                  "amount": int(round(float(it["amount"]) * 100)),
                                                  "currency": currency, "description": it["description"]})
        self.r("POST", f"/invoices/{inv['id']}/finalize")
        sent = self.r("POST", f"/invoices/{inv['id']}/send")
        return {"id": inv["id"], "url": sent.get("hosted_invoice_url"), "total": (sent.get("total") or 0) / 100}
