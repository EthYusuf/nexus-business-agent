"""E-ticaret & CRM: Trendyol, Shopify, WooCommerce, HubSpot."""
from __future__ import annotations

import datetime as dt

from .base import Connector, Field, arr, i, n, register, s, tool


def _ms(ts):
    try:
        return dt.datetime.fromtimestamp(int(ts) / 1000).isoformat(timespec="minutes")
    except (TypeError, ValueError):
        return ts


@register
class Trendyol(Connector):
    id = "trendyol"
    name = "Trendyol Satıcı"
    category = "E-ticaret"
    description = "Siparişleri, ürünleri ve müşteri sorularını yönetin; stok ve fiyat güncelleyin."
    icon = "shopping-bag"
    color = "#f27a1a"
    docs_url = "https://developers.trendyol.com"
    setup_steps = ["Trendyol Satıcı Paneli → Hesabım → Entegrasyon Bilgileri → Satıcı ID, API Key ve API Secret."]
    fields = [
        Field("seller_id", "Satıcı ID"),
        Field("api_key", "API Key"),
        Field("api_secret", "API Secret", "password"),
        Field("environment", "Ortam", "select", required=False, default="prod", options=["prod", "stage"]),
    ]

    def base(self):
        host = "stageapigw" if self.secret("environment") == "stage" else "apigw"
        return f"https://{host}.trendyol.com/integration"

    def r(self, method, path, **kw):
        sid = self.secret("seller_id")
        return self.http(method, self.base() + path.format(sid=sid),
                         auth=(self.secret("api_key"), self.secret("api_secret")),
                         headers={"User-Agent": f"{sid} - SelfIntegration"}, **kw)

    def test(self):
        self.r("GET", "/order/sellers/{sid}/orders", params={"size": 1})
        return "Trendyol bağlantısı başarılı."

    @tool("Siparişleri listeler. status: Created, Picking, Invoiced, Shipped, Delivered, Cancelled, UnDelivered, Returned.",
          {"status": s("Sipariş durumu"), "days": i("Son kaç gün (varsayılan 7)"), "size": i("Adet")})
    def list_orders(self, status="", days=7, size=50):
        now = dt.datetime.now()
        p = {"size": min(size, 200), "orderByField": "PackageLastModifiedDate", "orderByDirection": "DESC",
             "startDate": int((now - dt.timedelta(days=days)).timestamp() * 1000), "endDate": int(now.timestamp() * 1000)}
        if status:
            p["status"] = status
        d = self.r("GET", "/order/sellers/{sid}/orders", params=p)
        return {"total": d.get("totalElements"), "orders": [{
            "order_number": o.get("orderNumber"), "package_id": o.get("id"), "status": o.get("status"),
            "date": _ms(o.get("orderDate")), "customer": f"{o.get('customerFirstName', '')} {o.get('customerLastName', '')}".strip(),
            "total": o.get("totalPrice"), "cargo": o.get("cargoProviderName"), "tracking": o.get("cargoTrackingNumber"),
            "lines": [{"product": l.get("productName"), "barcode": l.get("barcode"), "qty": l.get("quantity"),
                       "price": l.get("price")} for l in o.get("lines", [])]} for o in d.get("content", [])]}

    @tool("Ürünleri listeler.", {"barcode": s("Barkod filtresi"), "page": i("Sayfa (0'dan)"), "size": i("Adet")})
    def list_products(self, barcode="", page=0, size=50):
        p = {"page": page, "size": min(size, 100)}
        if barcode:
            p["barcode"] = barcode
        d = self.r("GET", "/product/sellers/{sid}/products", params=p)
        return {"total": d.get("totalElements"), "products": [{
            "title": x.get("title"), "barcode": x.get("barcode"), "stock": x.get("quantity"),
            "sale_price": x.get("salePrice"), "list_price": x.get("listPrice"), "approved": x.get("approved"),
            "on_sale": x.get("onSale")} for x in d.get("content", [])]}

    @tool("Stok ve/veya fiyat günceller.", {"items": arr("Güncellenecek ürünler", {"type": "object", "properties": {
        "barcode": s("Barkod"), "quantity": i("Stok"), "sale_price": n("Satış fiyatı"), "list_price": n("Liste fiyatı")},
        "required": ["barcode"]})}, ["items"], write=True)
    def update_stock_price(self, items):
        payload = []
        for it in items:
            row = {"barcode": it["barcode"]}
            if "quantity" in it:
                row["quantity"] = it["quantity"]
            if "sale_price" in it:
                row["salePrice"] = it["sale_price"]
            if "list_price" in it:
                row["listPrice"] = it["list_price"]
            payload.append(row)
        return self.r("POST", "/inventory/sellers/{sid}/products/price-and-inventory", json={"items": payload})

    @tool("Yanıt bekleyen müşteri sorularını getirir.", {"status": s("WAITING_FOR_ANSWER (varsayılan), ANSWERED")})
    def list_questions(self, status="WAITING_FOR_ANSWER"):
        d = self.r("GET", "/qna/sellers/{sid}/questions/filter", params={"status": status, "size": 50})
        return [{"id": q.get("id"), "product": q.get("productName"), "question": q.get("text"),
                 "customer": q.get("userName"), "date": _ms(q.get("creationDate"))} for q in d.get("content", [])]

    @tool("Müşteri sorusunu yanıtlar (en az 10 karakter).", {"question_id": s("Soru ID"), "text": s("Yanıt")},
          ["question_id", "text"], write=True)
    def answer_question(self, question_id, text):
        self.r("POST", "/qna/sellers/{sid}/questions/" + str(question_id) + "/answers", json={"text": text})
        return {"answered": True}


