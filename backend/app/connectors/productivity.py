"""Proje ve bilgi yönetimi: Notion, Trello, Jira, GitHub."""
from __future__ import annotations

from .base import Connector, Field, arr, i, register, s, tool


@register
class Notion(Connector):
    id = "notion"
    name = "Notion"
    category = "Proje & Bilgi"
    description = "Notion sayfa ve veritabanlarında arayın, kayıt ekleyin, not oluşturun."
    icon = "notebook"
    color = "#111111"
    docs_url = "https://developers.notion.com"
    setup_steps = [
        "notion.so/my-integrations → New integration → 'Internal Integration Secret' değerini alın.",
        "Erişilecek sayfa/veritabanını açın → ••• → Connections → entegrasyonunuzu ekleyin.",
    ]
    fields = [Field("token", "Integration Secret", "password", placeholder="ntn_...")]
    API = "https://api.notion.com/v1"

    def h(self):
        return {"Authorization": f"Bearer {self.secret('token')}", "Notion-Version": "2022-06-28"}

    def test(self):
        me = self.http("GET", f"{self.API}/users/me", headers=self.h())
        return f"Bağlandı: {me.get('name') or me.get('bot', {}).get('workspace_name')}"

    @staticmethod
    def _title(obj):
        props = obj.get("properties", {})
        for p in props.values():
            if p.get("type") == "title":
                return "".join(t.get("plain_text", "") for t in p.get("title", []))
        return "".join(t.get("plain_text", "") for t in obj.get("title", []))

    @tool("Notion'da sayfa ve veritabanı arar.", {"query": s("Arama metni"),
                                                   "only": s("page veya database (isteğe bağlı)")})
    def search(self, query="", only=""):
        body = {"query": query, "page_size": 20}
        if only in ("page", "database"):
            body["filter"] = {"property": "object", "value": only}
        d = self.http("POST", f"{self.API}/search", headers=self.h(), json=body)
        return [{"id": r["id"], "type": r["object"], "title": self._title(r), "url": r.get("url")}
                for r in d.get("results", [])]

    @tool("Bir Notion veritabanındaki kayıtları getirir. filter Notion API filtre nesnesidir (isteğe bağlı).",
          {"database_id": s("Veritabanı ID"), "filter": {"type": "object", "description": "Notion filtre nesnesi"}},
          ["database_id"])
    def query_database(self, database_id, filter=None):
        body = {"page_size": 50}
        if filter:
            body["filter"] = filter
        d = self.http("POST", f"{self.API}/databases/{database_id}/query", headers=self.h(), json=body)
        rows = []
        for r in d.get("results", []):
            row = {"id": r["id"], "url": r.get("url")}
            for k, p in r.get("properties", {}).items():
                t = p.get("type")
                v = p.get(t)
                if t in ("title", "rich_text"):
                    v = "".join(x.get("plain_text", "") for x in v or [])
                elif t in ("select", "status"):
                    v = (v or {}).get("name")
                elif t == "multi_select":
                    v = [x.get("name") for x in v or []]
                elif t == "date":
                    v = (v or {}).get("start")
                elif t == "people":
                    v = [x.get("name") for x in v or []]
                row[k] = v
            rows.append(row)
        return rows

    @tool("Bir üst sayfanın altına içerikli yeni sayfa oluşturur. İçerik satırları paragraf olarak eklenir; '# ' ile başlayanlar başlık olur.",
          {"parent_page_id": s("Üst sayfa ID"), "title": s("Başlık"), "content": s("Sayfa içeriği (çok satırlı)")},
          ["parent_page_id", "title"], write=True)
    def create_page(self, parent_page_id, title, content=""):
        children = []
        for line in content.splitlines():
            if not line.strip():
                continue
            kind = "heading_2" if line.startswith("# ") else "bulleted_list_item" if line.startswith("- ") else "paragraph"
            text = line[2:] if kind != "paragraph" else line
            children.append({"object": "block", "type": kind,
                             kind: {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}})
        d = self.http("POST", f"{self.API}/pages", headers=self.h(), json={
            "parent": {"page_id": parent_page_id},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
            "children": children[:100]})
        return {"id": d.get("id"), "url": d.get("url")}

    @tool("Veritabanına yeni kayıt ekler. properties Notion API özellik nesnesidir; örnek: "
          '{"Ad": {"title": [{"text": {"content": "Ali"}}]}, "Durum": {"select": {"name": "Yeni"}}}',
          {"database_id": s("Veritabanı ID"), "properties": {"type": "object", "description": "Notion özellikleri"}},
          ["database_id", "properties"], write=True)
    def add_database_item(self, database_id, properties):
        d = self.http("POST", f"{self.API}/pages", headers=self.h(),
                      json={"parent": {"database_id": database_id}, "properties": properties})
        return {"id": d.get("id"), "url": d.get("url")}


