import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { SidebarSection, UiStatus } from "../ui/Primitives";

interface GoogleLinkScannerProps {
  dashboard: SimsoftDashboardModel;
}

export function GoogleLinkScanner({ dashboard }: GoogleLinkScannerProps) {
  const { state, actions } = dashboard;
  const count = state.scanResult?.branchCount ?? 0;
  const status: UiStatus =
    state.scanStatus === "scanning"
      ? "loading"
      : state.scanStatus === "completed"
        ? "completed"
        : state.scanStatus === "invalid" || state.scanStatus === "error"
          ? "error"
          : state.folderLinkValidation.ok
            ? "ready"
            : "idle";
  const statusLabel =
    state.scanStatus === "scanning"
      ? "Scanning"
      : state.scanStatus === "completed"
        ? "Ready"
        : state.scanStatus === "invalid"
          ? "Invalid"
          : state.scanStatus === "error"
            ? "Needs attention"
            : state.savedFolderUrl
              ? "Saved"
              : "Not saved";

  return (
    <SidebarSection title="Branch Folder" status={status} statusLabel={statusLabel} helper="Use the saved Google Drive folder that contains branch sheets.">
      <textarea
        className={state.savedFolderUrl ? "saved-folder-field" : ""}
        value={state.folderUrl}
        onChange={(event) => actions.setFolderUrl(event.target.value)}
        placeholder="Paste Google Drive folder link"
        readOnly={Boolean(state.savedFolderUrl)}
        rows={2}
      />
      <div className="folder-secondary-actions">
        <button
          className="small-text-button success-text"
          onClick={() => actions.setActiveModal("saveLinkConfirm")}
          disabled={!state.folderLinkValidation.ok || state.isScanning || state.busy}
          aria-label="Save folder link"
          title={state.folderLinkValidation.ok ? "Save Drive folder link" : "Paste a valid Google Drive folder link first."}
        >
          Save link
        </button>
        <button
          className="small-text-button danger-text"
          onClick={() => actions.setActiveModal("unsaveLinkConfirm")}
          disabled={!state.savedFolderUrl || state.isScanning || state.busy}
          aria-label="Remove saved folder link"
          title={state.savedFolderUrl ? "Remove saved Drive folder link" : "No saved link to remove."}
        >
          Unsave link
        </button>
      </div>
      <button
        className="primary primary-scan-action"
        onClick={() => actions.setActiveModal("rescanConfirm")}
        disabled={!state.folderLinkValidation.ok || state.isScanning || state.busy}
        aria-label="Scan Drive folder"
        title={state.folderLinkValidation.ok ? "Ctrl+R" : "Paste a valid Google Drive folder link first."}
      >
        {state.isScanning ? "Scanning..." : state.scanStatus === "completed" ? "Refresh Folder" : "Scan Folder"}
      </button>
      <div className={`scan-pill ${state.scanStatus}`}>
        {state.scanStatus === "scanning" ? <span className="spinner" /> : <i className={state.scanStatus === "completed" ? "dot online" : "dot offline"} />}
        {state.scanStatus === "idle" ? "Idle" : null}
        {state.scanStatus === "invalid" ? "Invalid link" : null}
        {state.scanStatus === "scanning" ? "Scanning folder..." : null}
        {state.scanStatus === "completed" ? `Completed: ${count} sheet(s)` : null}
        {state.scanStatus === "error" ? "Scan error" : null}
      </div>
      {state.scanError ? <p className="field-error">{state.scanError}</p> : null}
      {state.scanSource !== "idle" ? <p className="cache-note">{state.scanSource}</p> : null}
      {state.savedFolderUrl ? <p className="cache-note">Saved folder link</p> : null}
    </SidebarSection>
  );
}