@register
class Shopify(Connector):
    id = "shopify"
    name = "Shopify"
    category = "E-ticaret"
    description = "Shopify mağazanızın siparişlerini, ürünlerini ve müşterilerini yönetin."
    icon = "store"
    color = "#95bf47"
    docs_url = "https://shopify.dev/docs/api/admin-rest"
    setup_steps = ["Shopify Admin → Settings → Apps and sales channels → Develop apps → Create an app.",
                   "Admin API scopes: read_orders, read_products, write_products, read_customers → Install → Admin API access token."]
    fields = [Field("shop", "Mağaza alan adı", placeholder="magazam.myshopify.com"),
              Field("access_token", "Admin API Access Token", "password", placeholder="shpat_...")]
    VERSION = "2024-10"

    def r(self, method, path, **kw):
        shop = self.secret("shop").replace("https://", "").strip("/")
        return self.http(method, f"https://{shop}/admin/api/{self.VERSION}{path}",
                         headers={"X-Shopify-Access-Token": self.secret("access_token")}, **kw)

    def test(self):
        return f"Bağlandı: {self.r('GET', '/shop.json').get('shop', {}).get('name')}"

    @tool("Siparişleri listeler.", {"status": s("open, closed, cancelled, any"),
                                     "financial_status": s("paid, pending, refunded vb."), "limit": i("Adet")})
    def list_orders(self, status="any", financial_status="", limit=25):
        p = {"status": status, "limit": min(limit, 250)}
        if financial_status:
            p["financial_status"] = financial_status
        d = self.r("GET", "/orders.json", params=p)
        return [{"id": o["id"], "name": o.get("name"), "date": o.get("created_at"), "total": o.get("total_price"),
                 "currency": o.get("currency"), "financial": o.get("financial_status"),
                 "fulfillment": o.get("fulfillment_status"), "email": o.get("email"),
                 "items": [f"{li['quantity']}x {li['title']}" for li in o.get("line_items", [])]}
                for o in d.get("orders", [])]

    @tool("Ürünleri ve stok durumlarını listeler.", {"limit": i("Adet")})
    def list_products(self, limit=50):
        d = self.r("GET", "/products.json", params={"limit": min(limit, 250)})
        return [{"id": p["id"], "title": p["title"], "status": p.get("status"),
                 "variants": [{"id": v["id"], "sku": v.get("sku"), "price": v.get("price"),
                               "stock": v.get("inventory_quantity")} for v in p.get("variants", [])]}
                for p in d.get("products", [])]

    @tool("Müşteri arar.", {"query": s("Ad, e-posta veya telefon")}, ["query"])
    def search_customers(self, query):
        d = self.r("GET", "/customers/search.json", params={"query": query})
        return [{"id": c["id"], "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                 "email": c.get("email"), "orders": c.get("orders_count"), "spent": c.get("total_spent")}
                for c in d.get("customers", [])]

    @tool("Ürün varyantının fiyatını günceller.", {"variant_id": s("Varyant ID"), "price": s("Yeni fiyat")},
          ["variant_id", "price"], write=True)
    def update_price(self, variant_id, price):
        d = self.r("PUT", f"/variants/{variant_id}.json", json={"variant": {"id": int(variant_id), "price": price}})
        return {"ok": True, "price": d.get("variant", {}).get("price")}


@register
class WooCommerce(Connector):
    id = "woocommerce"
    name = "WooCommerce"
    category = "E-ticaret"
    description = "WordPress/WooCommerce sitenizin sipariş, ürün ve stoklarını yönetin."
    icon = "shopping-cart"
    color = "#7f54b3"
    docs_url = "https://woocommerce.github.io/woocommerce-rest-api-docs"
    setup_steps = ["WooCommerce → Ayarlar → Gelişmiş → REST API → Anahtar ekle (Okuma/Yazma)."]
    fields = [Field("site_url", "Site adresi", "url", placeholder="https://magazam.com"),
              Field("consumer_key", "Consumer Key", placeholder="ck_..."),
              Field("consumer_secret", "Consumer Secret", "password", placeholder="cs_...")]

    def r(self, method, path, **kw):
        return self.http(method, self.secret("site_url").rstrip("/") + "/wp-json/wc/v3" + path,
                         auth=(self.secret("consumer_key"), self.secret("consumer_secret")), **kw)

    def test(self):
        d = self.r("GET", "/system_status")
        return f"Bağlandı: WooCommerce {d.get('environment', {}).get('version', '')}"

    @tool("Siparişleri listeler.", {"status": s("pending, processing, on-hold, completed, cancelled, refunded, any"),
                                     "limit": i("Adet")})
    def list_orders(self, status="any", limit=20):
        d = self.r("GET", "/orders", params={"status": status, "per_page": min(limit, 100)})
        return [{"id": o["id"], "status": o["status"], "date": o.get("date_created"), "total": o.get("total"),
                 "currency": o.get("currency"),
                 "customer": f"{o['billing'].get('first_name', '')} {o['billing'].get('last_name', '')}".strip(),
                 "email": o["billing"].get("email"), "phone": o["billing"].get("phone"),
                 "items": [f"{li['quantity']}x {li['name']}" for li in o.get("line_items", [])]} for o in d]

    @tool("Sipariş durumunu günceller.", {"order_id": i("Sipariş ID"), "status": s("Yeni durum"),
                                          "note": s("Müşteriye not (isteğe bağlı)")}, ["order_id", "status"], write=True)
    def update_order_status(self, order_id, status, note=""):
        o = self.r("PUT", f"/orders/{order_id}", json={"status": status})
        if note:
            self.r("POST", f"/orders/{order_id}/notes", json={"note": note, "customer_note": True})
        return {"id": o["id"], "status": o["status"]}

    @tool("Ürünleri listeler.", {"search": s("Arama"), "low_stock": i("Bu değerin altındaki stokları göster")})
    def list_products(self, search="", low_stock=None):
        p = {"per_page": 100}
        if search:
            p["search"] = search
        d = self.r("GET", "/products", params=p)
        out = [{"id": x["id"], "name": x["name"], "sku": x.get("sku"), "price": x.get("price"),
                "stock": x.get("stock_quantity"), "status": x.get("stock_status")} for x in d]
        if low_stock is not None:
            out = [x for x in out if x["stock"] is not None and x["stock"] < low_stock]
        return out

    @tool("Ürün stok/fiyat günceller.", {"product_id": i("Ürün ID"), "stock_quantity": i("Stok"),
                                          "regular_price": s("Fiyat")}, ["product_id"], write=True)
    def update_product(self, product_id, stock_quantity=None, regular_price=None):
        body = {}
        if stock_quantity is not None:
            body.update(manage_stock=True, stock_quantity=stock_quantity)
        if regular_price is not None:
            body["regular_price"] = str(regular_price)
        x = self.r("PUT", f"/products/{product_id}", json=body)
        return {"id": x["id"], "stock": x.get("stock_quantity"), "price": x.get("price")}


@register
class HubSpot(Connector):
    id = "hubspot"
    name = "HubSpot CRM"
    category = "Satış & CRM"
    description = "Müşteri adaylarını, kişileri ve satış fırsatlarını yönetin."
    icon = "users"
    color = "#ff7a59"
    docs_url = "https://developers.hubspot.com/docs/api/crm"
    setup_steps = ["HubSpot → Settings → Integrations → Private Apps → Create.",
                   "Scopes: crm.objects.contacts.read/write, crm.objects.deals.read/write → Access token."]
    fields = [Field("token", "Private App Token", "password", placeholder="pat-...")]
    API = "https://api.hubapi.com/crm/v3/objects"

    def r(self, method, path, **kw):
        return self.http(method, self.API + path, headers={"Authorization": f"Bearer {self.secret('token')}"}, **kw)

    def test(self):
        self.r("GET", "/contacts", params={"limit": 1})
        return "HubSpot bağlantısı başarılı."

    @tool("Kişi arar (ad, e-posta, şirket).", {"query": s("Arama metni")}, ["query"])
    def search_contacts(self, query):
        d = self.r("POST", "/contacts/search", json={
            "query": query, "limit": 20,
            "properties": ["firstname", "lastname", "email", "phone", "company", "lifecyclestage"]})
        return [{"id": c["id"], **c.get("properties", {})} for c in d.get("results", [])]

    @tool("Yeni kişi (müşteri adayı) oluşturur.", {"email": s("E-posta"), "firstname": s("Ad"), "lastname": s("Soyad"),
                                                   "phone": s("Telefon"), "company": s("Şirket")},
          ["email"], write=True)
    def create_contact(self, email, firstname="", lastname="", phone="", company=""):
        props = {k: v for k, v in dict(email=email, firstname=firstname, lastname=lastname,
                                       phone=phone, company=company).items() if v}
        d = self.r("POST", "/contacts", json={"properties": props})
        return {"id": d.get("id")}

    @tool("Satış fırsatlarını listeler.", {"limit": i("Adet")})
    def list_deals(self, limit=30):
        d = self.r("GET", "/deals", params={"limit": min(limit, 100),
                                            "properties": "dealname,amount,dealstage,closedate,pipeline"})
        return [{"id": x["id"], **x.get("properties", {})} for x in d.get("results", [])]

    @tool("Yeni satış fırsatı oluşturur.", {"dealname": s("Fırsat adı"), "amount": n("Tutar"),
                                            "dealstage": s("Aşama (ör. appointmentscheduled, closedwon)"),
                                            "closedate": s("Tahmini kapanış ISO tarih")}, ["dealname"], write=True)
    def create_deal(self, dealname, amount=None, dealstage="appointmentscheduled", closedate=""):
        props = {"dealname": dealname, "dealstage": dealstage, "pipeline": "default"}
        if amount is not None:
            props["amount"] = str(amount)
        if closedate:
            props["closedate"] = closedate
        d = self.r("POST", "/deals", json={"properties": props})
        return {"id": d.get("id")}
