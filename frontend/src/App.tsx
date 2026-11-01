import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { AgentT, api, ConnectorT, MetaT } from "./api";
import { Icon, setToastHost } from "./ui";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Agents from "./pages/Agents";
import Integrations from "./pages/Integrations";
import Automations from "./pages/Automations";
import Approvals from "./pages/Approvals";
import Activity from "./pages/Activity";
import Settings from "./pages/Settings";

type Ctx = {
  meta: MetaT | null; agents: AgentT[]; connectors: ConnectorT[];
  reloadAgents: () => Promise<void>; reloadConnectors: () => Promise<void>;
  go: (route: string) => void; pendingCount: number;
};
const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

const NAV = [
  { id: "dashboard", label: "Genel Bakış", icon: "layout-dashboard" },
  { id: "chat", label: "Ajan Sohbeti", icon: "messages-square" },
  { id: "approvals", label: "Onay Kuyruğu", icon: "shield-check" },
  { id: "agents", label: "Ajanlar", icon: "bot" },
  { id: "integrations", label: "Entegrasyonlar", icon: "blocks" },
  { id: "automations", label: "Otomasyonlar", icon: "timer" },
  { id: "activity", label: "Etkinlik Günlüğü", icon: "scroll-text" },
  { id: "settings", label: "Ayarlar", icon: "settings" },
];

function parseHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [page, ...rest] = h.split("/");
  return { page: page || "dashboard", param: rest.join("/") };
}

export default function App() {
  const [route, setRoute] = useState(parseHash());
  const [meta, setMeta] = useState<MetaT | null>(null);
  const [agents, setAgents] = useState<AgentT[]>([]);
  const [connectors, setConnectors] = useState<ConnectorT[]>([]);
  const [pendingCount, setPending] = useState(0);
  const [toasts, setToasts] = useState<{ id: number; msg: string; tone: string }[]>([]);

  const reloadAgents = useCallback(async () => setAgents(await api.agents()), []);
  const reloadConnectors = useCallback(async () => setConnectors(await api.connectors()), []);

  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    api.meta().then(setMeta);
    reloadAgents();
    reloadConnectors();
    setToastHost((msg, tone = "ok") => {
      const id = Date.now() + Math.random();
      setToasts((t) => [...t, { id, msg, tone }]);
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
    });
    return () => window.removeEventListener("hashchange", on);
  }, [reloadAgents, reloadConnectors]);

  useEffect(() => {
    const tick = () => api.approvals().then((a) => setPending(a.length)).catch(() => {});
    tick();
    const t = setInterval(tick, 4000);
    return () => clearInterval(t);
  }, []);

  const go = (r: string) => { window.location.hash = "/" + r; };
  const active = connectors.filter((c) => c.connected && c.enabled && !c.builtin).length;

  let page;
  switch (route.page) {
    case "chat": page = <Chat convId={route.param} />; break;
    case "agents": page = <Agents />; break;
    case "integrations": page = <Integrations focus={route.param} />; break;
    case "automations": page = <Automations />; break;
    case "approvals": page = <Approvals />; break;
    case "activity": page = <Activity />; break;
    case "settings": page = <Settings />; break;
    default: page = <Dashboard />;
  }

  return (
    <AppCtx.Provider value={{ meta, agents, connectors, reloadAgents, reloadConnectors, go, pendingCount }}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">N</div>
            <div>
              <div className="brand-name">Nexus</div>
              <div className="brand-sub">Business Agent</div>
            </div>
          </div>
          <nav>
            {NAV.map((n) => (
              <a key={n.id} href={`#/${n.id}`} className={`nav-item ${route.page === n.id ? "active" : ""}`}>
                <Icon name={n.icon} size={18} />
                <span>{n.label}</span>
                {n.id === "approvals" && pendingCount > 0 && <span className="nav-count">{pendingCount}</span>}
              </a>
            ))}
          </nav>
          <div className="sidebar-foot">
            <div className="local-pill"><span className="dot ok" /> Yerel mod · verileriniz bu bilgisayarda</div>
            <div className="muted small">{active} entegrasyon aktif · v{meta?.version}</div>
          </div>
        </aside>
        <main className="main">{page}</main>
      </div>
      <div className="toasts">
        {toasts.map((t) => <div key={t.id} className={`toast toast-${t.tone}`}>{t.msg}</div>)}
      </div>
    </AppCtx.Provider>
  );
}
