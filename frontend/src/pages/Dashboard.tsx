import { useEffect, useState } from "react";
import { api, Dashboard as D, prettyTool, timeAgo } from "../api";
import { useApp } from "../App";
import { Badge, ConnectorLogo, Icon, PageHeader } from "../ui";

const DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

export default function Dashboard() {
  const { agents, connectors, go } = useApp();
  const [d, setD] = useState<D | null>(null);
  const [company, setCompany] = useState("");

  useEffect(() => {
    api.dashboard().then(setD);
    api.settings().then((s) => setCompany(s.company_name));
    const t = setInterval(() => api.dashboard().then(setD), 10000);
    return () => clearInterval(t);
  }, []);

  if (!d) return <div className="loading">Yükleniyor…</div>;

  const max = Math.max(1, ...d.activity_per_day);
  const labels = d.activity_per_day.map((_, i) => {
    const day = new Date(Date.now() - (6 - i) * 86400000);
    return DAYS[(day.getDay() + 6) % 7];
  });
  const steps = [
    { done: d.api_key_set, label: "Claude API anahtarını ekleyin", to: "settings" },
    { done: !!company, label: "Şirket profilinizi doldurun", to: "settings" },
    { done: d.connectors_active > 0, label: "İlk entegrasyonu bağlayın (ör. Gmail, Paraşüt)", to: "integrations" },
    { done: d.conversations > 0, label: "Bir ajana ilk görevinizi verin", to: "chat" },
  ];
  const doneCount = steps.filter((s) => s.done).length;

  return (
    <div className="page">
      <PageHeader title={company ? `Merhaba, ${company}` : "Genel Bakış"}
        subtitle="Tüm iş süreçleriniz ve yapay zeka ajanlarınız tek panelde."
        actions={<button className="btn primary" onClick={() => go("chat")}><Icon name="plus" size={16} /> Yeni görev</button>} />

      {doneCount < steps.length && (
        <div className="card setup">
          <div className="setup-head">
            <div>
              <h3>Kurulumu tamamlayın</h3>
              <p className="muted">{doneCount}/{steps.length} adım tamamlandı</p>
            </div>
            <div className="progress"><div style={{ width: `${(doneCount / steps.length) * 100}%` }} /></div>
          </div>
          <div className="setup-steps">
            {steps.map((s, i) => (
              <button key={i} className={`setup-step ${s.done ? "done" : ""}`} onClick={() => go(s.to)}>
                <span className="check">{s.done ? <Icon name="check" size={14} /> : i + 1}</span>
                {s.label}
                {!s.done && <Icon name="arrow-right" size={14} className="ml-auto" />}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="kpis">
        <Kpi icon="blocks" label="Aktif entegrasyon" value={`${d.connectors_active}`} sub={`${d.connectors_total} entegrasyondan`} onClick={() => go("integrations")} />
        <Kpi icon="bot" label="Ajanlar" value={`${d.agents}`} sub={`${d.conversations} görev / sohbet`} onClick={() => go("agents")} />
        <Kpi icon="shield-check" label="Onay bekleyen" value={`${d.pending_approvals}`} sub="işlem" tone={d.pending_approvals ? "warn" : undefined} onClick={() => go("approvals")} />
        <Kpi icon="zap" label="Son 7 gün işlem" value={`${d.actions_7d}`} sub={`%${d.success_rate} başarılı`} onClick={() => go("activity")} />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head"><h3>Ajan etkinliği</h3><span className="muted small">son 7 gün</span></div>
          <div className="bars">
            {d.activity_per_day.map((v, i) => (
              <div key={i} className="bar-col">
                <div className="bar-val">{v || ""}</div>
                <div className="bar" style={{ height: `${(v / max) * 100}%` }} />
                <div className="bar-label">{labels[i]}</div>
              </div>
            ))}
          </div>
          <div className="token-row muted small">
            <span>Girdi: {d.tokens_in.toLocaleString("tr-TR")} token</span>
            <span>Çıktı: {d.tokens_out.toLocaleString("tr-TR")} token</span>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>Son işlemler</h3><a className="link" href="#/activity">Tümü</a></div>
          {d.recent.length === 0 ? <p className="muted pad">Henüz ajan işlemi yok.</p> : (
            <ul className="feed">
              {d.recent.map((a) => {
                const t = prettyTool(a.tool, connectors);
                return (
                  <li key={a.id}>
                    {t.connector ? <ConnectorLogo icon={t.connector.icon} color={t.connector.color} size={30} /> : <Icon name="wrench" />}
                    <div className="feed-main">
                      <div className="feed-title">{t.name}</div>
                      <div className="muted small">{t.connector?.name} · {timeAgo(a.created_at)}</div>
                    </div>
                    <Badge tone={a.ok ? "green" : "red"}>{a.ok ? "Başarılı" : "Hata"}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-head"><h3>Ajanlarınız</h3><a className="link" href="#/agents">Yönet</a></div>
        <div className="agent-strip">
          {agents.map((a) => (
            <button key={a.id} className="agent-chip" onClick={() => go(`chat/new:${a.id}`)}>
              <span className="agent-avatar" style={{ background: a.color }}><Icon name={a.icon} size={16} /></span>
              <span>
                <b>{a.name}</b>
                <span className="muted small block">{a.connectors.length} entegrasyon</span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon, label, value, sub, tone, onClick }: {
  icon: string; label: string; value: string; sub: string; tone?: string; onClick?: () => void;
}) {
  return (
    <button className={`kpi ${tone ? "kpi-" + tone : ""}`} onClick={onClick}>
      <div className="kpi-icon"><Icon name={icon} size={18} /></div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="muted small">{sub}</div>
    </button>
  );
}
