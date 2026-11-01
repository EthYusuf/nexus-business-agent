import { icons, Plug, X } from "lucide-react";
import { ReactNode, useEffect } from "react";

export function Icon({ name, size = 18, className }: { name: string; size?: number; className?: string }) {
  const pascal = name.split("-").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join("");
  const Cmp = (icons as Record<string, typeof Plug>)[pascal] || Plug;
  return <Cmp size={size} className={className} />;
}

export function Badge({ tone = "gray", children }: { tone?: string; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Modal({ title, subtitle, onClose, children, footer, wide }: {
  title: ReactNode; subtitle?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{title}</h3>
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Kapat"><X size={18} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track"><span className="toggle-thumb" /></span>
      {label && <span>{label}</span>}
    </label>
  );
}

export function Empty({ icon, title, text, action }: { icon: string; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon name={icon} size={26} /></div>
      <h4>{title}</h4>
      {text && <p className="muted">{text}</p>}
      {action}
    </div>
  );
}

export function ConnectorLogo({ icon, color, size = 36 }: { icon: string; color: string; size?: number }) {
  return (
    <div className="clogo" style={{ width: size, height: size, background: color + "1a", color }}>
      <Icon name={icon} size={Math.round(size * 0.5)} />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="row gap">{actions}</div>}
    </div>
  );
}

let toastHost: ((msg: string, tone?: string) => void) | null = null;
export const toast = (msg: string, tone = "ok") => toastHost?.(msg, tone);
export function setToastHost(fn: typeof toastHost) { toastHost = fn; }