@register
class Trello(Connector):
    id = "trello"
    name = "Trello"
    category = "Proje & Bilgi"
    description = "Panoları, listeleri ve kartları yönetin; görev oluşturun ve taşıyın."
    icon = "trello"
    color = "#0079bf"
    docs_url = "https://developer.atlassian.com/cloud/trello/rest"
    setup_steps = ["trello.com/power-ups/admin → yeni Power-Up oluşturun → API Key alın.",
                   "API Key sayfasındaki 'Token' bağlantısı ile token üretin."]
    fields = [Field("api_key", "API Key"), Field("token", "Token", "password")]
    API = "https://api.trello.com/1"

    def q(self, **kw):
        return {"key": self.secret("api_key"), "token": self.secret("token"), **kw}

    def test(self):
        me = self.http("GET", f"{self.API}/members/me", params=self.q())
        return f"Bağlandı: {me.get('fullName')}"

    @tool("Panoları listeler.")
    def list_boards(self):
        d = self.http("GET", f"{self.API}/members/me/boards", params=self.q(filter="open", fields="name,url"))
        return [{"id": b["id"], "name": b["name"], "url": b["url"]} for b in d]

    @tool("Panodaki listeleri ve kartları getirir.", {"board_id": s("Pano ID")}, ["board_id"])
    def get_board(self, board_id):
        lists = self.http("GET", f"{self.API}/boards/{board_id}/lists",
                          params=self.q(cards="open", card_fields="name,desc,due,url,idMembers", fields="name"))
        return [{"list_id": l["id"], "list": l["name"],
                 "cards": [{"id": c["id"], "name": c["name"], "due": c.get("due"), "url": c.get("url")}
                           for c in l.get("cards", [])]} for l in lists]

    @tool("Yeni kart (görev) oluşturur.", {"list_id": s("Liste ID"), "name": s("Kart başlığı"),
                                           "desc": s("Açıklama"), "due": s("Son tarih ISO 8601")},
          ["list_id", "name"], write=True)
    def create_card(self, list_id, name, desc="", due=""):
        p = self.q(idList=list_id, name=name, desc=desc)
        if due:
            p["due"] = due
        c = self.http("POST", f"{self.API}/cards", params=p)
        return {"id": c["id"], "url": c.get("url")}

    @tool("Kartı başka listeye taşır.", {"card_id": s("Kart ID"), "list_id": s("Hedef liste ID")},
          ["card_id", "list_id"], write=True)
    def move_card(self, card_id, list_id):
        c = self.http("PUT", f"{self.API}/cards/{card_id}", params=self.q(idList=list_id))
        return {"id": c["id"], "list": c.get("idList")}

    @tool("Karta yorum ekler.", {"card_id": s("Kart ID"), "text": s("Yorum")}, ["card_id", "text"], write=True)
    def add_comment(self, card_id, text):
        self.http("POST", f"{self.API}/cards/{card_id}/actions/comments", params=self.q(text=text))
        return {"ok": True}


def _adf(text: str) -> dict:
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in (text or " ").splitlines() if line.strip()] or [{"type": "paragraph", "content": []}]}


