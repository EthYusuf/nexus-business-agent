import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentT, api, ConversationT, EventT, prettyTool, timeAgo } from "../api";
import { useApp } from "../App";
import ApprovalCard, { ParamView } from "../components/ApprovalCard";
import { Badge, ConnectorLogo, Icon, toast } from "../ui";

const SUGGESTIONS: Record<string, string[]> = {
  a_inbox: ["Bugün gelen okunmamış e-postaları önceliklendir ve özetle", "Yarın 14:00'te ekip toplantısı ayarla ve davet gönder"],
  a_finance: ["Vadesi geçmiş faturaları listele ve hatırlatma e-postası taslağı hazırla", "ABC Ltd. için 3 adet danışmanlık hizmeti (5.000 TL + KDV) faturası kes"],
  a_commerce: ["Trendyol'da bekleyen siparişleri ve yanıtlanmamış müşteri sorularını özetle", "Stoğu 5'in altına düşen ürünleri raporla"],
  a_sales: ["Yeni müşteri adaylarını CRM'e ekle ve takip e-postası yaz", "Açık satış fırsatlarını aşamalarına göre özetle"],
  a_pm: ["Bu haftaki Jira ve Trello görevlerinden durum raporu hazırla ve Slack'e gönder"],
  a_research: ["Türkiye'de e-fatura entegratörlerini karşılaştıran bir rapor hazırla ve kaydet"],
  default: ["Bugün neler yapmam gerekiyor? E-posta, takvim ve siparişlerimi kontrol et", "Haftalık iş özetimi çıkar ve rapor olarak kaydet"],
};

export default function Chat({ convId }: { convId: string }) {
  const { agents, go } = useApp();
  const [convs, setConvs] = useState<ConversationT[]>([]);
  const [filter, setFilter] = useState("");
  const isNew = !convId || convId.startsWith("new");
  const presetAgent = convId?.startsWith("new:") ? convId.slice(4) : "";

  const loadList = useCallback(() => api.conversations().then(setConvs), []);
  useEffect(() => { loadList(); const t = setInterval(loadList, 5000); return () => clearInterval(t); }, [loadList]);

  const shown = convs.filter((c) => !filter || c.agent_id === filter);

  return (
    <div className="chat-layout">
      <div className="chat-list">
        <div className="chat-list-head">
          <button className="btn primary block" onClick={() => go("chat/new")}><Icon name="plus" size={16} /> Yeni görev</button>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">Tüm ajanlar</option>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div className="chat-items">
          {shown.length === 0 && <p className="muted small pad">Henüz sohbet yok.</p>}
          {shown.map((c) => {
            const a = agents.find((x) => x.id === c.agent_id);
            return (
              <a key={c.id} href={`#/chat/${c.id}`} className={`chat-item ${c.id === convId ? "active" : ""}`}>
                <span className="agent-avatar sm" style={{ background: a?.color || "#888" }}><Icon name={a?.icon || "bot"} size={13} /></span>
                <div className="grow min0">
                  <div className="ellipsis">{c.title}</div>
                  <div className="muted small">{a?.name} · {timeAgo(c.updated_at)}</div>
                </div>
                <StatusDot status={c.status} />
              </a>
            );
          })}
        </div>
      </div>
      {isNew ? <NewChat agents={agents} preset={presetAgent} onCreated={(id) => { loadList(); go(`chat/${id}`); }} />
        : <Conversation key={convId} id={convId} onChange={loadList} />}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    running: ["run", "Çalışıyor"], awaiting_approval: ["warn", "Onay bekliyor"], error: ["err", "Hata"], idle: ["", ""],
  };
  const [cls, title] = map[status] || ["", ""];
  return cls ? <span className={`dot ${cls}`} title={title} /> : null;
}

