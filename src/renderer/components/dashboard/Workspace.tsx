import { useCallback, useEffect, useRef, useState } from "react";
import { Download, RotateCw } from "lucide-react";
import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import type { AppUpdateController } from "../../services/updateService";
import { NextStepPanel } from "../ui/Primitives";
import { GoogleLinkScanner } from "../layout/GoogleLinkScanner";
import { SwipeToPostButton } from "../layout/SwipeToPostButton";
import { TargetBranchSelector } from "../layout/TargetBranchSelector";
import { UploadFolderCard } from "../layout/UploadFolderCard";
import { PreviewPanel } from "./PreviewPanel";
import { displayValue, friendlyIssueText, initialsFromName } from "./workspaceFormatters";

interface WorkspaceProps {
  dashboard: SimsoftDashboardModel;
  updater: AppUpdateController;
}

function UpdatePatchButton({ updater }: { updater: AppUpdateController }) {
  const visible =
    updater.status === "checking" ||
    updater.status === "error" ||
    updater.status === "available" ||
    updater.status === "downloading" ||
    updater.status === "installing" ||
    updater.status === "readyToRestart";
  if (!visible) {
    return (
      <span className="app-version-badge toolbar-chip" title="Installed app version">
        v{updater.appVersion}
      </span>
    );
  }

  const progress = updater.contentLength ? Math.min(99, Math.round((updater.downloadedBytes / updater.contentLength) * 100)) : undefined;
  const isChecking = updater.status === "checking";
  const isError = updater.status === "error";
  const isBusy = isChecking || updater.status === "downloading" || updater.status === "installing";
  const isRestartReady = updater.status === "readyToRestart";
  const label = isRestartReady
    ? "Restart"
    : isError
      ? "Retry update"
      : isChecking
        ? "Checking"
        : updater.status === "installing"
          ? "Installing"
          : updater.status === "downloading"
            ? progress
              ? `Downloading ${progress}%`
              : "Downloading"
            : updater.version
              ? `Update ${updater.version}`
              : "Update";
  const buttonClassName = [
    "update-patch-button",
    "toolbar-chip",
    isRestartReady ? "restart-ready" : "",
    isBusy ? "loading" : "",
    isError ? "error" : ""
  ]
    .filter(Boolean)
    .join(" ");
  const clickHandler = isRestartReady ? updater.restartApp : isError ? updater.checkForUpdates : updater.installUpdate;

  return (
    <button
      className={buttonClassName}
      type="button"
      onClick={() => void clickHandler()}
      disabled={isBusy}
      aria-label={isRestartReady ? "Restart to finish update" : isError ? "Retry update check" : "Download and install update"}
      title={isError ? updater.error || "Update check failed" : updater.body || label}
    >
      {isRestartReady || isChecking || isError ? <RotateCw aria-hidden="true" size={15} /> : <Download aria-hidden="true" size={15} />}
      <span>{label}</span>
    </button>
  );
}

type OperatorStep = {
  title: string;
  detail: string;
  actionLabel?: string;
  action?: () => void;
  tone: "info" | "warning" | "success";
};

type AttentionPanel = "fullyPaid" | "ibp" | "errors" | null;

function fullyPaidCashType(row: Record<string, unknown>): "FULLY PAID" | "CASH" | "REVIEW" {
  const rawType = String(row["Type"] ?? row["type"] ?? row["Export Type"] ?? row["export_type"] ?? "").trim().toUpperCase();
  if (rawType.includes("FULLY")) return "FULLY PAID";
  if (rawType === "CASH") return "CASH";
  return "REVIEW";
}