@register
class Jira(Connector):
    id = "jira"
    name = "Jira"
    category = "Proje & Bilgi"
    description = "Jira kayıtlarını JQL ile arayın, yeni iş oluşturun, yorum ekleyin."
    icon = "kanban"
    color = "#0052cc"
    docs_url = "https://developer.atlassian.com/cloud/jira/platform/rest/v3"
    setup_steps = ["id.atlassian.com/manage-profile/security/api-tokens → API token oluşturun."]
    fields = [
        Field("base_url", "Site adresi", "url", placeholder="https://sirketiniz.atlassian.net"),
        Field("email", "E-posta"),
        Field("api_token", "API Token", "password"),
    ]

    def r(self, method, path, **kw):
        return self.http(method, self.secret("base_url").rstrip("/") + path,
                         auth=(self.secret("email"), self.secret("api_token")),
                         headers={"Accept": "application/json"}, **kw)

    def test(self):
        me = self.r("GET", "/rest/api/3/myself")
        return f"Bağlandı: {me.get('displayName')}"

    @tool("JQL ile Jira kayıtlarını arar (ör. 'project = ABC AND status != Done ORDER BY created DESC').",
          {"jql": s("JQL sorgusu"), "max_results": i("Adet")}, ["jql"])
    def search_issues(self, jql, max_results=20):
        d = self.r("GET", "/rest/api/3/search/jql", params={
            "jql": jql, "maxResults": min(max_results, 100),
            "fields": "summary,status,assignee,priority,created,duedate"})
        return [{"key": x["key"], "summary": x["fields"].get("summary"),
                 "status": (x["fields"].get("status") or {}).get("name"),
                 "assignee": (x["fields"].get("assignee") or {}).get("displayName"),
                 "priority": (x["fields"].get("priority") or {}).get("name"),
                 "due": x["fields"].get("duedate")} for x in d.get("issues", [])]

    @tool("Yeni Jira kaydı oluşturur.", {"project_key": s("Proje anahtarı"), "summary": s("Özet"),
                                          "description": s("Açıklama"), "issue_type": s("Tür (Task, Bug, Story)")},
          ["project_key", "summary"], write=True)
    def create_issue(self, project_key, summary, description="", issue_type="Task"):
        d = self.r("POST", "/rest/api/3/issue", json={"fields": {
            "project": {"key": project_key}, "summary": summary,
            "issuetype": {"name": issue_type}, "description": _adf(description)}})
        return {"key": d.get("key"), "url": self.secret("base_url").rstrip("/") + "/browse/" + str(d.get("key"))}

    @tool("Jira kaydına yorum ekler.", {"issue_key": s("Kayıt anahtarı"), "comment": s("Yorum")},
          ["issue_key", "comment"], write=True)
    def add_comment(self, issue_key, comment):
        self.r("POST", f"/rest/api/3/issue/{issue_key}/comment", json={"body": _adf(comment)})
        return {"ok": True}


@register
class GitHub(Connector):
    id = "github"
    name = "GitHub"
    category = "Proje & Bilgi"
    description = "Depolardaki issue ve pull request'leri takip edin, yeni issue açın."
    icon = "github"
    color = "#24292f"
    docs_url = "https://docs.github.com/rest"
    setup_steps = ["github.com/settings/personal-access-tokens → Fine-grained token (Issues: Read & Write)."]
    fields = [Field("token", "Personal Access Token", "password"),
              Field("default_repo", "Varsayılan depo", required=False, placeholder="sahip/depo")]
    API = "https://api.github.com"

    def r(self, method, path, **kw):
        return self.http(method, self.API + path, headers={
            "Authorization": f"Bearer {self.secret('token')}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}, **kw)

    def repo(self, repo):
        return repo or self.secret("default_repo") or "?"

    def test(self):
        return f"Bağlandı: {self.r('GET', '/user').get('login')}"

    @tool("Depodaki issue'ları listeler.", {"repo": s("sahip/depo"), "state": s("open, closed, all")})
    def list_issues(self, repo="", state="open"):
        d = self.r("GET", f"/repos/{self.repo(repo)}/issues", params={"state": state, "per_page": 30})
        return [{"number": x["number"], "title": x["title"], "state": x["state"], "pr": "pull_request" in x,
                 "user": x["user"]["login"], "url": x["html_url"]} for x in d]

    @tool("Yeni issue açar.", {"repo": s("sahip/depo"), "title": s("Başlık"), "body": s("Açıklama"),
                               "labels": arr("Etiketler", s("etiket"))}, ["title"], write=True)
    def create_issue(self, title, body="", repo="", labels=None):
        d = self.r("POST", f"/repos/{self.repo(repo)}/issues", json={"title": title, "body": body, "labels": labels or []})
        return {"number": d.get("number"), "url": d.get("html_url")}

    @tool("Issue veya PR'a yorum ekler.", {"repo": s("sahip/depo"), "number": i("Numara"), "body": s("Yorum")},
          ["number", "body"], write=True)
    def comment(self, number, body, repo=""):
        d = self.r("POST", f"/repos/{self.repo(repo)}/issues/{number}/comments", json={"body": body})
        return {"url": d.get("html_url")}
