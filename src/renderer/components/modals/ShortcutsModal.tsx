import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface ShortcutsModalProps {
  dashboard: SimsoftDashboardModel;
}

const shortcuts = [
  ["Esc", "Close modal, settings, or expanded details"],
  ["Ctrl+O", "Choose SIMSOFT file"],
  ["Ctrl+R", "Rescan Drive folder"],
  ["Ctrl+U", "Update selected Google Sheet"],
  ["Ctrl+Enter", "Validate SIMSOFT file"],
  ["Ctrl+P", "Open post confirmation"],
  ["Ctrl+,", "Open Advanced Settings"],
  ["Ctrl+1-5", "Switch preview tabs"]
] as const;

export function ShortcutsModal({ dashboard }: ShortcutsModalProps) {
  const { actions } = dashboard;

  return (
    <ModalShell
      title="Keyboard Shortcuts"
      titleId="shortcuts-modal-title"
      closeLabel="Close shortcuts"
      className="shortcuts-modal"
      onClose={() => actions.setActiveModal(null)}
      footer={<button className="primary" onClick={() => actions.setActiveModal(null)}>Done</button>}
    >
      <div className="shortcut-list">
        {shortcuts.map(([keys, description]) => (
          <div className="shortcut-row" key={keys}>
            <kbd>{keys}</kbd>
            <span>{description}</span>
          </div>
        ))}
      </div>
    </ModalShell>
  );
}
