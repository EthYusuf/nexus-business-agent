import { useState } from "react";
import { AgentT, api } from "../api";
import { useApp } from "../App";
import { Badge, ConnectorLogo, Icon, Modal, PageHeader, toast, Toggle } from "../ui";

const ICONS = ["bot", "sparkles", "mail", "receipt", "shopping-bag", "users", "kanban", "globe", "briefcase",
  "headphones", "megaphone", "calculator", "truck", "file-text", "brain", "rocket"];
const COLORS = ["#6366f1", "#ea4335", "#ff6b00", "#f27a1a", "#ff7a59", "#0052cc", "#0ea5e9", "#10b981", "#8b5cf6", "#e11d48", "#334155"];

const blank: Omit<AgentT, "id"> = {
  name: "", description: "", icon: "bot", color: "#6366f1", system_prompt: "", model: "", effort: "",
  connectors: [], auto_approve: false,
};

export default function Agents() {
  const { agents, connectors, reloadAgents, go } = useApp();
  const [edit, setEdit] = useState<(Omit<AgentT, "id"> & { id?: string }) | null>(null);

  return (
    <div className="page">
      <PageHeader title="Ajanlar" subtitle="Her biri belirli bir iş alanında uzmanlaşmış yapay zeka çalışanlarınız."
        actions={<button className="btn primary" onClick={() => setEdit({ ...blank })}><Icon name="plus" size={16} /> Yeni ajan</button>} />
      <div className="cards">
        {agents.map((a) => (
          <div key={a.id} className="card agent-card">
            <div className="row gap">
              <span className="agent-avatar lg" style={{ background: a.color }}><Icon name={a.icon} size={22} /></span>
              <div className="grow min0">
                <h3>{a.name}</h3>
                <div className="row gap-s wrap">
                  {a.auto_approve ? <Badge tone="amber">Otomatik onay</Badge> : <Badge tone="green">Onaylı çalışır</Badge>}
                  {a.model && <Badge>{a.model.replace("claude-", "")}</Badge>}
                </div>
              </div>
            </div>
            <p className="muted clamp-2">{a.description}</p>
            <div className="logo-row">
              {a.connectors.slice(0, 9).map((cid) => {
                const c = connectors.find((x) => x.id === cid);
                return c ? <span key={cid} title={c.name}><ConnectorLogo icon={c.icon} color={c.color} size={26} /></span> : null;
              })}
              {a.connectors.length > 9 && <span className="muted small">+{a.connectors.length - 9}</span>}
            </div>
            <div className="row gap mt-auto">
              <button className="btn primary grow" onClick={() => go(`chat/new:${a.id}`)}><Icon name="message-square" size={15} /> Görev ver</button>
              <button className="btn" onClick={() => setEdit({ ...a })}><Icon name="settings-2" size={15} /> Düzenle</button>
            </div>
          </div>
        ))}
      </div>
      {edit && <AgentEditor value={edit} onClose={() => setEdit(null)} onSaved={async () => { await reloadAgents(); setEdit(null); }} />}
    </div>
  );
}

