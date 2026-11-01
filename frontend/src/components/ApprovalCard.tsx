import { useState } from "react";
import { api, ConversationT, prettyTool } from "../api";
import { useApp } from "../App";
import { ConnectorLogo, Icon, toast } from "../ui";

export default function ApprovalCard({ conv, onDone, compact }: { conv: ConversationT; onDone?: () => void; compact?: boolean }) {
  const { connectors } = useApp();
  const items = conv.pending.filter((p) => p.needs_approval);
  const [inputs, setInputs] = useState<Record<string, string>>(
    Object.fromEntries(items.map((p) => [p.id, JSON.stringify(p.input, null, 2)])));
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (approve: Record<string, boolean>) => {
    const decisions: Record<string, { approve: boolean; input?: unknown }> = {};
    try {
      for (const p of items) {
        decisions[p.id] = { approve: approve[p.id] };
        if (approve[p.id]) decisions[p.id].input = JSON.parse(inputs[p.id]);
      }
    } catch {
      toast("Düzenlenen parametreler geçerli JSON değil.", "err");
      return;
    }
    setBusy(true);
    try {
      await api.decide(conv.id, decisions);
      toast(Object.values(approve).some(Boolean) ? "Onaylandı, ajan devam ediyor." : "Reddedildi.");
      onDone?.();
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  };
  const all = (v: boolean) => Object.fromEntries(items.map((p) => [p.id, v]));

  return (
    <div className={`approval ${compact ? "compact" : ""}`}>
      <div className="approval-head">
        <Icon name="shield-alert" size={18} />
        <div>
          <b>Onayınız gerekiyor</b>
          <div className="muted small">Ajan aşağıdaki işlem{items.length > 1 ? "leri" : "i"} yapmak istiyor. Parametreleri inceleyip düzenleyebilirsiniz.</div>
        </div>
      </div>
      {items.map((p) => {
        const t = prettyTool(p.name, connectors);
        return (
          <div key={p.id} className="approval-item">
            <div className="row gap">
              {t.connector && <ConnectorLogo icon={t.connector.icon} color={t.connector.color} size={28} />}
              <div className="grow">
                <b className="cap">{t.name}</b>
                <div className="muted small">{t.connector?.name}</div>
              </div>
              <button className="btn ghost sm" onClick={() => setEditing(editing === p.id ? null : p.id)}>
                <Icon name={editing === p.id ? "eye" : "pencil"} size={14} /> {editing === p.id ? "Önizle" : "Düzenle"}
              </button>
            </div>
            {editing === p.id ? (
              <textarea className="code-edit" rows={10} value={inputs[p.id]}
                onChange={(e) => setInputs({ ...inputs, [p.id]: e.target.value })} />
            ) : (
              <ParamView value={safeParse(inputs[p.id])} />
            )}
            {items.length > 1 && (
              <div className="row gap mt">
                <button className="btn sm" disabled={busy} onClick={() => submit({ ...all(false), [p.id]: true })}>Sadece bunu onayla</button>
              </div>
            )}
          </div>
        );
      })}
      <div className="row gap end">
        <button className="btn danger-ghost" disabled={busy} onClick={() => submit(all(false))}>
          <Icon name="x" size={16} /> Reddet
        </button>
        <button className="btn primary" disabled={busy} onClick={() => submit(all(true))}>
          <Icon name="check" size={16} /> {items.length > 1 ? "Tümünü onayla" : "Onayla ve çalıştır"}
        </button>
      </div>
    </div>
  );
}

function safeParse(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

export function ParamView({ value }: { value: unknown }) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return (
      <dl className="params">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>{typeof v === "string" ? <span className="pre">{v}</span> : <code className="pre">{JSON.stringify(v, null, 2)}</code>}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <pre className="code">{JSON.stringify(value, null, 2)}</pre>;
}
