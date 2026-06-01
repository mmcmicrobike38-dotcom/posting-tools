import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface ConfirmPostModalProps {
  dashboard: SimsoftDashboardModel;
}

export function ConfirmPostModal({ dashboard }: ConfirmPostModalProps) {
  const { state, derived, actions } = dashboard;
  const selectedFileNames = (state.filePaths.length ? state.filePaths : state.filePath ? [state.filePath] : []).map((path) => path.split(/[\\/]/).pop() || path);
  const fileName = selectedFileNames.length > 1 ? `${selectedFileNames.length} files selected` : selectedFileNames[0] || "No file selected";
  const selectedBranch = state.sheetStats?.targetBranchName || state.selectedBranchId || "No branch selected";
  const duplicateCount = derived.duplicateRowCount;
  const canPost = Boolean(
    state.previewResult?.canPost &&
      derived.hasNewRowsToPost &&
      !state.previewResult.errors.length &&
      !state.previewResult.lockReasons.length &&
      state.governance.canFinalizePosting
  );

  return (
    <ModalShell
      title="Post validated data?"
      titleId="confirm-post-modal-title"
      closeLabel="Close post confirmation"
      className="post-confirm-modal"
      onClose={() => actions.setActiveModal(null)}
      footer={
        <>
          <button onClick={() => actions.setActiveModal(null)} disabled={state.isPosting}>Cancel</button>
          <button className="primary" onClick={actions.postGooglePreviews} disabled={state.isPosting || !canPost}>
            {state.isPosting ? "Posting..." : state.governance.canFinalizePosting ? "Post Now" : "Admin Approval Required"}
          </button>
        </>
      }
    >
      <p>You are about to post validated records to SCRVSBR. Review the summary before continuing.</p>
      <dl className="modal-facts post-summary">
        <dt>Target Branch</dt>
        <dd>{selectedBranch}</dd>
        <dt>Selected File(s)</dt>
        <dd>{fileName}</dd>
        <dt>Passed Rows</dt>
        <dd>{derived.passedRowCount}</dd>
        <dt>Duplicates</dt>
        <dd>{duplicateCount}</dd>
        <dt>Destination</dt>
        <dd>ACCOUNTS, RECEIPT, 1-31 Daily, SCR VS BR</dd>
        <dt>Current User</dt>
        <dd>{state.operatorIdentity?.email || "Not signed in"}</dd>
      </dl>
      {!canPost ? (
        <p className="modal-warning">
          {state.governance.canFinalizePosting
            ? "Posting is blocked. Resolve validation warnings, duplicate issues, or missing Google/branch setup first."
            : "Final posting requires admin approval."}
        </p>
      ) : null}
    </ModalShell>
  );
}