function AgentEditor({ value, onClose, onSaved }: {
  value: Omit<AgentT, "id"> & { id?: string }; onClose: () => void; onSaved: () => void;
}) {
  const { connectors, meta } = useApp();
  const [a, setA] = useState(value);
  const set = <K extends keyof AgentT>(k: K, v: AgentT[K]) => setA({ ...a, [k]: v });
  const groups = connectors.reduce<Record<string, typeof connectors>>((g, c) => ((g[c.category] ||= []).push(c), g), {});

  const save = async () => {
    if (!a.name.trim()) return toast("Ajan adı gerekli.", "err");
    try {
      if (a.id) await api.updateAgent(a as AgentT); else await api.createAgent(a);
      toast("Ajan kaydedildi.");
      onSaved();
    } catch (e) { toast((e as Error).message, "err"); }
  };
  const remove = async () => {
    if (!a.id || !confirm(`"${a.name}" silinsin mi?`)) return;
    await api.deleteAgent(a.id);
    toast("Ajan silindi.");
    onSaved();
  };
  const toggleConn = (id: string) =>
    set("connectors", a.connectors.includes(id) ? a.connectors.filter((x) => x !== id) : [...a.connectors, id]);

  return (
    <Modal wide title={a.id ? "Ajanı düzenle" : "Yeni ajan"} onClose={onClose}
      footer={<>
        {a.id && <button className="btn danger-ghost" onClick={remove}><Icon name="trash-2" size={15} /> Sil</button>}
        <span className="grow" />
        <button className="btn" onClick={onClose}>Vazgeç</button>
        <button className="btn primary" onClick={save}>Kaydet</button>
      </>}>
      <div className="form-grid">
        <label>Ad<input value={a.name} onChange={(e) => set("name", e.target.value)} placeholder="ör. Müşteri Destek Ajanı" /></label>
        <label>Kısa açıklama<input value={a.description} onChange={(e) => set("description", e.target.value)} /></label>
      </div>
      <div className="form-grid">
        <div>
          <div className="label">Simge</div>
          <div className="icon-pick">
            {ICONS.map((ic) => (
              <button key={ic} className={a.icon === ic ? "active" : ""} onClick={() => set("icon", ic)}><Icon name={ic} size={16} /></button>
            ))}
          </div>
        </div>
        <div>
          <div className="label">Renk</div>
          <div className="color-pick">
            {COLORS.map((c) => <button key={c} style={{ background: c }} className={a.color === c ? "active" : ""} onClick={() => set("color", c)} />)}
          </div>
        </div>
      </div>
      <label>Talimatlar (sistem istemi)
        <textarea rows={6} value={a.system_prompt} onChange={(e) => set("system_prompt", e.target.value)}
          placeholder="Ajanın rolü, tonu, kuralları… ör. 'Sen bir müşteri destek uzmanısın. İade taleplerinde önce sipariş durumunu kontrol et…'" />
      </label>
      <div className="form-grid">
        <label>Model
          <select value={a.model} onChange={(e) => set("model", e.target.value)}>
            <option value="">Varsayılan (Ayarlar)</option>
            {meta?.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <label>Düşünme derinliği (effort)
          <select value={a.effort} onChange={(e) => set("effort", e.target.value)}>
            <option value="">Varsayılan (Ayarlar)</option>
            {meta?.efforts.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
      </div>
      <div className="card inset">
        <Toggle checked={a.auto_approve} onChange={(v) => set("auto_approve", v)}
          label={<span><b>Otomatik onay</b> <span className="muted small block">Açıkken ajan e-posta gönderme, fatura kesme gibi işlemleri onay beklemeden yapar. Yalnızca güvendiğiniz ajanlarda açın.</span></span>} />
      </div>
      <div className="label row">Erişebileceği entegrasyonlar <span className="muted small ml-s">({a.connectors.length} seçili)</span>
        <span className="grow" />
        <button className="link sm" onClick={() => set("connectors", connectors.map((c) => c.id))}>Tümü</button>
        <button className="link sm" onClick={() => set("connectors", [])}>Hiçbiri</button>
      </div>
      {Object.entries(groups).map(([g, list]) => (
        <div key={g} className="conn-group">
          <div className="muted small">{g}</div>
          <div className="conn-checks">
            {list.map((c) => (
              <button key={c.id} className={`conn-check ${a.connectors.includes(c.id) ? "on" : ""}`} onClick={() => toggleConn(c.id)}>
                <ConnectorLogo icon={c.icon} color={c.color} size={24} />
                <span className="grow ellipsis">{c.name}</span>
                {!(c.connected && c.enabled) && <span className="muted small">bağlı değil</span>}
                <Icon name={a.connectors.includes(c.id) ? "check-square" : "square"} size={16} />
              </button>
            ))}
          </div>
        </div>
      ))}
    </Modal>
  );
}
