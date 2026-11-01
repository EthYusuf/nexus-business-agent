import { useEffect, useState } from "react";
import { api, ConversationT, timeAgo } from "../api";
import { useApp } from "../App";
import ApprovalCard from "../components/ApprovalCard";
import { Empty, Icon, PageHeader } from "../ui";

export default function Approvals() {
  const { agents } = useApp();
  const [list, setList] = useState<ConversationT[] | null>(null);
  const load = () => api.approvals().then(setList);
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);

  return (
    <div className="page narrow">
      <PageHeader title="Onay Kuyruğu" subtitle="Ajanların dış dünyayı etkileyen işlemleri (e-posta, fatura, stok, mesaj) burada onayınızı bekler." />
      {list === null ? <div className="loading">Yükleniyor…</div> : list.length === 0 ? (
        <Empty icon="shield-check" title="Bekleyen onay yok" text="Tüm işlemler güncel." />
      ) : list.map((c) => {
        const a = agents.find((x) => x.id === c.agent_id);
        return (
          <div key={c.id + c.updated_at} className="card approval-wrap">
            <div className="row gap mb">
              <span className="agent-avatar" style={{ background: a?.color }}><Icon name={a?.icon || "bot"} size={15} /></span>
              <div className="grow"><b>{a?.name}</b><div className="muted small">{c.title} · {timeAgo(c.updated_at)}</div></div>
              <a className="link small" href={`#/chat/${c.id}`}>Sohbeti aç →</a>
            </div>
            <ApprovalCard conv={c} onDone={load} compact />
          </div>
        );
      })}
    </div>
  );
}
