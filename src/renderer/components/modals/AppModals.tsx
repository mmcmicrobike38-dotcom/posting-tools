import { useState } from "react";
import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ConfirmPostModal } from "./ConfirmPostModal";
import { DoneModal } from "./DoneModal";
import { PostAgainModal } from "./PostAgainModal";
import { ResetDuplicateHistoryModal } from "./ResetDuplicateHistoryModal";
import { SettingsModal } from "./SettingsModal";
import { ShortcutsModal } from "./ShortcutsModal";
import { ActionModals } from "./ActionModals";

interface AppModalsProps {
  dashboard: SimsoftDashboardModel;
}

export function AppModals({ dashboard }: AppModalsProps) {
  const [showBranchWarningDetails, setShowBranchWarningDetails] = useState(false);
  const branchWarningMessage = dashboard.state.branchUploadMessage;
  const branchWarningParts = branchWarningMessage.split(/((?:MMC\d{3})(?:,\s*MMC\d{3})*)/);
  const actionModal = <ActionModals dashboard={dashboard} />;

  if (dashboard.state.activeModal === "confirmPost") return <ConfirmPostModal dashboard={dashboard} />;
  if (dashboard.state.activeModal === "postAgain") return <PostAgainModal dashboard={dashboard} />;
  if (dashboard.state.activeModal === "settings") return <SettingsModal dashboard={dashboard} />;
  if (dashboard.state.activeModal === "shortcuts") return <ShortcutsModal dashboard={dashboard} />;
  if (dashboard.state.activeModal === "resetDuplicates") return <ResetDuplicateHistoryModal dashboard={dashboard} />;
  if (dashboard.state.activeModal === "branchNotUploaded") {
    return (
      <DoneModal
        dashboard={dashboard}
        title="BRANCH NOT UPLOADED"
        message={branchWarningMessage}
        actionLabel="Continue"
        className="branch-warning-modal"
        onAction={() => dashboard.actions.setActiveModal(null)}
      >
        <div className="branch-warning-copy">
          <p>
            {branchWarningParts.map((part, index) =>
              /^MMC\d{3}(?:,\s*MMC\d{3})*$/.test(part) ? <strong key={index}>{part}</strong> : <span key={index}>{part}</span>
            )}
          </p>
          {showBranchWarningDetails ? (
            <p className="branch-warning-details">
              This assigned branch sheet was not found in the Google Drive folder. You can continue using the branch sheets that are available, or upload the missing branch sheet and rescan again.
            </p>
          ) : null}
          <button className="text-button" onClick={() => setShowBranchWarningDetails((current) => !current)}>
            {showBranchWarningDetails ? "See less" : "See more"}
          </button>
        </div>
      </DoneModal>
    );
  }
  if (dashboard.state.activeModal === "rescanDone") return <DoneModal dashboard={dashboard} title="RESCAN DONE" message="Google Drive folder scan is complete." />;
  if (dashboard.state.activeModal === "updateDone") return <DoneModal dashboard={dashboard} title="UPDATE DONE" message="Selected Google Sheet data has been refreshed." />;
  if (dashboard.state.activeModal === "wrongBranch") {
    return (
      <DoneModal
        dashboard={dashboard}
        title="WRONG BRANCH"
        message={dashboard.state.previewResult?.lockReasons.find((reason) => reason.includes("SIMSOFT file is for")) ?? "The SIMSOFT file does not match the selected branch."}
      />
    );
  }
  if (dashboard.state.activeModal === "updateSheetFirst") {
    return (
      <DoneModal
        dashboard={dashboard}
        title="UPDATE SHEET FIRST"
        message="Click Update Sheet for the selected branch before validating missing accounts. The Google Sheet may have changed."
      />
    );
  }
  if (dashboard.state.activeModal === "missingAccount") {
    return (
      <DoneModal
        dashboard={dashboard}
        title="MISSING ACCOUNT"
        message={
          dashboard.state.previewResult?.lockReasons.find((reason) => reason.startsWith("Missing account(s):")) ??
          "One or more regular accounts were not found in the selected branch ACCOUNTS tab."
        }
      />
    );
  }
  return actionModal;
}
