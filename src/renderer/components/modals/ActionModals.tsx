import { useState } from "react";
import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "./ModalShell";

interface ActionModalsProps {
  dashboard: SimsoftDashboardModel;
}

function close(dashboard: SimsoftDashboardModel) {
  dashboard.actions.setActiveModal(null);
}

function ResultList({ items }: { items: { label: string; value: string | number }[] }) {
  return (
    <dl className="modal-facts">
      {items.map((item) => (
        <div className="modal-fact-row" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ActionModals({ dashboard }: ActionModalsProps) {
  const { state, actions } = dashboard;
  const [cacheAcknowledged, setCacheAcknowledged] = useState(false);

  if (state.activeModal === "logoutConfirm") {
    return (
      <ModalShell
        title="Logout from SIMSOFT?"
        titleId="logout-confirm-title"
        closeLabel="Close logout confirmation"
        className="compact-modal warning-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)} disabled={state.isAuthenticating}>Cancel</button>
            <button className="danger" onClick={actions.logoutGoogleOperator} disabled={state.isAuthenticating}>
              {state.isAuthenticating ? "Logging out..." : "Logout"}
            </button>
          </>
        }
      >
        <p>You will be signed out of this session.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "rescanConfirm") {
    return (
      <ModalShell
        title="Rescan Drive Folder?"
        titleId="rescan-confirm-title"
        closeLabel="Close rescan confirmation"
        className="compact-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)} disabled={state.isScanning}>Cancel</button>
            <button className="primary" data-default-action="true" onClick={actions.refreshScan} disabled={state.isScanning}>
              {state.isScanning ? "Scanning..." : "Scan"}
            </button>
          </>
        }
      >
        <p>This will check the saved Google Drive folder again and update the branch sheet list.</p>
        {state.isScanning ? <div className="inline-progress"><span className="spinner" />Scanning Drive folder...</div> : null}
      </ModalShell>
    );
  }

  if (state.activeModal === "saveLinkConfirm") {
    return (
      <ModalShell
        title="Save Drive Folder Link?"
        titleId="save-link-confirm-title"
        closeLabel="Close save link confirmation"
        className="compact-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)}>Cancel</button>
            <button
              className="primary"
              data-default-action="true"
              onClick={() => {
                if (actions.saveFolderUrl()) actions.setActiveModal("saveLinkDone");
              }}
            >
              Save Link
            </button>
          </>
        }
      >
        <p>This folder will be used as the source for branch sheets.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "saveLinkDone") {
    return (
      <ModalShell
        title="Drive folder link saved"
        titleId="save-link-done-title"
        closeLabel="Close saved link result"
        className="compact-modal result-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>OK</button>}
      >
        <p>The saved folder will be used for branch sheet scans.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "unsaveLinkConfirm") {
    return (
      <ModalShell
        title="Remove Saved Drive Folder Link?"
        titleId="unsave-link-confirm-title"
        closeLabel="Close remove link confirmation"
        className="compact-modal destructive-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)}>Cancel</button>
            <button
              className="danger"
              onClick={() => {
                actions.unsaveFolderUrl();
                actions.setActiveModal("unsaveLinkDone");
              }}
            >
              Remove Link
            </button>
          </>
        }
      >
        <p>The app will forget the current Drive folder link. You can add it again later.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "unsaveLinkDone") {
    return (
      <ModalShell
        title="Drive folder link removed"
        titleId="unsave-link-done-title"
        closeLabel="Close remove link result"
        className="compact-modal result-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>OK</button>}
      >
        <p>The app is ready for a new Drive folder link.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "updateSheetConfirm") {
    return (
      <ModalShell
        title="Update Branch Sheet?"
        titleId="update-sheet-confirm-title"
        closeLabel="Close update sheet confirmation"
        className="compact-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)} disabled={state.sheetUpdateStatus === "loading"}>Cancel</button>
            <button className="primary" data-default-action="true" onClick={actions.updateGoogleSheet} disabled={state.sheetUpdateStatus === "loading"}>
              {state.sheetUpdateStatus === "loading" ? "Updating..." : "Update Sheet"}
            </button>
          </>
        }
      >
        <p>This will load the selected branch sheet and update the account count.</p>
        {state.sheetUpdateStatus === "loading" ? <div className="inline-progress"><span className="spinner" />Loading selected branch sheet...</div> : null}
      </ModalShell>
    );
  }

  if (state.activeModal === "validateFileFirst" || state.activeModal === "invalidFileType") {
    return (
      <ModalShell
        title={state.activeModal === "validateFileFirst" ? "Choose a SIMSOFT Excel file first" : "Invalid file type"}
        titleId="file-error-title"
        closeLabel="Close file error"
        className="compact-modal error-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)}>Cancel</button>
            <button className="primary" data-default-action="true" onClick={actions.chooseFile}>Choose File</button>
          </>
        }
      >
        <p>{state.activeModal === "validateFileFirst" ? "Choose the SIMSOFT export Excel file, then click Validate." : "Please select the SIMSOFT Excel export file ending in .xlsx or .xlsm."}</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "postBlocked") {
    return (
      <ModalShell
        title="Posting blocked"
        titleId="post-blocked-title"
        closeLabel="Close posting blocked message"
        className="compact-modal error-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>OK</button>}
      >
        <p>{state.message || "Resolve duplicates or validation errors first."}</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "clearCacheConfirm") {
    return (
      <ModalShell
        title="Clear App Cache?"
        titleId="clear-cache-confirm-title"
        closeLabel="Close clear cache confirmation"
        className="compact-modal destructive-modal"
        onClose={() => {
          setCacheAcknowledged(false);
          close(dashboard);
        }}
        footer={
          <>
            <button onClick={() => close(dashboard)} disabled={state.isLoadingCache}>Cancel</button>
            <button
              className="danger"
              onClick={() => {
                setCacheAcknowledged(false);
                void actions.clearCache();
              }}
              disabled={state.isLoadingCache || !cacheAcknowledged}
            >
              {state.isLoadingCache ? "Clearing..." : "Clear Cache"}
            </button>
          </>
        }
      >
        <p>This may slow down the next scan because SIMSOFT will rebuild cached data.</p>
        <label className="confirmation-checkbox">
          <input type="checkbox" checked={cacheAcknowledged} onChange={(event) => setCacheAcknowledged(event.target.checked)} />
          <span>I understand that the next scan may take longer.</span>
        </label>
      </ModalShell>
    );
  }

  if (state.activeModal === "clearCacheDone") {
    return (
      <ModalShell
        title="App cache cleared"
        titleId="clear-cache-done-title"
        closeLabel="Close cache result"
        className="compact-modal result-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>OK</button>}
      >
        <p>The next scan may take longer while SIMSOFT rebuilds saved data.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "googleTestUsersConfirm") {
    return (
      <ModalShell
        title="Open Google Test Users Page?"
        titleId="google-test-users-confirm-title"
        closeLabel="Close Google page confirmation"
        className="compact-modal"
        onClose={() => close(dashboard)}
        footer={
          <>
            <button onClick={() => close(dashboard)}>Cancel</button>
            <button className="primary" data-default-action="true" onClick={actions.openGoogleTestUsersPage} disabled={state.busy}>Open</button>
          </>
        }
      >
        <p>This will open the Google test users page in your browser.</p>
      </ModalShell>
    );
  }

  if (state.activeModal === "healthCheckResult") {
    return (
      <ModalShell
        title={state.busy ? "Running Health Check" : state.healthCheck?.ok ? "Health check passed" : "Health check needs attention"}
        titleId="health-check-result-title"
        closeLabel="Close health check result"
        className="health-result-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)} disabled={state.busy}>Done</button>}
      >
        {state.busy ? (
          <div className="inline-progress"><span className="spinner" />Checking Google login, Drive folder, cache, and app files...</div>
        ) : (
          <div className="health-list">
            {(state.healthCheck?.items ?? []).length ? (
              state.healthCheck?.items.map((item) => (
                <div className={item.ok ? "health-row ok" : "health-row"} key={item.label}>
                  <i aria-hidden="true" />
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.detail}</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="cache-note">Run Health Check to review Google login, Drive folder, cache, logs, access list, and credentials.</p>
            )}
          </div>
        )}
      </ModalShell>
    );
  }

  if (state.activeModal === "settingsSummary") {
    return (
      <ModalShell
        title="Settings Summary"
        titleId="settings-summary-title"
        closeLabel="Close settings summary"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>Done</button>}
      >
        <ResultList
          items={[
            { label: "Version", value: state.status?.appVersion ?? "Unknown" },
            { label: "Google Login", value: state.operatorIdentity?.signedIn ? "Ready" : "Needs attention" },
            { label: "Drive Folder", value: state.savedFolderUrl || state.folderUrl ? "Saved" : "Not set" },
            { label: "Branch", value: state.selectedBranchId || "No branch selected" },
            { label: "Access Role", value: state.userRole === "admin" ? "Admin" : "Member" },
            { label: "Duplicate Rows", value: state.duplicateStatus?.duplicateTransactionCount ?? 0 }
          ]}
        />
      </ModalShell>
    );
  }

  if (state.activeModal === "aboutPostingReview") {
    return (
      <ModalShell
        title="About Posting Review"
        titleId="about-posting-review-title"
        closeLabel="Close posting review information"
        className="info-modal"
        onClose={() => close(dashboard)}
        footer={<button className="primary" data-default-action="true" onClick={() => close(dashboard)}>Done</button>}
      >
        <p>Use this screen to check a SIMSOFT Excel export before sending approved records to the selected branch sheet.</p>
        <ol className="simple-list">
          <li>Connect Google and scan the Drive folder.</li>
          <li>Select the correct branch and update the sheet.</li>
          <li>Choose the SIMSOFT Excel file, then validate it.</li>
          <li>Review the preview tabs and any warnings.</li>
          <li>Post only when the app says posting is ready.</li>
        </ol>
      </ModalShell>
    );
  }

  return null;
}
