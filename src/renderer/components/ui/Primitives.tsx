import { ReactNode } from "react";

export type UiStatus = "idle" | "loading" | "success" | "warning" | "error" | "blocked" | "ready" | "completed" | "attention";

interface StatusBadgeProps {
  status: UiStatus;
  children: ReactNode;
}

export function StatusBadge({ status, children }: StatusBadgeProps) {
  return <span className={`status-badge ${status}`}>{children}</span>;
}

interface SidebarSectionProps {
  title: string;
  status: UiStatus;
  statusLabel: string;
  helper: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function SidebarSection({ title, status, statusLabel, helper, children, actions }: SidebarSectionProps) {
  return (
    <section className="side-card sidebar-section">
      <div className="sidebar-section-header">
        <div>
          <h3>{title}</h3>
          <p>{helper}</p>
        </div>
        <StatusBadge status={status}>{statusLabel}</StatusBadge>
      </div>
      <div className="sidebar-section-body">{children}</div>
      {actions ? <div className="sidebar-section-actions">{actions}</div> : null}
    </section>
  );
}

interface NextStepPanelProps {
  tone: "info" | "warning" | "success" | "error";
  title: string;
  detail: string;
  actionLabel?: string;
  actionSlot?: ReactNode;
  disabled?: boolean;
  onAction?: () => void;
}

export function NextStepPanel({ tone, title, detail, actionLabel, actionSlot, disabled, onAction }: NextStepPanelProps) {
  return (
    <section className={`next-step-panel ${tone}`} aria-live="polite">
      <div>
        <span>Next step</span>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
      {actionSlot ? actionSlot : onAction && actionLabel ? (
        <button className={tone === "success" ? "success-action" : tone === "warning" ? "warning-action" : "primary-action"} onClick={onAction} disabled={disabled}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}