function buildOperatorStep({ state, derived, actions }: SimsoftDashboardModel): OperatorStep {
  const selectedSheetReady = Boolean(
    state.selectedBranchId &&
      state.sheetStatsByBranch[state.selectedBranchId]?.googleReady &&
      state.sheetStatsByBranch[state.selectedBranchId]?.targetBranchId === state.selectedBranchId
  );

  if (!state.operatorIdentity?.signedIn) {
    return {
      title: "Start with Google login",
      detail: "Connect the operator's Google account so Drive and Sheets access can be checked.",
      actionLabel: "Continue with Google",
      action: actions.loginGoogleOperator,
      tone: "info"
    };
  }

  if (!state.folderLinkValidation.ok) {
    return {
      title: "Paste the Drive folder link",
      detail: "Use the branch folder link shared with this operator, then scan it.",
      tone: "warning"
    };
  }

  if (state.scanStatus !== "completed") {
    return {
      title: "Scan the branch folder",
      detail: "Load branch spreadsheets before selecting the posting target.",
      actionLabel: state.scanStatus === "scanning" ? "Scanning..." : "Scan Folder",
      action: () => actions.scanFolder(false),
      tone: "info"
    };
  }

  if (!state.selectedBranchId) {
    return {
      title: "Select the target branch",
      detail: "Choose the branch that matches the SIMSOFT batch.",
      tone: "warning"
    };
  }

  if (!selectedSheetReady) {
    return {
      title: "Load the branch sheet",
      detail: "Load live ACCOUNTS data before validating the SIMSOFT file.",
      actionLabel: state.sheetUpdateStatus === "loading" ? "Loading..." : "Load Branch Sheet",
      action: actions.updateGoogleSheet,
      tone: "info"
    };
  }

  if (!state.filePath && !state.filePaths.length) {
    return {
      title: "Choose the SIMSOFT export",
      detail: "Select the Excel file or files for this posting batch.",
      actionLabel: "Choose File",
      action: actions.chooseFile,
      tone: "info"
    };
  }

  if (!state.result) {
    return {
      title: "Check the SIMSOFT file",
      detail: "Check rows, duplicates, and target-sheet rules before previewing.",
      actionLabel: "Check File",
      action: actions.parseFile,
      tone: "info"
    };
  }

  if (state.result.errors.length) {
    return {
      title: "Fix validation issues",
      detail: "Review the issues below, correct the source file, then validate again.",
      actionLabel: "Check Again",
      action: actions.parseFile,
      tone: "warning"
    };
  }

  if (!state.previewResult) {
    return {
      title: "Build the posting preview",
      detail: "Create the Google Sheet preview before final review.",
      actionLabel: "Build Preview",
      action: () => void actions.buildGooglePreviews(false),
      tone: "info"
    };
  }

  if (state.previewResult.canPost && derived.hasNewRowsToPost && state.governance.canFinalizePosting) {
    return {
      title: "Ready for final review",
      detail: "Check the preview tables, then use the Post control when everything is correct.",
      actionLabel: "Post",
      action: () => actions.setActiveModal("confirmPost"),
      tone: "success"
    };
  }

  if (state.previewResult.canPost && derived.hasNewRowsToPost && !state.governance.canFinalizePosting) {
    return {
      title: "Ready for admin review",
      detail: "This posting is ready, but final posting requires admin approval.",
      tone: "warning"
    };
  }

  if (state.previewResult.canPost && !derived.hasNewRowsToPost) {
    return {
      title: "No new rows to post",
      detail: "This batch appears to be fully duplicated, so posting is intentionally disabled.",
      tone: "success"
    };
  }

  return {
    title: "Review posting blockers",
    detail: "Resolve the listed blockers, then validate again before posting.",
    actionLabel: "Check Again",
    action: actions.parseFile,
    tone: "warning"
  };
}

