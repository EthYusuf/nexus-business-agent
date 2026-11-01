import { useEffect, useState } from "react";
import { api, SettingsT } from "../api";
import { useApp } from "../App";
import { Icon, PageHeader, toast, Toggle } from "../ui";

export default function Settings() {
  const { meta } = useApp();
  const [s, setS] = useState<SettingsT | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.settings().then(setS); }, []);
  if (!s) return <div className="loading">Yükleniyor…</div>;
  const set = <K extends keyof SettingsT>(k: K, v: SettingsT[K]) => setS({ ...s, [k]: v });

  const save = async () => {
    setBusy(true);
    try { setS(await api.saveSettings(s)); toast("Ayarlar kaydedildi."); }
    catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  };
  const test = async () => {
    setBusy(true);
    try { await api.saveSettings(s); const r = await api.testKey(); toast(`API anahtarı çalışıyor (${r.model}).`); }
    catch (e) { toast((e as Error).message, "err"); } finally { setBusy(false); }
  };

  return (
    <div className="page narrow">
      <PageHeader title="Ayarlar" actions={<button className="btn primary" disabled={busy} onClick={save}>Kaydet</button>} />

      <section className="card section">
        <h3><Icon name="key-round" size={17} /> Yapay zeka motoru</h3>
        <p className="muted">Ajanlar Anthropic Claude modelleriyle çalışır. API anahtarınızı console.anthropic.com adresinden alabilirsiniz.
          Anahtar yalnızca bu bilgisayarda saklanır.</p>
        <label>Anthropic API anahtarı
          <div className="row gap">
            <input type="password" className="grow" value={s.anthropic_api_key} placeholder="sk-ant-..."
              onChange={(e) => set("anthropic_api_key", e.target.value)} />
            <button className="btn" disabled={busy} onClick={test}><Icon name="plug-zap" size={15} /> Test et</button>
          </div>
        </label>
        <div className="form-grid">
          <label>Varsayılan model
            <select value={s.default_model} onChange={(e) => set("default_model", e.target.value)}>
              {meta?.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <label>Varsayılan düşünme derinliği
            <select value={s.default_effort} onChange={(e) => set("default_effort", e.target.value)}>
              {meta?.efforts.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
            <span className="muted small">low: hızlı ve ekonomik · medium: dengeli · high/xhigh/max: karmaşık işler</span>
          </label>
        </div>
        <Toggle checked={s.fallback_enabled} onChange={(v) => set("fallback_enabled", v)}
          label={<span>Sunucu taraflı yedek model <span className="muted small block">Model bir isteği reddederse Anthropic uygun bir yedek modelle yeniden dener.</span></span>} />
      </section>

      <section className="card section">
        <h3><Icon name="building-2" size={17} /> Şirket profili</h3>
        <p className="muted">Ajanlar bu bilgileri her görevde bağlam olarak kullanır (imza, ton, ürünler, politikalar).</p>
        <label>Şirket adı<input value={s.company_name} onChange={(e) => set("company_name", e.target.value)} /></label>
        <label>Şirket hakkında
          <textarea rows={7} value={s.company_profile} onChange={(e) => set("company_profile", e.target.value)}
            placeholder={"Sektör, ürün/hizmetler, çalışma saatleri, iade politikası, e-posta imzası, iletişim tonu…\nör. 'E-postaları \"Saygılarımızla, ABC Ltd. Müşteri Hizmetleri\" ile bitir.'"} />
        </label>
      </section>

      <section className="card section">
        <h3><Icon name="hard-drive" size={17} /> Yerel veri</h3>
        <p className="muted">Tüm veriler (sohbetler, şifreli kimlik bilgileri, günlükler) bu bilgisayardaki <code>data</code> klasöründe tutulur.
          Ajanların oluşturduğu dosyalar:</p>
        <code className="pathbox">{meta?.workspace}</code>
      </section>
    </div>
  );
}
