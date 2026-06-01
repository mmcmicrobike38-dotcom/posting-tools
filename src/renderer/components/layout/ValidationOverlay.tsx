import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";

interface ValidationOverlayProps {
  dashboard: SimsoftDashboardModel;
}

export function ValidationOverlay({ dashboard }: ValidationOverlayProps) {
  const overlay = dashboard.state.validationOverlay;
  if (!overlay) return null;

  return (
    <div className="validation-overlay" role="status" aria-live="polite">
      <div className={`validation-loader ${overlay.status}`}>
        <div className="validation-symbol" aria-hidden="true" />
        <strong>{overlay.title}</strong>
        <span>{overlay.message}</span>
      </div>
    </div>
  );
}
