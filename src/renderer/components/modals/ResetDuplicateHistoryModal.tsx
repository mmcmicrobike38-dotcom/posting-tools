import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface ResetDuplicateHistoryModalProps {
  dashboard: SimsoftDashboardModel;
}

export function ResetDuplicateHistoryModal({ dashboard }: ResetDuplicateHistoryModalProps) {
  const { state, derived, actions } = dashboard;
  const sourceFileLabel =
    state.filePaths.length > 1
      ? `${state.filePaths.length} files`
      : (state.filePaths[0] || state.filePath).split(/[\\/]/).pop() || "";

  return (
    <ModalShell
      title="Duplicate History"
      titleId="reset-modal-title"
      closeLabel="Close duplicate history reset"
      onClose={() => actions.setActiveModal(null)}
      footer={
        <>
          <button onClick={() => actions.setActiveModal(null)} disabled={state.busy}>Cancel</button>
          <button className="danger" onClick={actions.resetDuplicateHistory} disabled={!derived.duplicateResetConfirmed || state.busy}>
            {state.busy ? "Resetting..." : "Reset Local Duplicate History"}
          </button>
        </>
      }
    >
      <p>Review duplicate protection totals before resetting. Resetting clears only the local duplicate protection files on this PC and does not delete Google Sheet rows.</p>
      <div className="duplicate-history-filters" aria-label="Duplicate history filters">
        <input value={dashboard.state.selectedBranchId || ""} readOnly aria-label="Branch filter" placeholder="Branch" />
        <input value={new Date().toLocaleDateString()} readOnly aria-label="Date filter" placeholder="Date" />
        <input value={sourceFileLabel} readOnly aria-label="Source file filter" placeholder="Source file" />
      </div>
      <dl className="modal-facts">
        <dt>History File</dt>
        <dd>{state.duplicateStatus?.duplicateHistoryPath || "data/duplicate_history.csv"}</dd>
        <dt>Transaction Keys</dt>
        <dd>{state.duplicateStatus?.duplicateTransactionCount ?? 0}</dd>
        <dt>Posted Batch Rows</dt>
        <dd>{state.duplicateStatus?.postedBatchRowCount ?? 0}</dd>
      </dl>
      <label>Type Reset Duplicate History</label>
      <input value={state.duplicateResetText} onChange={(event) => actions.setDuplicateResetText(event.target.value)} autoFocus />
    </ModalShell>
  );
}
