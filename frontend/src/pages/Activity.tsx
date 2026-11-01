import { Fragment, useEffect, useState } from "react";
import { ActivityT, api, prettyTool } from "../api";
import { useApp } from "../App";
import { Badge, ConnectorLogo, Empty, Icon, PageHeader } from "../ui";

export default function Activity() {
  const { connectors, agents } = useApp();
  const [rows, setRows] = useState<ActivityT[] | null>(null);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => { api.activity(filter || undefined).then(setRows); }, [filter]);

  const exportCsv = () => {
    if (!rows) return;
    const head = ["Tarih", "Ajan", "Entegrasyon", "Araç", "Durum", "Onay", "Süre (ms)", "Parametreler"];
    const lines = rows.map((r) => [new Date(r.created_at * 1000).toLocaleString("tr-TR"),
      agents.find((a) => a.id === r.agent_id)?.name || r.agent_id, r.connector_id, r.tool, r.ok ? "Başarılı" : "Hata",
      r.approved_by, r.duration_ms, r.input].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";"));
    const blob = new Blob(["﻿" + [head.join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "nexus-etkinlik.csv";
    a.click();
  };

  return (
    <div className="page">
      <PageHeader title="Etkinlik Günlüğü" subtitle="Ajanların gerçekleştirdiği her işlemin denetim kaydı."
        actions={<>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">Tüm entegrasyonlar</option>
            {connectors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn" onClick={exportCsv}><Icon name="download" size={15} /> CSV</button>
        </>} />
      {rows === null ? <div className="loading">Yükleniyor…</div> : rows.length === 0 ? (
        <Empty icon="scroll-text" title="Kayıt yok" text="Ajanlar araç kullandıkça burada görünecek." />
      ) : (
        <div className="card table-card">
          <table>
            <thead><tr><th>Zaman</th><th>İşlem</th><th>Ajan</th><th>Onay</th><th>Süre</th><th>Durum</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const t = prettyTool(r.tool, connectors);
                return (
                  <Fragment key={r.id}>
                    <tr className="clickable" onClick={() => setOpen(open === r.id ? null : r.id)}>
                      <td className="nowrap muted">{new Date(r.created_at * 1000).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" })}</td>
                      <td><div className="row gap-s">{t.connector && <ConnectorLogo icon={t.connector.icon} color={t.connector.color} size={24} />}<span className="cap">{t.name}</span></div></td>
                      <td>{agents.find((a) => a.id === r.agent_id)?.name || "—"}</td>
                      <td>{r.approved_by === "user" ? <Badge tone="violet">Kullanıcı</Badge> : <span className="muted small">otomatik</span>}</td>
                      <td className="muted">{r.duration_ms} ms</td>
                      <td><Badge tone={r.ok ? "green" : "red"}>{r.ok ? "Başarılı" : "Hata"}</Badge></td>
                    </tr>
                    {open === r.id && (
                      <tr className="detail"><td colSpan={6}>
                        <div className="split">
                          <div><div className="label">Parametreler</div><pre className="code">{pretty(r.input)}</pre></div>
                          <div><div className="label">Sonuç</div><pre className="code">{r.result}</pre></div>
                        </div>
                        <a className="link small" href={`#/chat/${r.conversation_id}`}>Sohbete git →</a>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function pretty(s: string) {
  try { return JSON.stringify(JSON.parse(s), null, 2); } catch { return s; }
}