function NewChat({ agents, preset, onCreated }: { agents: AgentT[]; preset: string; onCreated: (id: string) => void }) {
  const [agentId, setAgentId] = useState(preset || agents[0]?.id || "");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!agentId && agents[0]) setAgentId(agents[0].id); }, [agents, agentId]);
  useEffect(() => { if (preset) setAgentId(preset); }, [preset]);
  const agent = agents.find((a) => a.id === agentId);

  const start = async (msg: string) => {
    if (!msg.trim() || !agentId) return;
    setBusy(true);
    try {
      const c = await api.createConversation(agentId, msg);
      onCreated(c.id);
    } catch (e) {
      toast((e as Error).message, "err");
      setBusy(false);
    }
  };

  return (
    <div className="chat-main">
      <div className="new-chat">
        <div className="new-chat-hero">
          <span className="agent-avatar lg" style={{ background: agent?.color }}><Icon name={agent?.icon || "bot"} size={26} /></span>
          <h2>{agent?.name || "Ajan seçin"}</h2>
          <p className="muted">{agent?.description}</p>
        </div>
        <div className="agent-picker">
          {agents.map((a) => (
            <button key={a.id} className={`agent-pick ${a.id === agentId ? "active" : ""}`} onClick={() => setAgentId(a.id)}>
              <span className="agent-avatar sm" style={{ background: a.color }}><Icon name={a.icon} size={13} /></span>
              {a.name}
            </button>
          ))}
        </div>
        <div className="suggestions">
          {(SUGGESTIONS[agentId] || SUGGESTIONS.default).map((s) => (
            <button key={s} className="suggestion" onClick={() => start(s)} disabled={busy}>
              <Icon name="sparkles" size={14} /> {s}
            </button>
          ))}
        </div>
        <Composer value={text} onChange={setText} onSend={() => start(text)} disabled={busy}
          placeholder={`${agent?.name || "Ajan"}'na bir görev verin…`} />
      </div>
    </div>
  );
}

type Item =
  | { type: "user" | "assistant" | "system" | "error"; ev: EventT }
  | { type: "tool"; call: EventT; result?: EventT; decision?: string };

function Conversation({ id, onChange }: { id: string; onChange: () => void }) {
  const { agents, connectors } = useApp();
  const [conv, setConv] = useState<ConversationT | null>(null);
  const [events, setEvents] = useState<EventT[]>([]);
  const [text, setText] = useState("");
  const lastId = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    try {
      const c = await api.conversation(id, lastId.current);
      if (c.events?.length) {
        lastId.current = c.events[c.events.length - 1].id;
        setEvents((e) => [...e, ...c.events!]);
      }
      setConv((prev) => {
        if (prev && prev.status !== c.status) onChange();
        return c;
      });
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }, [id, onChange]);

  useEffect(() => { lastId.current = 0; setEvents([]); poll(); }, [id, poll]);
  useEffect(() => {
    const t = setInterval(poll, conv?.status === "running" ? 900 : 3000);
    return () => clearInterval(t);
  }, [poll, conv?.status]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [events.length, conv?.status]);

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    const tools: Record<string, Item & { type: "tool" }> = {};
    for (const ev of events) {
      if (ev.kind === "tool_call") {
        const it = { type: "tool" as const, call: ev };
        tools[ev.payload.tool_use_id] = it;
        out.push(it);
      } else if (ev.kind === "tool_result" && tools[ev.payload.tool_use_id]) {
        tools[ev.payload.tool_use_id].result = ev;
      } else if (ev.kind === "approval" && tools[ev.payload.tool_use_id]) {
        tools[ev.payload.tool_use_id].decision = ev.payload.decision;
      } else if (["user", "assistant", "system", "error"].includes(ev.kind)) {
        if (ev.kind === "system" && ev.payload.text === "Onay bekleniyor.") continue;
        out.push({ type: ev.kind as "user", ev });
      }
    }
    return out;
  }, [events]);

  if (!conv) return <div className="chat-main"><div className="loading">Yükleniyor…</div></div>;
  const agent = agents.find((a) => a.id === conv.agent_id);
  const busy = conv.status === "running" || conv.status === "awaiting_approval";

  const send = async () => {
    if (!text.trim()) return;
    const t = text;
    setText("");
    try {
      await api.send(id, t);
      poll();
    } catch (e) {
      setText(t);
      toast((e as Error).message, "err");
    }
  };

  return (
    <div className="chat-main">
      <div className="chat-head">
        <span className="agent-avatar" style={{ background: agent?.color }}><Icon name={agent?.icon || "bot"} size={16} /></span>
        <div className="grow min0">
          <div className="ellipsis"><b>{conv.title}</b></div>
          <div className="muted small">{agent?.name} · {(conv.usage_in + conv.usage_out).toLocaleString("tr-TR")} token
            {conv.source === "automation" && " · otomasyon"}</div>
        </div>
        {busy && <button className="btn ghost sm" onClick={() => api.stop(id).then(poll)}><Icon name="square" size={14} /> Durdur</button>}
        <button className="icon-btn" title="Sil" onClick={async () => {
          if (!confirm("Bu sohbet silinsin mi?")) return;
          await api.deleteConversation(id);
          onChange();
          window.location.hash = "/chat";
        }}><Icon name="trash-2" size={16} /></button>
      </div>

      <div className="messages">
        {items.map((it, i) => {
          if (it.type === "tool") return <ToolCard key={i} item={it} connectors={connectors} />;
          const p = it.ev.payload;
          if (it.type === "user") return <div key={i} className="msg user"><div className="bubble">{p.text}</div></div>;
          if (it.type === "assistant") return (
            <div key={i} className="msg assistant">
              <span className="agent-avatar sm" style={{ background: agent?.color }}><Icon name={agent?.icon || "bot"} size={13} /></span>
              <div className="bubble md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{p.text}</ReactMarkdown></div>
            </div>
          );
          if (it.type === "error") return <div key={i} className="sys err"><Icon name="alert-triangle" size={14} /> {p.message}</div>;
          return <div key={i} className="sys"><Icon name="info" size={14} /> {p.text}</div>;
        })}
        {conv.status === "running" && (
          <div className="msg assistant">
            <span className="agent-avatar sm" style={{ background: agent?.color }}><Icon name={agent?.icon || "bot"} size={13} /></span>
            <div className="thinking"><span /><span /><span /> Çalışıyor…</div>
          </div>
        )}
        {conv.status === "awaiting_approval" && <ApprovalCard key={conv.updated_at} conv={conv} onDone={poll} />}
        {conv.status === "error" && conv.error && !events.some((e) => e.kind === "error" && e.payload.message === conv.error) && (
          <div className="sys err"><Icon name="alert-triangle" size={14} /> {conv.error}</div>
        )}
        <div ref={bottom} />
      </div>

      <div className="composer-wrap">
        <Composer value={text} onChange={setText} onSend={send} disabled={busy}
          placeholder={busy ? (conv.status === "awaiting_approval" ? "Önce yukarıdaki işlemi onaylayın veya reddedin" : "Ajan çalışıyor…") : "Mesaj yazın… (Shift+Enter yeni satır)"} />
      </div>
    </div>
  );
}

