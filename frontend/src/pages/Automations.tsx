import { useEffect, useState } from "react";
import { api, AutomationT, timeAgo } from "../api";
import { useApp } from "../App";
import { Empty, Icon, Modal, PageHeader, toast, Toggle } from "../ui";

const INTERVALS = [
  [15, "Her 15 dakikada"], [30, "Her 30 dakikada"], [60, "Saatte bir"], [180, "3 saatte bir"],
  [360, "6 saatte bir"], [720, "Günde iki kez"], [1440, "Günde bir"], [10080, "Haftada bir"],
] as const;

const TEMPLATES = [
  { name: "Sabah e-posta özeti", agent_id: "a_inbox", interval_minutes: 1440,
    prompt: "Son 24 saatteki okunmamış e-postaları tara, önceliklendir ve özetini Telegram'dan gönder." },
  { name: "Vadesi geçen fatura takibi", agent_id: "a_finance", interval_minutes: 1440,
    prompt: "Paraşüt'te vadesi geçmiş faturaları bul ve her müşteri için kibar bir hatırlatma e-postası taslağı oluştur." },
  { name: "Trendyol soru yanıtlama", agent_id: "a_commerce", interval_minutes: 60,
    prompt: "Trendyol'da yanıt bekleyen müşteri sorularını yanıtla. Emin olmadığın soruları atla ve listele." },
  { name: "Düşük stok uyarısı", agent_id: "a_commerce", interval_minutes: 360,
    prompt: "Tüm mağazalarda stoğu 5'in altına düşen ürünleri bul ve Telegram'dan uyarı gönder." },
];

export default function Automations() {
  const { agents, go } = useApp();
  const [list, setList] = useState<AutomationT[]>([]);
  const [edit, setEdit] = useState<Partial<AutomationT> | null>(null);
  const load = () => api.automations().then(setList);
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!edit?.name || !edit.prompt || !edit.agent_id) return toast("Ad, ajan ve görev gerekli.", "err");
    const body = { ...edit, enabled: edit.enabled ?? 1 };
    if (edit.id) await api.updateAutomation(edit.id, body); else await api.createAutomation(body);
    toast("Otomasyon kaydedildi.");
    setEdit(null);
    load();
  };

  return (
    <div className="page">
      <PageHeader title="Otomasyonlar" subtitle="Ajanlarınız belirlediğiniz aralıklarla görevleri kendiliğinden çalıştırır. Uygulama açık olduğu sürece çalışır."
        actions={<button className="btn primary" onClick={() => setEdit({ interval_minutes: 60, agent_id: agents[0]?.id, enabled: 1 })}><Icon name="plus" size={16} /> Yeni otomasyon</button>} />

      {list.length === 0 ? (
        <>
          <Empty icon="timer" title="Henüz otomasyon yok" text="Hazır şablonlardan biriyle başlayabilirsiniz." />
          <div className="cards">
            {TEMPLATES.map((t) => (
              <button key={t.name} className="card conn-card" onClick={() => setEdit({ ...t, enabled: 1 })}>
                <h3 className="left">{t.name}</h3>
                <p className="muted left">{t.prompt}</p>
                <span className="link small mt-auto">Şablonu kullan →</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="card table-card">
          <table>
            <thead><tr><th>Otomasyon</th><th>Ajan</th><th>Sıklık</th><th>Son çalışma</th><th>Durum</th><th /></tr></thead>
            <tbody>
              {list.map((a) => {
                const ag = agents.find((x) => x.id === a.agent_id);
                return (
                  <tr key={a.id}>
                    <td><b>{a.name}</b><div className="muted small clamp-1">{a.prompt}</div></td>
                    <td>{ag?.name || "—"}</td>
                    <td>{INTERVALS.find((i) => i[0] === a.interval_minutes)?.[1] || `${a.interval_minutes} dk`}</td>
                    <td>{a.last_conversation_id ? <a className="link" href={`#/chat/${a.last_conversation_id}`}>{timeAgo(a.last_run)}</a> : "—"}</td>
                    <td><Toggle checked={!!a.enabled} onChange={async (v) => { await api.updateAutomation(a.id, { ...a, enabled: v ? 1 : 0 }); load(); }} /></td>
                    <td className="nowrap">
                      <button className="btn sm" onClick={async () => { const r = await api.runAutomation(a.id); go(`chat/${r.conversation_id}`); }}>
                        <Icon name="play" size={13} /> Şimdi çalıştır</button>
                      <button className="icon-btn" onClick={() => setEdit(a)}><Icon name="pencil" size={15} /></button>
                      <button className="icon-btn" onClick={async () => { if (confirm("Silinsin mi?")) { await api.deleteAutomation(a.id); load(); } }}><Icon name="trash-2" size={15} /></button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {edit && (
        <Modal title={edit.id ? "Otomasyonu düzenle" : "Yeni otomasyon"} onClose={() => setEdit(null)}
          footer={<><span className="grow" /><button className="btn" onClick={() => setEdit(null)}>Vazgeç</button><button className="btn primary" onClick={save}>Kaydet</button></>}>
          <label>Ad<input value={edit.name || ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
          <div className="form-grid">
            <label>Ajan<select value={edit.agent_id} onChange={(e) => setEdit({ ...edit, agent_id: e.target.value })}>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
            <label>Sıklık<select value={edit.interval_minutes} onChange={(e) => setEdit({ ...edit, interval_minutes: +e.target.value })}>
              {INTERVALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          </div>
          <label>Görev talimatı<textarea rows={5} value={edit.prompt || ""} onChange={(e) => setEdit({ ...edit, prompt: e.target.value })} /></label>
          <p className="muted small">Onay gerektiren işlemler "Onay Kuyruğu"na düşer; ajanın otomatik onayı açıksa doğrudan çalıştırılır.</p>
        </Modal>
      )}
    </div>
  );
}
