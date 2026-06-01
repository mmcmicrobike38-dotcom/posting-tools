import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface DoneModalProps {
  dashboard: SimsoftDashboardModel;
  title: string;
  message: string;
  actionLabel?: string;
  className?: string;
  children?: React.ReactNode;
  onAction?: () => void;
}

export function DoneModal({ dashboard, title, message, actionLabel = "OK", className = "done-modal", children, onAction }: DoneModalProps) {
  const close = () => dashboard.actions.setActiveModal(null);
  const handleAction = () => {
    if (onAction) {
      onAction();
      return;
    }
    close();
  };

  return (
    <ModalShell
      title={title}
      titleId={`${title.toLowerCase().replace(/\s+/g, "-")}-title`}
      closeLabel="Close"
      className={className}
      onClose={close}
      footer={
        <button className="primary" onClick={handleAction}>
          {actionLabel}
        </button>
      }
    >
      {children ?? <p>{message}</p>}
    </ModalShell>
  );
}
