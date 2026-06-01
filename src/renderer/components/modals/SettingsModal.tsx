import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface SettingsModalProps {
  dashboard: SimsoftDashboardModel;
}

export function SettingsModal({ dashboard }: SettingsModalProps) {
  const { state, derived, actions } = dashboard;
  const checkedAt = state.healthCheck?.checkedAt ? new Date(state.healthCheck.checkedAt).toLocaleString() : "Not checked yet";

  return (
    <ModalShell
      title="Settings"
      titleId="settings-modal-title"
      closeLabel="Close settings"
      onClose={() => actions.setActiveModal(null)}
      footer={
        <>
          <button onClick={actions.runHealthCheck} disabled={state.busy}>{state.busy ? "Checking..." : "Run Health Check"}</button>
          <button className="primary" onClick={() => actions.setActiveModal(null)}>Done</button>
        </>
      }
    >
      <section className="settings-section">
        <h3>Setup</h3>
        <div className="settings-list">
          {derived.setupChecklist.map((item) => (
            <div className="settings-row" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.done ? "Ready" : "Needed"}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <h3>App</h3>
        <dl className="settings-facts">
          <dt>Version</dt>
          <dd>{state.status?.appVersion ?? "Unknown"}</dd>
          <dt>Auth</dt>
          <dd>{state.effectiveGoogleAuthMode ?? state.status?.authMode ?? "service_account"}</dd>
          <dt>Operator</dt>
          <dd>{state.operatorIdentity?.email || "Not signed in"}</dd>
          <dt>Folder</dt>
          <dd>{state.savedFolderUrl || state.folderUrl || "Not saved"}</dd>
        </dl>
      </section>

      <section className="settings-section">
        <h3>Local Paths</h3>
        <dl className="settings-facts">
          <dt>Cache</dt>
          <dd>{state.status?.cachePath ?? ""}</dd>
          <dt>Duplicates</dt>
          <dd>{state.status?.duplicateHistoryPath ?? ""}</dd>
          <dt>Batches</dt>
          <dd>{state.status?.postedBatchesPath ?? ""}</dd>
          <dt>Locks</dt>
          <dd>{state.status?.postingLocksPath ?? ""}</dd>
          <dt>Access</dt>
          <dd>{state.status?.accessControlPath ?? ""}</dd>
          <dt>Logs</dt>
          <dd>{state.status?.logDir ?? ""}</dd>
          <dt>OAuth</dt>
          <dd>{state.status?.oauthTokenDir ?? ""}</dd>
          <dt>Credential</dt>
          <dd>{state.status?.serviceAccountJsonPath ?? ""}</dd>
        </dl>
        <div className="settings-actions">
          <button onClick={() => actions.openSupportFolder("data")}>Open Data</button>
          <button onClick={() => actions.openSupportFolder("logs")}>Open Logs</button>
          <button onClick={() => actions.openSupportFolder("config")}>Open Config</button>
        </div>
      </section>

      <section className={state.status?.sharedStorageConfigured ? "settings-section storage-ready" : "settings-section storage-local"}>
        <h3>Deployment Storage</h3>
        <p>
          {state.status?.sharedStorageConfigured
            ? "Shared storage paths are configured for duplicate history, batch records, locks, or logs."
            : "This workstation is using local storage. Use shared storage paths before running multiple posting PCs."}
        </p>
      </section>

      <section className="settings-section">
        <div className="side-card-header">
          <h3>Health Check</h3>
          <span>{checkedAt}</span>
        </div>
        {state.healthCheck ? (
          <div className="health-list">
            {state.healthCheck.items.map((item) => (
              <div className={item.ok ? "health-row ok" : "health-row"} key={item.label}>
                <i aria-hidden="true" />
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>Run a health check to verify local files and folders.</p>
        )}
      </section>
    </ModalShell>
  );
}