function ToolCard({ item, connectors }: { item: Item & { type: "tool" }; connectors: ReturnType<typeof useApp>["connectors"] }) {
  const [open, setOpen] = useState(false);
  const p = item.call.payload;
  const isServer = !!p.server;
  const t = isServer ? { connector: connectors.find((c) => c.id === "web"), name: "web araması" } : prettyTool(p.tool, connectors);
  const r = item.result?.payload;
  let state: [string, string, string];
  if (isServer) state = ["green", "Tamamlandı", "check"];
  else if (r) state = r.ok ? ["green", "Başarılı", "check"] : ["red", item.decision === "rejected" ? "Reddedildi" : "Hata", "x"];
  else if (p.needs_approval && !item.decision) state = ["amber", "Onay bekliyor", "shield-alert"];
  else state = ["blue", "Çalışıyor", "loader"];

  return (
    <div className="tool-card">
      <button className="tool-head" onClick={() => setOpen(!open)}>
        {t.connector ? <ConnectorLogo icon={t.connector.icon} color={t.connector.color} size={26} /> : <Icon name="wrench" />}
        <span className="cap"><b>{t.name}</b> <span className="muted small">· {t.connector?.name}</span></span>
        {item.decision === "approved" && <Badge tone="violet">Onaylandı</Badge>}
        <Badge tone={state[0]}><Icon name={state[2]} size={12} className={state[2] === "loader" ? "spin" : ""} /> {state[1]}</Badge>
        {r?.duration_ms > 0 && <span className="muted small">{(r.duration_ms / 1000).toFixed(1)} sn</span>}
        <Icon name={open ? "chevron-up" : "chevron-down"} size={16} className="ml-auto" />
      </button>
      {open && (
        <div className="tool-body">
          <div className="label">Parametreler</div>
          <ParamView value={p.input} />
          {r && <><div className="label">Sonuç</div><pre className="code">{r.result}</pre></>}
        </div>
      )}
    </div>
  );
}

function Composer({ value, onChange, onSend, disabled, placeholder }: {
  value: string; onChange: (v: string) => void; onSend: () => void; disabled?: boolean; placeholder?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (ref.current) { ref.current.style.height = "auto"; ref.current.style.height = Math.min(ref.current.scrollHeight, 220) + "px"; }
  }, [value]);
  return (
    <div className={`composer ${disabled ? "disabled" : ""}`}>
      <textarea ref={ref} rows={1} value={value} placeholder={placeholder} disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!disabled) onSend(); } }} />
      <button className="btn primary send" onClick={onSend} disabled={disabled || !value.trim()} aria-label="Gönder">
        <Icon name="arrow-up" size={18} />
      </button>
    </div>
  );
}
