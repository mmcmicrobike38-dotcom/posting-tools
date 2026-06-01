import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { SidebarSection, UiStatus } from "../ui/Primitives";

interface UploadFolderCardProps {
  dashboard: SimsoftDashboardModel;
}

export function UploadFolderCard({ dashboard }: UploadFolderCardProps) {
  const { state, actions } = dashboard;
  const fileNames = (state.filePaths.length ? state.filePaths : state.filePath ? [state.filePath] : []).map((path) => path.split(/[\\/]/).pop() || path);
  const fileLabel = state.filePaths.length > 1 ? `${state.filePaths.length} files selected` : state.filePath;
  const hasFiles = Boolean(state.filePath || state.filePaths.length);
  const status: UiStatus = state.busy && state.message.toLowerCase().includes("validating") ? "loading" : state.result ? "completed" : hasFiles ? "ready" : "idle";
  const statusLabel = state.result ? "Validated" : hasFiles ? "Selected" : "No file";

  return (
    <SidebarSection title="SIMSOFT Excel" status={status} statusLabel={statusLabel} helper="Choose one or more SIMSOFT export Excel files before validation.">
      <button className="secondary-action choose-file-button" onClick={actions.chooseFile} disabled={state.busy} title="Ctrl+O">Choose SIMSOFT Excel Files</button>
      <input
        className={hasFiles ? "uploaded-file-field" : ""}
        value={fileLabel}
        onChange={(event) => actions.setFilePath(event.target.value)}
        placeholder="No file selected"
        readOnly={hasFiles}
      />
      {fileNames.length ? (
        <div className="file-chip-list">
          {fileNames.map((fileName) => (
            <div className="file-chip" key={fileName}>
              <i aria-hidden="true" />
              <span>{fileName}</span>
            </div>
          ))}
        </div>
      ) : (
        <span>No SIMSOFT file loaded yet. Choose the export Excel file(s), then click Validate.</span>
      )}
      <button
        className="success-action"
        onClick={actions.parseFile}
        disabled={state.busy}
        title={hasFiles ? "Ctrl+Enter" : "Choose a SIMSOFT Excel file first."}
      >
        {state.busy ? "Checking..." : "Check File"}
      </button>
    </SidebarSection>
  );
}