export function Workspace({ dashboard, updater }: WorkspaceProps) {
  const { state, derived, actions } = dashboard;
  const [activeFunction, setActiveFunction] = useState<string | null>(null);
  const [openAttentionPanel, setOpenAttentionPanel] = useState<AttentionPanel>(null);
  const [ibpRedirectHint, setIbpRedirectHint] = useState("");
  const [ibpRedirectHintClosing, setIbpRedirectHintClosing] = useState(false);
  const [ibpPopupPosition, setIbpPopupPosition] = useState<{ top: number; left: number } | null>(null);
  const ibpAttentionRef = useRef<HTMLDivElement | null>(null);
  const hasErrors = Boolean(state.result?.errors.length || state.previewResult?.error || state.scanResult?.error || state.scanResult?.duplicateWarnings.length);
  const selectedSheetReady = Boolean(
    state.selectedBranchId &&
      state.sheetStatsByBranch[state.selectedBranchId]?.googleReady &&
      state.sheetStatsByBranch[state.selectedBranchId]?.targetBranchId === state.selectedBranchId
  );
  const operatorStep = buildOperatorStep(dashboard);
  const validationIssues = [
    ...(state.previewResult?.error ? [state.previewResult.error] : []),
    ...(state.result?.errors ?? [])
  ].map(friendlyIssueText);
  const scanIssues = [
    ...(state.scanResult?.error ? [state.scanResult.error] : []),
    ...(state.scanResult?.duplicateWarnings ?? [])
  ].map(friendlyIssueText);
  const postFailed = Boolean(state.postStatus && (state.postStatus.includes("ERROR") || state.postStatus.includes("locked")));
  const errorLogItems = [...validationIssues, ...scanIssues, ...(state.postStatus && postFailed ? [friendlyIssueText(state.postStatus)] : [])];
  const activeSheetLayout = state.previewResult?.sheetLayouts?.[state.activeTab];
  const selectPreviewTab = useCallback((tab: typeof state.activeTab) => actions.setActiveTab(tab), [actions.setActiveTab]);
  const fullyPaidCount = state.previewResult?.fullyPaidCashRows.length ?? 0;
  const ibpAttentionCount = derived.ibpReviewRows.filter((row) => {
    const breakdown = state.ibpPaymentBreakdowns[row.key];
    return !state.ibpParticulars[row.key]?.trim() || !breakdown?.amount?.trim();
  }).length;
  const selectedFileNames = (state.filePaths.length ? state.filePaths : state.filePath ? [state.filePath] : []).map((path) => path.split(/[\\/]/).pop() || path);
  const fileName = selectedFileNames.length > 1 ? `${selectedFileNames.length} files` : selectedFileNames[0] || "No file selected";
  const fullyPaidRows = state.previewResult?.fullyPaidCashRows ?? [];

  useEffect(() => {
    if (!ibpRedirectHint || openAttentionPanel !== "ibp") return;

    function updatePopupPosition() {
      const rect = ibpAttentionRef.current?.getBoundingClientRect();
      if (!rect) return;
      setIbpPopupPosition({
        top: Math.max(0, rect.top),
        left: Math.max(0, rect.left)
      });
    }

    updatePopupPosition();
    window.addEventListener("resize", updatePopupPosition);
    window.addEventListener("scroll", updatePopupPosition, true);
    return () => {
      window.removeEventListener("resize", updatePopupPosition);
      window.removeEventListener("scroll", updatePopupPosition, true);
    };
  }, [ibpRedirectHint, openAttentionPanel]);

  function updateIbpBreakdown(key: string, field: "rebate" | "amount" | "penalty", value: string) {
    setIbpRedirectHintClosing(false);
    setIbpRedirectHint("");
    setIbpPopupPosition(null);
    actions.setIbpPaymentBreakdowns({
      ...state.ibpPaymentBreakdowns,
      [key]: {
        rebate: state.ibpPaymentBreakdowns[key]?.rebate ?? "",
        amount: state.ibpPaymentBreakdowns[key]?.amount ?? "",
        penalty: state.ibpPaymentBreakdowns[key]?.penalty ?? "",
        [field]: value
      }
    });
  }

  function updateIbpParticular(key: string, value: string) {
    setIbpRedirectHintClosing(false);
    setIbpRedirectHint("");
    setIbpPopupPosition(null);
    actions.setIbpParticulars({
      ...state.ibpParticulars,
      [key]: value
    });
  }

  function firstMissingIbpField() {
    for (const [index, row] of derived.ibpReviewRows.entries()) {
      const breakdown = state.ibpPaymentBreakdowns[row.key];
      if (!state.ibpParticulars[row.key]?.trim()) return { index, field: "particular" };
      if (!breakdown?.amount?.trim()) return { index, field: "amount" };
    }
    return null;
  }

  function requestPostReview() {
    const missingIbpField = firstMissingIbpField();
    if (missingIbpField) {
      setOpenAttentionPanel("ibp");
      setIbpRedirectHintClosing(false);
      setIbpRedirectHint(
        missingIbpField.field === "particular"
          ? "Post is waiting for this IBP particular. Fill this field, then click Post again."
          : "Post is waiting for this MI amount. Fill this field, then click Post again."
      );
      window.setTimeout(() => {
        const input = document.querySelector<HTMLInputElement>(
          `[data-ibp-review-index="${missingIbpField.index}"][data-ibp-field="${missingIbpField.field}"]`
        );
        input?.scrollIntoView({ block: "center", behavior: "smooth" });
        input?.focus();
        input?.select();
      }, 0);
      return;
    }
    actions.setActiveModal("confirmPost");
  }

  function dismissIbpRedirectHint() {
    setIbpRedirectHintClosing(true);
    window.setTimeout(() => {
      setIbpRedirectHint("");
      setIbpRedirectHintClosing(false);
      setIbpPopupPosition(null);
    }, 180);
  }

  const functionTiles = [
    {
      id: "folder",
      label: "Branch Folder",
      value: state.scanStatus === "completed" ? `${state.scanResult?.branchCount ?? 0} sheets` : state.folderLinkValidation.ok ? "Ready" : "Not set",
      ready: state.scanStatus === "completed"
    },
    {
      id: "branch",
      label: "Target Branch",
      value: state.selectedBranchId || "Not selected",
      ready: Boolean(state.selectedBranchId)
    },
    {
      id: "sheet",
      label: "Branch Sheet",
      value: selectedSheetReady ? "Loaded" : "Not loaded",
      ready: selectedSheetReady
    },
    {
      id: "file",
      label: "SIMSOFT Excel",
      value: state.filePath || state.filePaths.length ? fileName : "No file",
      ready: Boolean(state.filePath || state.filePaths.length)
    },
    {
      id: "check",
      label: "Check File",
      value: state.previewResult ? "Preview ready" : state.result ? "Checked" : "Not checked",
      ready: Boolean(state.result || state.previewResult)
    },
    {
      id: "post",
      label: state.governance.canFinalizePosting ? "Post" : "Admin Review",
      value: state.previewResult?.canPost && derived.hasNewRowsToPost && state.governance.canFinalizePosting ? "Ready" : "Locked",
      ready: Boolean(state.previewResult?.canPost && derived.hasNewRowsToPost && state.governance.canFinalizePosting)
    }
  ];
  const canSwipePost =
    state.folderLinkValidation.ok &&
    Boolean(state.selectedBranchId) &&
    Boolean(state.scanResult) &&
    Boolean(state.filePath || state.filePaths.length) &&
    Boolean(state.previewResult?.canPost) &&
    derived.hasNewRowsToPost &&
    state.governance.canFinalizePosting &&
    state.scanStatus !== "scanning" &&
    !state.busy &&
    !state.isPosting;
  const postDisabledReason = !state.folderLinkValidation.ok
    ? "Save and scan a valid Drive folder first."
    : !state.selectedBranchId
      ? "Select the target branch first."
      : !state.filePath && !state.filePaths.length
        ? "Choose the SIMSOFT Excel file or files first."
        : !state.previewResult
          ? "Check the file and review the preview first."
          : !state.previewResult.canPost
            ? state.previewResult.postLockReason || "Posting is blocked by validation checks."
            : !state.governance.canFinalizePosting
              ? "Admin approval is required to finalize postings."
            : !derived.hasNewRowsToPost
              ? "There are no new passed rows to post."
              : "";
  const activeFunctionPanel =
    activeFunction === "folder" ? (
      <GoogleLinkScanner dashboard={dashboard} />
    ) : activeFunction === "branch" || activeFunction === "sheet" ? (
      <TargetBranchSelector dashboard={dashboard} />
    ) : activeFunction === "file" || activeFunction === "check" ? (
      <UploadFolderCard dashboard={dashboard} />
    ) : activeFunction === "post" ? (
      <div className="function-post-panel">
        <SwipeToPostButton disabled={!canSwipePost} posting={state.isPosting} disabledReason={postDisabledReason} onConfirm={requestPostReview} />
      </div>
    ) : null;
  const operatorName = state.operatorIdentity?.name || state.operatorIdentity?.email || "Operator";
  const nextStepAction = operatorStep.action
    ? { label: operatorStep.actionLabel, action: operatorStep.actionLabel === "Post" ? requestPostReview : operatorStep.action }
    : !state.folderLinkValidation.ok
      ? { label: "Branch Folder", action: () => setActiveFunction("folder") }
      : !state.selectedBranchId
        ? { label: "Select Branch", action: () => setActiveFunction("branch") }
        : !selectedSheetReady
          ? { label: "Load Sheet", action: () => setActiveFunction("sheet") }
          : !state.filePath && !state.filePaths.length
            ? { label: "Choose File", action: () => setActiveFunction("file") }
            : !state.result
              ? { label: "Check File", action: () => setActiveFunction("check") }
              : !state.previewResult
                ? { label: "Build Preview", action: () => void actions.buildGooglePreviews(false) }
                : { label: "Review Post", action: () => setActiveFunction("post") };
  const showBranchPickerInNextStep = state.scanStatus === "completed" && !state.selectedBranchId;
  const nextStepActionSlot = showBranchPickerInNextStep ? (
    <div className="next-step-branch-action">
      <select
        value={state.selectedBranchId}
        onChange={(event) => actions.setSelectedBranchId(event.target.value)}
        disabled={!derived.branchOptions.length || state.busy || state.isScanning}
        aria-label="Select target branch"
      >
        <option value="">Select target branch</option>
        {derived.branchOptions.map((branch) => (
          <option key={branch.branch_id} value={branch.branch_id}>
            {branch.branch_id} - {branch.branch_name || branch.file_name}
          </option>
        ))}
      </select>
      <button className="warning-action" onClick={() => setActiveFunction("sheet")} disabled={!state.selectedBranchId || state.busy}>
        OK
      </button>
    </div>
  ) : undefined;
  const operatorRole = state.userRole === "admin" ? "Admin" : "Member";
  const operatorInitials = initialsFromName(operatorName);

  return (
    <section className="workspace">
      {ibpRedirectHint ? (
        <div
          className={ibpRedirectHintClosing ? "ibp-redirect-popup closing" : "ibp-redirect-popup"}
          role="status"
          style={ibpPopupPosition ? { top: ibpPopupPosition.top, left: ibpPopupPosition.left } : { visibility: "hidden" }}
        >
          <span>
            <strong>Important</strong>
            {ibpRedirectHint}
          </span>
          <button type="button" onClick={dismissIbpRedirectHint} aria-label="Dismiss IBP message" title="Dismiss">
            &rarr;
          </button>
        </div>
      ) : null}
      <header className="toolbar">
        <div className="toolbar-identity">
          <span className="toolbar-brand-mark" aria-hidden="true">{operatorInitials}</span>
          <div>
            <p className="operator-kicker">Posting Tools</p>
            <h2>{operatorName}</h2>
            <p>{operatorRole}</p>
          </div>
        </div>
        <div className="toolbar-update-slot toolbar-status-group" aria-live="polite" aria-label="Current app version">
          <UpdatePatchButton updater={updater} />
        </div>
        <div className="toolbar-actions">
          <div className="toolbar-status-group" aria-label="Current posting context">
            <span className={hasErrors ? "badge toolbar-chip danger-badge" : "badge toolbar-chip"}>{hasErrors ? "Needs attention" : "Ready"}</span>
            <span className="badge toolbar-chip">Branch: {state.selectedBranchId || "Not selected"}</span>
          </div>
          <button className="info-button" onClick={() => actions.setActiveModal("aboutPostingReview")} aria-label="About posting review" title="About Posting Review">
            i
          </button>
          <button className="settings-icon-button" onClick={() => actions.setShowAdvancedSettings(true)} aria-label="Open settings" title="Settings">
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
              <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.65 8.9a1.7 1.7 0 0 0-.34-1.88l-.06-.06A2 2 0 1 1 7.08 4.1l.06.06a1.7 1.7 0 0 0 1.88.34H9A1.7 1.7 0 0 0 10 2.96V3a2 2 0 1 1 4 0v-.04a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.88v.02a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z" />
            </svg>
          </button>
          <button className="header-logout-button" onClick={() => actions.setActiveModal("logoutConfirm")} aria-label="Logout" title="Logout" disabled={state.isAuthenticating}>
            <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <path d="M16 17l5-5-5-5" />
              <path d="M21 12H9" />
            </svg>
          </button>
        </div>
      </header>

      <section className="dashboard-function-card" aria-label="App functions">
        <div className="function-summary-grid">
          {functionTiles.map((tile, index) => (
            <button
              className={`function-summary-tile ${tile.ready ? "ready" : ""} ${activeFunction === tile.id ? "active" : ""}`}
              key={tile.label}
              onClick={() => setActiveFunction((current) => (current === tile.id ? null : tile.id))}
              aria-expanded={activeFunction === tile.id}
            >
              <span>{tile.ready ? "OK" : index + 1}</span>
              <div>
                <strong>{tile.label}</strong>
                <small>{tile.value}</small>
              </div>
            </button>
          ))}
        </div>
        {activeFunctionPanel ? <div className="function-detail-drawer">{activeFunctionPanel}</div> : null}
      </section>

      <NextStepPanel
        tone={operatorStep.tone}
        title={operatorStep.title}
        detail={operatorStep.detail}
        actionLabel={nextStepAction.label}
        actionSlot={nextStepActionSlot}
        onAction={nextStepAction.action}
        disabled={state.busy || state.isScanning || state.sheetUpdateStatus === "loading"}
      />

      <section className="sheet-review-card" aria-label="Google Sheet preview and operator attention">
        <PreviewPanel
          activeTab={state.activeTab}
          activeColumns={derived.activeColumns}
          activeRows={derived.activeRows}
          previewCounts={derived.previewCounts}
          activeSheetLayout={activeSheetLayout}
          emptyPreviewMessage={derived.emptyPreviewMessage}
          onSelectTab={selectPreviewTab}
        />

        <aside className="operator-attention-panel" aria-label="Operator attention">
          <div className="review-panel-header">
            <div>
              <span>Operator Attention</span>
              <h3>Review before posting</h3>
            </div>
          </div>

          <div className="attention-list">
            <div className={`${fullyPaidCount ? "attention-item warning" : "attention-item ready"} ${openAttentionPanel === "fullyPaid" ? "expanded" : ""}`.trim()}>
              <button
                className="attention-toggle"
                onClick={() => setOpenAttentionPanel((current) => (current === "fullyPaid" ? null : "fullyPaid"))}
                aria-expanded={openAttentionPanel === "fullyPaid"}
                type="button"
              >
                <div>
                  <strong>Fully Paid / Cash</strong>
                  <p>{fullyPaidCount ? "Check accounts marked fully paid or cash before posting." : "No fully paid or cash rows found."}</p>
                </div>
                <span>{fullyPaidCount}</span>
              </button>
              {openAttentionPanel === "fullyPaid" ? (
                <div className="attention-detail">
                  {fullyPaidRows.length ? (
                    fullyPaidRows.map((row, index) => {
                      const rowType = fullyPaidCashType(row);
                      return (
                        <div className={`attention-detail-row fully-paid-cash-row ${rowType === "CASH" ? "cash-row" : rowType === "FULLY PAID" ? "fully-paid-row" : ""}`.trim()} key={index}>
                          <div className="attention-account-heading fully-paid-cash-heading">
                            <span>{displayValue(row["Code"] ?? row["CODE"] ?? row["code"] ?? row["OR No"] ?? row["OR Number"] ?? row["Reference"] ?? row["REF"])}</span>
                            <strong>{displayValue(row["Account Name"] ?? row["Account"] ?? row["account_name"])}</strong>
                            <em className="fully-paid-cash-badge">{rowType}</em>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <p className="attention-empty">No Fully Paid / Cash details to review.</p>
                  )}
                </div>
              ) : null}
            </div>

            <div ref={ibpAttentionRef} className={`${ibpAttentionCount ? "attention-item warning" : "attention-item ready"} ${openAttentionPanel === "ibp" ? "expanded" : ""}`.trim()}>
              <button
                className="attention-toggle"
                onClick={() => setOpenAttentionPanel((current) => (current === "ibp" ? null : "ibp"))}
                aria-expanded={openAttentionPanel === "ibp"}
                type="button"
              >
                <div>
                  <strong>IBP to Other Branch Input</strong>
                  <p>{ibpAttentionCount ? "Enter missing particulars and amount breakdowns." : "IBP particulars are complete."}</p>
                </div>
                <span>{ibpAttentionCount}</span>
              </button>
              {openAttentionPanel === "ibp" ? (
                <div className="attention-detail">
                  {derived.ibpReviewRows.length ? (
                    derived.ibpReviewRows.map((row, rowIndex) => {
                      const breakdown = state.ibpPaymentBreakdowns[row.key] ?? { rebate: "", amount: "", penalty: "" };
                      return (
                        <div className="attention-detail-row ibp-attention-row" key={row.key}>
                          <strong>{row.customer || row.accountNo}</strong>
                          <div className="attention-ibp-inputs" aria-label={`IBP payment breakdown for ${row.customer || row.accountNo}`}>
                            <label>
                              <span>IBP</span>
                              <input
                                value={state.ibpParticulars[row.key] ?? ""}
                                onChange={(event) => updateIbpParticular(row.key, event.target.value)}
                                placeholder="25/36 MI"
                                data-ibp-review-index={rowIndex}
                                data-ibp-field="particular"
                              />
                            </label>
                            <label>
                              <span>REBATE</span>
                              <input
                                inputMode="decimal"
                                value={breakdown.rebate}
                                onChange={(event) => updateIbpBreakdown(row.key, "rebate", event.target.value)}
                                placeholder="0.00"
                              />
                            </label>
                            <label>
                              <span>MI</span>
                              <input
                                inputMode="decimal"
                                value={breakdown.amount}
                                onChange={(event) => updateIbpBreakdown(row.key, "amount", event.target.value)}
                                placeholder={row.amount || "0.00"}
                                data-ibp-review-index={rowIndex}
                                data-ibp-field="amount"
                              />
                            </label>
                            <label>
                              <span>PEN</span>
                              <input
                                inputMode="decimal"
                                value={breakdown.penalty}
                                onChange={(event) => updateIbpBreakdown(row.key, "penalty", event.target.value)}
                                placeholder="0.00"
                              />
                            </label>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <p className="attention-empty">No IBP rows need input.</p>
                  )}
                </div>
              ) : null}
            </div>

            <div className={`${errorLogItems.length ? "attention-item danger" : "attention-item ready"} ${openAttentionPanel === "errors" ? "expanded" : ""}`.trim()}>
              <button
                className="attention-toggle"
                onClick={() => setOpenAttentionPanel((current) => (current === "errors" ? null : "errors"))}
                aria-expanded={openAttentionPanel === "errors"}
                type="button"
              >
                <div>
                  <strong>Error Logs</strong>
                  <p>{errorLogItems[0] ?? "No current validation or scan errors."}</p>
                </div>
                <span>{errorLogItems.length}</span>
              </button>
              {openAttentionPanel === "errors" ? (
                <div className="attention-detail">
                  {errorLogItems.length ? (
                    <ul className="attention-error-list">
                      {errorLogItems.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="attention-empty">No error logs right now.</p>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </aside>
      </section>

      {validationIssues.length ? (
        <section className="errors message-card">
          <h3>Needs Attention</h3>
          <ul className="issue-list">
            {validationIssues.map((issue, index) => (
              <li key={`${issue}-${index}`}>{issue}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {state.postStatus ? (
        <section className={postFailed ? "errors message-card" : "notice message-card"}>
          <h3>Posting Result</h3>
          <p>{friendlyIssueText(state.postStatus)}</p>
        </section>
      ) : null}

      {scanIssues.length ? (
        <section className="errors message-card">
          <h3>Folder Scan Issue</h3>
          <ul className="issue-list">
            {scanIssues.map((issue, index) => (
              <li key={`${issue}-${index}`}>{issue}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
