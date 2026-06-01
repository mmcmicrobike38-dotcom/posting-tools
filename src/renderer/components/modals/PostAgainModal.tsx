import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface PostAgainModalProps {
  dashboard: SimsoftDashboardModel;
}

export function PostAgainModal({ dashboard }: PostAgainModalProps) {
  const { state, actions } = dashboard;
  const postingPreview = state.previewResult as (typeof state.previewResult & { postedCount?: number; postedAt?: string }) | null;
  const postedCount = Number(postingPreview?.postedCount ?? 0);
  const postedAt = String(postingPreview?.postedAt ?? "");

  return (
    <ModalShell
      title="Posting completed"
      titleId="post-again-modal-title"
      closeLabel="Close post complete"
      className="done-modal"
      onClose={() => actions.setActiveModal(null)}
      footer={
        <>
          <button onClick={() => actions.setActiveModal(null)}>Close</button>
          <button className="primary" onClick={actions.prepareNextPost} disabled={state.busy}>Post Again</button>
        </>
      }
    >
      <p>Posting finished. You can close this message or prepare the app for another SIMSOFT batch.</p>
      <dl className="modal-facts">
        <dt>Posted Count</dt>
        <dd>{postedCount}</dd>
        <dt>Duplicate History</dt>
        <dd>{state.duplicateStatus?.duplicateTransactionCount ?? 0}</dd>
        <dt>Timestamp</dt>
        <dd>{postedAt ? new Date(postedAt).toLocaleString() : new Date().toLocaleString()}</dd>
        <dt>Branch</dt>
        <dd>{state.sheetStats?.targetBranchName || state.selectedBranchId || "Selected branch"}</dd>
      </dl>
    </ModalShell>
  );
}
