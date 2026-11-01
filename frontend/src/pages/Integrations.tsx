import { useEffect, useMemo, useState } from "react";
import { api, ConnectorT } from "../api";
import { useApp } from "../App";
import { Badge, ConnectorLogo, Icon, Modal, PageHeader, toast, Toggle } from "../ui";

export default function Integrations({ focus }: { focus?: string }) {
  const { connectors, reloadConnectors } = useApp();
  const [cat, setCat] = useState("Tümü");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(focus || null);

  const cats = useMemo(() => ["Tümü", "Bağlı", ...Array.from(new Set(connectors.map((c) => c.category)))], [connectors]);
  const list = connectors.filter((c) =>
    (cat === "Tümü" || (cat === "Bağlı" ? c.connected && !c.builtin : c.category === cat)) &&
    (!q || (c.name + c.description).toLowerCase().includes(q.toLowerCase())));
  const current = connectors.find((c) => c.id === open);

  return (
    <div className="page">
      <PageHeader title="Entegrasyonlar"
        subtitle={`${connectors.length} entegrasyon · ${connectors.reduce((n, c) => n + c.tools.length, 0)} ajan aracı. Kimlik bilgileri bu bilgisayarda şifreli saklanır.`} />
      <div className="toolbar">
        <div className="tabs">
          {cats.map((c) => <button key={c} className={cat === c ? "active" : ""} onClick={() => setCat(c)}>{c}</button>)}
        </div>
        <div className="search"><Icon name="search" size={15} /><input placeholder="Ara…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      <div className="cards">
        {list.map((c) => (
          <button key={c.id} className="card conn-card" onClick={() => setOpen(c.id)}>
            <div className="row gap">
              <ConnectorLogo icon={c.icon} color={c.color} size={42} />
              <div className="grow min0 left">
                <h3 className="ellipsis">{c.name}</h3>
                <div className="muted small">{c.category}</div>
              </div>
              <StatusBadge c={c} />
            </div>
            <p className="muted left clamp-2">{c.description}</p>
            <div className="row gap-s muted small mt-auto">
              <Icon name="wrench" size={13} /> {c.tools.length} araç
              {c.tools.some((t) => t.write) && <><span>·</span><Icon name="shield-check" size={13} /> onaylı işlemler</>}
            </div>
          </button>
        ))}
      </div>
      {current && <ConnectorModal c={current} onClose={() => setOpen(null)} onChanged={reloadConnectors} />}
    </div>
  );
}

function StatusBadge({ c }: { c: ConnectorT }) {
  if (c.builtin) return <Badge tone="violet">Yerleşik</Badge>;
  if (!c.connected) return <Badge>Bağlı değil</Badge>;
  if (!c.enabled) return <Badge>Devre dışı</Badge>;
  if (c.status === "ok") return <Badge tone="green">Bağlı</Badge>;
  if (c.status === "error") return <Badge tone="red">Hata</Badge>;
  return <Badge tone="amber">Test edilmedi</Badge>;
}

function ConnectorModal({ c, onClose, onChanged }: { c: ConnectorT; onClose: () => void; onChanged: () => Promise<void> }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState(c.connected ? c.enabled : true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(
    c.status_message ? { ok: c.status === "ok", message: c.status_message } : null);

  useEffect(() => {
    setValues(Object.fromEntries(c.fields.map((f) => [f.key, c.values[f.key] || f.default || ""])));
  }, [c.id]); // eslint-disable-line

  const save = async (test: boolean) => {
    for (const f of c.fields) if (f.required && !values[f.key]?.trim()) return toast(`"${f.label}" gerekli.`, "err");
    setBusy(true);
    try {
      if (!c.builtin) await api.saveConnector(c.id, values, enabled);
      if (test) {
        const r = await api.testConnector(c.id);
        setResult(r);
        toast(r.ok ? "Bağlantı başarılı." : "Bağlantı testi başarısız.", r.ok ? "ok" : "err");
      } else toast("Kaydedildi.");
      await onChanged();
    } catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!confirm(`${c.name} bağlantısı ve kayıtlı kimlik bilgileri silinsin mi?`)) return;
    await api.deleteConnector(c.id);
    await onChanged();
    toast("Bağlantı kaldırıldı.");
    onClose();
  };

  return (
    <Modal wide onClose={onClose}
      title={<span className="row gap"><ConnectorLogo icon={c.icon} color={c.color} size={34} /> {c.name}</span>}
      subtitle={c.description}
      footer={<>
        {c.connected && !c.builtin && <button className="btn danger-ghost" onClick={remove}><Icon name="unplug" size={15} /> Bağlantıyı kaldır</button>}
        <span className="grow" />
        {!c.builtin && <button className="btn" disabled={busy} onClick={() => save(false)}>Kaydet</button>}
        <button className="btn primary" disabled={busy} onClick={() => save(true)}>
          <Icon name={busy ? "loader" : "plug-zap"} size={15} className={busy ? "spin" : ""} /> {c.builtin ? "Test et" : "Kaydet ve test et"}
        </button>
      </>}>
      <div className="split">
        <div>
          {c.setup_steps.length > 0 && (
            <div className="card inset">
              <div className="label">Kurulum adımları</div>
              <ol className="steps">{c.setup_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              {c.docs_url && <a className="link small" href={c.docs_url} target="_blank" rel="noreferrer">API dokümantasyonu <Icon name="external-link" size={12} /></a>}
            </div>
          )}
          {c.fields.map((f) => (
            <label key={f.key}><span>{f.label}{f.required && <span className="req">*</span>}</span>
              {f.type === "textarea" ? (
                <textarea rows={3} value={values[f.key] || ""} placeholder={f.placeholder}
                  onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
              ) : f.type === "select" ? (
                <select value={values[f.key] || f.default} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}>
                  {f.options.map((o) => <option key={o}>{o}</option>)}
                </select>
              ) : (
                <input type={f.type === "password" ? "password" : "text"} autoComplete="off" value={values[f.key] || ""}
                  placeholder={f.placeholder} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
              )}
              {f.help && <span className="muted small">{f.help}</span>}
            </label>
          ))}
          {!c.builtin && <Toggle checked={enabled} onChange={setEnabled} label="Ajanlar bu entegrasyonu kullanabilsin" />}
          {result && (
            <div className={`result ${result.ok ? "ok" : "err"}`}>
              <Icon name={result.ok ? "check-circle-2" : "alert-circle"} size={16} /> <span>{result.message}</span>
            </div>
          )}
        </div>
        <div>
          <div className="label">Ajanların kullanabileceği araçlar</div>
          <ul className="tool-list">
            {c.tools.map((t) => (
              <li key={t.name}>
                <div className="row gap-s">
                  <code>{t.name}</code>
                  {t.write ? <Badge tone="amber">Onay gerekir</Badge> : <Badge tone="green">Okuma</Badge>}
                </div>
                <div className="muted small">{t.description}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Modal>
  );
}
