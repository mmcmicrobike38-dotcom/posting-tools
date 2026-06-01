import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AppStatus,
  FolderScanResult,
  GoogleSheetStats,
  GoogleSheetPreviewResult,
  IbpPaymentBreakdowns,
  IbpParticulars,
  ParseResult,
} from "../../shared/types";
import { ActiveModal, PreviewTab } from "../lib/previewTabs";
import { authService } from "../services/authService";
import { cacheService } from "../services/cacheService";
import { ScanSource, scanService } from "../services/scanService";
import { postService } from "../services/postService";
import {
  getBranchOptions,
  isExcelFilePath,
  resolveGovernanceUiAccess,
  resolveGovernanceUser,
  resolveAccessViewState,
  SAVED_FOLDER_URL_KEY,
  ScanStatus,
  SheetUpdateStatus
} from "../features/posting/model/postingViewModel";
import { useAppBootstrap } from "./dashboard/useAppBootstrap";
import { useDashboardFeedback } from "./dashboard/useDashboardFeedback";
import { usePreviewState } from "./dashboard/usePreviewState";
import { simsoftApi } from "../shared/api/simsoftApiClient";
import { operatorError } from "../utils/errors";
import { safeDisplayText, validateGoogleFolderLink } from "../utils/googleLinks";

export function useSimsoftDashboard() {
  const [message, setMessage] = useState("");
  const {
    status,
    setStatus,
    refreshStatus,
    duplicateStatus,
    setDuplicateStatus,
    healthCheck,
    setHealthCheck,
    operatorIdentity,
    setOperatorIdentity
  } = useAppBootstrap(setMessage);
  const { toastMessage, validationOverlay, showToast, showValidationOverlay } = useDashboardFeedback();
  const [filePath, setFilePath] = useState("");
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const [folderUrl, setFolderUrl] = useState("");
  const [savedFolderUrl, setSavedFolderUrl] = useState("");
  const [scanResult, setScanResult] = useState<FolderScanResult | null>(null);
  const [sheetStats, setSheetStats] = useState<GoogleSheetStats | null>(null);
  const [sheetStatsByBranch, setSheetStatsByBranch] = useState<Record<string, GoogleSheetStats>>({});
  const [selectedBranchId, setSelectedBranchId] = useState("");
  const [result, setResult] = useState<ParseResult | null>(null);
  const [previewResult, setPreviewResult] = useState<GoogleSheetPreviewResult | null>(null);
  const [activeTab, setActiveTab] = useState<PreviewTab>("SIMSOFT");
  const [postStatus, setPostStatus] = useState("");
  const [ibpParticulars, setIbpParticulars] = useState<IbpParticulars>({});
  const [ibpPaymentBreakdowns, setIbpPaymentBreakdowns] = useState<IbpPaymentBreakdowns>({});
  const [duplicateResetText, setDuplicateResetText] = useState("");
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [legacyBusy, setBusy] = useState(false);
  const [isPosting, setIsPosting] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false);
  const [isLoadingCache, setIsLoadingCache] = useState(false);
  const [showPostingGateDetails, setShowPostingGateDetails] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [scanStatus, setScanStatus] = useState<ScanStatus>("idle");
  const [sheetUpdateStatus, setSheetUpdateStatus] = useState<SheetUpdateStatus>("idle");
  const [scanSource, setScanSource] = useState<ScanSource>("idle");
  const [scanError, setScanError] = useState("");
  const [scanCompletedAt, setScanCompletedAt] = useState<number | null>(null);
  const [branchUploadMessage, setBranchUploadMessage] = useState("");
  const scanRequestId = useRef(0);
  const lastScannedLink = useRef("");
  const busy = legacyBusy || isPosting || isAuthenticating || isGeneratingPreview || isLoadingCache;

  useEffect(() => {
    const savedLink = window.localStorage.getItem(SAVED_FOLDER_URL_KEY) ?? "";
    const validation = validateGoogleFolderLink(savedLink);
    if (validation.ok) {
      setSavedFolderUrl(validation.normalizedUrl);
      setFolderUrl(validation.normalizedUrl);
    }
  }, []);

  const folderLinkValidation = useMemo(() => validateGoogleFolderLink(folderUrl), [folderUrl]);

  const accessViewState = useMemo(() => resolveAccessViewState(status, operatorIdentity), [operatorIdentity, status]);
  const { userRole, isAdmin, assignedBranchIds, hasLimitedBranchAssignment } = accessViewState;
  const governanceUser = useMemo(() => resolveGovernanceUser(status, operatorIdentity), [operatorIdentity, status]);
  const governance = useMemo(() => resolveGovernanceUiAccess(governanceUser, selectedBranchId), [governanceUser, selectedBranchId]);

  const branchOptions = useMemo(
    () => getBranchOptions(scanResult?.branchIndex, accessViewState),
    [accessViewState, scanResult]
  );

  const previewState = usePreviewState({
    activeTab,
    previewResult,
    result,
    sheetStats,
    selectedBranchId,
    ibpParticulars,
    ibpPaymentBreakdowns
  });
  const {
    summaryRows,
    activeRows,
    activeColumns,
    previewCounts,
    passedRowCount,
    duplicateRowCount,
    hasNewRowsToPost,
    ibpReviewRows,
    ibpReviewRequired,
    emptyPreviewMessage
  } = previewState;

  const duplicateResetConfirmed = duplicateResetText.trim().toLowerCase() === "reset duplicate history";
  const effectiveGoogleAuthMode = operatorIdentity?.signedIn ? operatorIdentity.authMode : status?.authMode;
  const setupChecklist = useMemo(
    () => [
      { label: "Google login", done: Boolean(operatorIdentity?.signedIn) },
      { label: "Drive folder", done: folderLinkValidation.ok && scanStatus === "completed" },
      { label: "Target branch", done: Boolean(selectedBranchId) },
      { label: "SIMSOFT file", done: Boolean(result) }
    ],
    [folderLinkValidation.ok, operatorIdentity?.signedIn, result, scanStatus, selectedBranchId]
  );
  const setupComplete = setupChecklist.every((item) => item.done);
  const selectedBranchSheetUpdated = Boolean(
    selectedBranchId &&
      sheetStatsByBranch[selectedBranchId]?.googleReady &&
      sheetStatsByBranch[selectedBranchId]?.targetBranchId === selectedBranchId
  );

  async function chooseFile() {
    try {
      const selectedFiles = await simsoftApi.chooseSimsoftFiles();
      if (!selectedFiles.length) return;
      const invalidFile = selectedFiles.find((selected) => !isExcelFilePath(selected));
      if (invalidFile) {
        setMessage("Invalid file type. Please select the SIMSOFT Excel export file.");
        setActiveModal("invalidFileType");
        return;
      }
      setFilePaths(selectedFiles);
      setFilePath(selectedFiles[0]);
      setResult(null);
      setPreviewResult(null);
      const label = selectedFiles.length === 1 ? selectedFiles[0].split(/[\\/]/).pop() || "SIMSOFT Excel file" : `${selectedFiles.length} SIMSOFT Excel files`;
      setMessage(`Selected ${label}. Click Validate when ready.`);
    } catch (error) {
      setMessage(operatorError(error, "File picker could not be opened."));
    }
  }

  function updateFilePath(path: string) {
    setFilePath(path);
    setFilePaths(path ? [path] : []);
    setResult(null);
    setPreviewResult(null);
  }

  async function parseFile() {
    const selectedFilePaths = filePaths.length ? filePaths : filePath ? [filePath] : [];
    if (!selectedFilePaths.length) {
      setMessage("Choose one or more SIMSOFT Excel files first.");
      setActiveModal("validateFileFirst");
      return;
    }
    if (selectedFilePaths.some((path) => !isExcelFilePath(path))) {
      setMessage("Invalid file type. Please select only SIMSOFT Excel export files.");
      setActiveModal("invalidFileType");
      return;
    }
    setBusy(true);
    setMessage("Checking SIMSOFT file...");
    showValidationOverlay({ status: "loading", title: "Checking", message: "Validating SIMSOFT file..." });
    try {
      const parsed = await simsoftApi.parseSimsoftFiles(selectedFilePaths);
      setResult(parsed);
      setPreviewResult(null);
      setActiveTab("SIMSOFT");
      if (parsed.errors.length) {
        setMessage("Validation needs attention.");
        showValidationOverlay({ status: "error", title: "Validation Failed", message: "Please review the highlighted errors." }, true);
      } else if (folderUrl && scanResult && selectedBranchId && operatorIdentity?.signedIn) {
        showValidationOverlay({ status: "loading", title: "Checking", message: "Building Google Sheet preview..." });
        const built = await buildGooglePreviews(false);
        if (built && !built.error && !built.lockReasons.includes("Wrong branch") && !built.lockReasons.some((reason) => reason.startsWith("Missing account(s):"))) {
          showValidationOverlay({ status: "success", title: "Validated", message: "SIMSOFT and Google Sheet preview are ready." }, true);
        } else {
          showValidationOverlay({ status: "error", title: "Validation Failed", message: "Please review the branch or account warning." }, true);
        }
      } else {
        setMessage("Preview data is ready.");
        showValidationOverlay({ status: "success", title: "Validated", message: "SIMSOFT file is ready." }, true);
      }
    } catch (error) {
      const message = operatorError(error, "SIMSOFT file could not be validated.");
      setResult({ rows: [], errors: [message], parser: "python-core" });
      setPreviewResult(null);
      setMessage(message);
      showValidationOverlay({ status: "error", title: "Validation Failed", message }, true);
    } finally {
      setBusy(false);
    }
  }

  const saveFolderUrl = useCallback(() => {
    const validation = validateGoogleFolderLink(folderUrl);
    if (!validation.ok) {
      setScanStatus(validation.reason === "empty" ? "idle" : "invalid");
      setScanError(validation.reason === "invalid" ? "Paste a valid Google Drive folder link." : "");
      setMessage("Paste a valid Google Drive folder link before saving.");
      return false;
    }
    window.localStorage.setItem(SAVED_FOLDER_URL_KEY, validation.normalizedUrl);
    setSavedFolderUrl(validation.normalizedUrl);
    setFolderUrl(validation.normalizedUrl);
    setScanResult(null);
    setSheetStats(null);
    setSheetStatsByBranch({});
    setSelectedBranchId("");
    setPreviewResult(null);
    setScanStatus("idle");
    setSheetUpdateStatus("idle");
    setScanSource("idle");
    setScanError("");
    setScanCompletedAt(null);
    lastScannedLink.current = "";
    setMessage("Drive folder link saved. Click Scan Folder when ready.");
    return true;
  }, [folderUrl]);

  const unsaveFolderUrl = useCallback(() => {
    window.localStorage.removeItem(SAVED_FOLDER_URL_KEY);
    setSavedFolderUrl("");
    setFolderUrl("");
    setScanResult(null);
    setSheetStats(null);
    setSheetStatsByBranch({});
    setSelectedBranchId("");
    setPreviewResult(null);
    setScanStatus("idle");
    setSheetUpdateStatus("idle");
    setScanSource("idle");
    setScanError("");
    setScanCompletedAt(null);
    lastScannedLink.current = "";
    setMessage("Saved Drive folder link removed.");
  }, []);

  const scanFolder = useCallback(async (forceRefresh = false, showDoneModal = false) => {
    const validation = validateGoogleFolderLink(folderUrl);
    if (!validation.ok) {
      setScanStatus(validation.reason === "empty" ? "idle" : "invalid");
      setScanError(validation.reason === "invalid" ? "Paste a valid Google Drive folder link." : "");
      return;
    }
    if (!forceRefresh && validation.normalizedUrl === lastScannedLink.current && scanResult) {
      setScanStatus("completed");
      setScanSource("cached scan");
      setMessage("Using cached scan result.");
      return;
    }
    const requestId = scanRequestId.current + 1;
    scanRequestId.current = requestId;
    setScanStatus("scanning");
    setScanError("");
    setMessage("Scanning Drive folder...");
    try {
      const scanned = await scanService.scanFolder(validation.normalizedUrl, forceRefresh, {
        authMode: effectiveGoogleAuthMode,
        operatorIdentity
      });
      if (requestId !== scanRequestId.current) return;
      setScanResult(scanned.result);
      setScanSource(scanned.source);
      setScanCompletedAt(scanned.scannedAt);
      lastScannedLink.current = validation.normalizedUrl;
      if (!scanned.result.error) {
        window.localStorage.setItem(SAVED_FOLDER_URL_KEY, validation.normalizedUrl);
        setSavedFolderUrl(validation.normalizedUrl);
        setFolderUrl(validation.normalizedUrl);
      }
      const allowed = new Set(assignedBranchIds.map((branch) => branch.toUpperCase()));
      const scannedBranchIds = new Set(Object.values(scanned.result.branchIndex).map((branch) => branch.branch_id.toUpperCase()));
      const missingAssignedBranches =
        (isAdmin && !hasLimitedBranchAssignment) || allowed.has("*")
          ? []
          : assignedBranchIds.map((branch) => branch.toUpperCase()).filter((branch) => branch && !scannedBranchIds.has(branch));
      const accessibleBranches = Object.values(scanned.result.branchIndex).filter(
        (branch) => (isAdmin && !hasLimitedBranchAssignment) || allowed.has("*") || allowed.has(branch.branch_id.toUpperCase())
      );
      setSelectedBranchId(accessibleBranches.length === 1 ? accessibleBranches[0].branch_id : "");
      setPreviewResult(null);
      setSheetStats(null);
      setSheetStatsByBranch({});
      setSheetUpdateStatus("idle");
      if (scanned.result.error) {
        setScanStatus("error");
        setScanError(scanned.result.error);
        setMessage(safeDisplayText(scanned.result.error));
      } else if (scanned.result.branchCount) {
        setScanStatus("completed");
        if (missingAssignedBranches.length) {
          const missingText = missingAssignedBranches.join(", ");
          const uploadMessage = `${missingText} ${missingAssignedBranches.length === 1 ? "branch is" : "branches are"} not yet uploaded.`;
          setBranchUploadMessage(uploadMessage);
          setMessage(uploadMessage);
        } else {
          setBranchUploadMessage("");
          setMessage(`Found ${scanned.result.branchCount} branch sheets.`);
        }
        if (showDoneModal) setActiveModal(missingAssignedBranches.length ? "branchNotUploaded" : "rescanDone");
      } else {
        setScanStatus("completed");
        if (missingAssignedBranches.length) {
          const missingText = missingAssignedBranches.join(", ");
          const uploadMessage = `${missingText} ${missingAssignedBranches.length === 1 ? "branch is" : "branches are"} not yet uploaded.`;
          setBranchUploadMessage(uploadMessage);
          setMessage(uploadMessage);
        } else {
          setBranchUploadMessage("");
          setMessage("No branch sheets found.");
        }
        if (showDoneModal) setActiveModal(missingAssignedBranches.length ? "branchNotUploaded" : "rescanDone");
      }
    } catch (error) {
      if (requestId !== scanRequestId.current) return;
      const message = operatorError(error, "Folder scan could not be completed.");
      setScanStatus("error");
      setScanError(message);
      setMessage(message);
    }
  }, [assignedBranchIds, effectiveGoogleAuthMode, folderUrl, hasLimitedBranchAssignment, isAdmin, operatorIdentity, scanResult]);

  useEffect(() => {
    const validation = validateGoogleFolderLink(folderUrl);
    if (!validation.ok) {
      setScanStatus(validation.reason === "empty" ? "idle" : "invalid");
      setScanError(validation.reason === "invalid" ? "Paste a valid Google Drive folder link." : "");
    } else if (scanStatus === "invalid") {
      setScanStatus("idle");
      setScanError("");
    }
  }, [folderUrl, scanStatus]);

  async function buildGooglePreviews(showDoneModal = false): Promise<GoogleSheetPreviewResult | null> {
    const selectedFilePaths = filePaths.length ? filePaths : filePath ? [filePath] : [];
    if (!selectedFilePaths.length) {
      setMessage("Choose and validate one or more SIMSOFT Excel files first.");
      return null;
    }
    if (!folderUrl || !scanResult) {
      setMessage("Scan the Google Drive branch folder first.");
      return null;
    }
    if (!selectedBranchId) {
      setMessage("Select a target branch first.");
      return null;
    }
    if (!operatorIdentity?.signedIn) {
      setMessage("Google operator login is required before building previews.");
      return null;
    }
    if (!selectedBranchSheetUpdated) {
      setMessage("Click Update Sheet for the selected branch before validating accounts.");
      setActiveModal("updateSheetFirst");
      return null;
    }
    setIsGeneratingPreview(true);
    setMessage("Loading Google Sheet tabs and building previews...");
    try {
      const built = await simsoftApi.buildGooglePreviews({
        filePath,
        filePaths: selectedFilePaths,
        folderUrl,
        branchId: selectedBranchId,
        branchIndex: scanResult.branchIndex,
        authMode: effectiveGoogleAuthMode,
        operatorIdentity
      });
      setPreviewResult(built);
      setSheetStats({
        targetBranchId: built.sheet.targetBranchId,
        targetBranchName: built.sheet.targetBranchName,
        targetSpreadsheetId: built.sheet.targetSpreadsheetId,
        accountsRowCount: built.sheet.accountsRowCount ?? built.accountsPreviewRows.length,
        googleReady: built.sheet.googleReady,
        error: built.error
      });
      setSheetStatsByBranch((current) => ({
        ...current,
        [built.sheet.targetBranchId]: {
          targetBranchId: built.sheet.targetBranchId,
          targetBranchName: built.sheet.targetBranchName,
          targetSpreadsheetId: built.sheet.targetSpreadsheetId,
          accountsRowCount: built.sheet.accountsRowCount ?? built.accountsPreviewRows.length,
          googleReady: built.sheet.googleReady,
          error: built.error
        }
      }));
      setSheetUpdateStatus(built.sheet.googleReady ? "completed" : "error");
      setPostStatus("");
      setResult((current) =>
        current
          ? { ...current, rows: built.parsedRows, errors: built.errors, summary: built.summary }
          : { rows: built.parsedRows, errors: built.errors, summary: built.summary, parser: "python-core" }
      );
      setActiveTab("ACCOUNTS");
      if (built.error) {
        setMessage(built.error);
      } else if (built.lockReasons.includes("Wrong branch")) {
        setMessage("Wrong branch selected. Choose the matching target branch.");
        setActiveModal("wrongBranch");
      } else if (built.lockReasons.some((reason) => reason.startsWith("Missing account(s):"))) {
        setMessage("Missing account found in selected branch ACCOUNTS tab.");
        setActiveModal("missingAccount");
      } else if (built.sheet.googleReady) {
        setMessage("Google Sheet previews are ready.");
        if (showDoneModal) setActiveModal("updateDone");
      } else {
        setMessage("Google Sheet connection is not ready.");
      }
      return built;
    } catch (error) {
      const message = operatorError(error, "Google Sheet previews could not be built.");
      setPreviewResult({
        parsedRows: [],
        accountsPreviewRows: [],
        receiptPreviewRows: [],
        dailyPreviewRows: [],
        scrPreviewRows: [],
        fullyPaidCashRows: [],
        scrUpdates: [],
        sheetLayouts: {},
        aiResolver: {
          enabled: false,
          status: "skipped",
          model: "",
          summary: "",
          suggestions: [],
          warnings: [],
          error: ""
        },
        errors: [message],
        lockReasons: [message],
        summary: {},
        sheet: {
          targetBranchId: selectedBranchId,
          targetBranchName: "",
          targetSpreadsheetId: "",
          activeReceiptTab: "",
          activeDailyTab: "",
          googleReady: false
        },
        cache: {},
        performanceTimings: {},
        canPost: false,
        postLockReason: message,
        error: message
      });
      setMessage(message);
      return null;
    } finally {
      setIsGeneratingPreview(false);
    }
  }

  async function updateGoogleSheet() {
    if (!folderUrl || !scanResult) {
      setMessage("Scan the Google Drive branch folder first.");
      return;
    }
    if (!selectedBranchId) {
      setMessage("Select a target branch first.");
      return;
    }
    if (!operatorIdentity?.signedIn) {
      setMessage("Google operator login is required before updating the selected sheet.");
      return;
    }
    setSheetUpdateStatus("loading");
    setMessage("Loading selected branch ACCOUNTS tab...");
    try {
      const stats = await simsoftApi.getGoogleSheetStats({
        folderUrl,
        branchId: selectedBranchId,
        branchIndex: scanResult.branchIndex,
        authMode: effectiveGoogleAuthMode,
        operatorIdentity
      });
      setSheetStats(stats);
      if (stats.targetBranchId) {
        setSheetStatsByBranch((current) => ({
          ...current,
          [stats.targetBranchId]: stats
        }));
      }
      if (stats.error) {
        setSheetUpdateStatus("error");
        setMessage(stats.error);
        return;
      }
      setSheetUpdateStatus("completed");
      setMessage(`${stats.accountsRowCount} ACCOUNTS row(s) loaded from selected branch.`);
      setActiveModal("updateDone");
      if ((filePath || filePaths.length) && result) {
        await buildGooglePreviews(false);
      }
    } catch (error) {
      setSheetUpdateStatus("error");
      setMessage(operatorError(error, "Selected Google Sheet could not be updated."));
    }
  }

  async function postGooglePreviews() {
    const selectedFilePaths = filePaths.length ? filePaths : filePath ? [filePath] : [];
    if (!selectedFilePaths.length || !folderUrl || !selectedBranchId || !scanResult || !previewResult) {
      setMessage("Build and review Google previews before posting.");
      setActiveModal("postBlocked");
      return;
    }
    if (!operatorIdentity?.signedIn) {
      setMessage("Google operator login is required before posting.");
      setActiveModal("postBlocked");
      return;
    }
    if (!governance.canFinalizePosting) {
      setMessage("Admin approval is required to finalize postings.");
      setActiveModal("postBlocked");
      return;
    }
    if (!previewResult.canPost || previewResult.errors.length || previewResult.lockReasons.length || !hasNewRowsToPost) {
      setMessage(previewResult.postLockReason || previewResult.lockReasons[0] || "Posting blocked. Resolve duplicates or validation errors first.");
      setActiveModal("postBlocked");
      return;
    }
    if (ibpReviewRequired) {
      setMessage("Enter IBP particulars and MI amount in the IBP to Other Branch card before posting.");
      setActiveModal(null);
      return;
    }
    setIsPosting(true);
    setMessage("Posting to Google Sheets...");
    try {
      const posted = await postService.postGooglePreviews({
        filePath,
        filePaths: selectedFilePaths,
        folderUrl,
        branchId: selectedBranchId,
        branchIndex: scanResult.branchIndex,
        ibpParticulars,
        ibpPaymentBreakdowns,
        authMode: effectiveGoogleAuthMode,
        operatorIdentity
      });
      setPreviewResult(posted);
      const duplicateOnlyMessage =
        posted.postedCount === 0 && duplicateRowCount > 0
          ? "No new transactions were posted because every SIMSOFT row is already marked as duplicate."
          : `${posted.lastPostStatus || "POSTED"} - saved ${posted.postedCount} history row(s).`;
      setPostStatus(posted.error ? posted.error : duplicateOnlyMessage);
      setMessage(posted.error ? posted.error : "Posting finished.");
      setActiveModal(posted.error ? null : "postAgain");
    } catch (error) {
      const message = operatorError(error, "Posting could not be completed.");
      setPostStatus(`ERROR - ${message}`);
      setMessage(message);
      setActiveModal(null);
    } finally {
      setIsPosting(false);
    }
  }

  async function clearCache() {
    if (!isAdmin) {
      setMessage("Admin access is required for this action.");
      return;
    }
    setIsLoadingCache(true);
    try {
      await simsoftApi.clearCache(operatorIdentity);
      cacheService.clearLocalCaches();
      lastScannedLink.current = "";
      setScanResult(null);
      setSheetStats(null);
      setSheetStatsByBranch({});
      setSelectedBranchId("");
      setResult(null);
      setPreviewResult(null);
      setSheetUpdateStatus("idle");
      setScanStatus(folderLinkValidation.ok ? "idle" : "invalid");
      setScanCompletedAt(null);
      setScanSource("idle");
      setMessage("Cache cleared.");
      setActiveModal("clearCacheDone");
    } catch (error) {
      setMessage(operatorError(error, "Cache could not be cleared."));
    } finally {
      setIsLoadingCache(false);
    }
  }

  function prepareNextPost() {
    setFilePath("");
    setFilePaths([]);
    setResult(null);
    setPreviewResult(null);
    setSheetStats(null);
    setActiveTab("SIMSOFT");
    setPostStatus("");
    setActiveModal(null);
    setMessage("Ready for the next batch.");
  }

  async function copyServiceAccountEmail() {
    const email = scanResult?.serviceAccountEmail;
    if (!email) {
      setMessage("Scan the Google Drive folder first to load the service account email.");
      return;
    }
    try {
      await navigator.clipboard.writeText(email);
      setMessage("Service account email copied.");
      showToast("Copied successfully");
    } catch {
      setMessage(email);
    }
  }

  async function runHealthCheck() {
    setActiveModal("healthCheckResult");
    setBusy(true);
    setMessage("Running health check...");
    try {
      const checked = await simsoftApi.runHealthCheck();
      setHealthCheck(checked);
      refreshStatus();
      setMessage(checked.ok ? "Health check passed." : "Health check needs attention.");
      setActiveModal("healthCheckResult");
    } catch (error) {
      setMessage(operatorError(error, "Health check could not be completed."));
    } finally {
      setBusy(false);
    }
  }

  async function openGoogleTestUsersPage() {
    if (!isAdmin) {
      setMessage("Admin access is required for this action.");
      return;
    }
    try {
      await simsoftApi.openGoogleTestUsersPage(operatorIdentity);
      setMessage("Opened Google Cloud test users page.");
      setActiveModal(null);
    } catch (error) {
      setMessage(operatorError(error, "Google Cloud test users page could not be opened."));
    }
  }

  async function requestAccess(input: { email: string; name?: string }) {
    const email = input.email.trim().toLowerCase();
    if (!email) {
      setMessage("Enter your Google email before requesting access.");
      return;
    }
    try {
      setBusy(true);
      setMessage("Opening access request email...");
      const requested = await simsoftApi.requestAccess({ email, name: input.name?.trim() });
      if (!requested.ok) {
        setMessage(requested.error || "Access request could not be created.");
        return;
      }
      setMessage(`Access request sent to admin${requested.recipients.length ? `: ${requested.recipients.join(", ")}` : ""}.`);
      refreshStatus();
      showToast("Access request sent");
    } catch (error) {
      setMessage(operatorError(error, "Access request could not be created."));
    } finally {
      setBusy(false);
    }
  }

  async function openSupportFolder(kind: "config" | "data" | "logs") {
    try {
      const opened = await simsoftApi.openSupportFolder(kind, operatorIdentity);
      setMessage(opened.ok ? `Opened ${kind} folder.` : opened.error || `Could not open ${kind} folder.`);
    } catch (error) {
      setMessage(operatorError(error, `Could not open ${kind} folder.`));
    }
  }

  async function saveAccessConfig(input: {
    adminEmails: string[];
    memberEmails: string[];
    userBranches: Record<string, string[]>;
    accessRequests?: AppStatus["accessRequests"];
    successMessage?: string;
    successToast?: string;
  }): Promise<boolean> {
    if (!isAdmin) {
      setMessage("Admin access is required for this action.");
      return false;
    }
    try {
      const nextStatus = await simsoftApi.saveAccessConfig(input, operatorIdentity);
      setStatus(nextStatus);
      setMessage(input.successMessage ?? "Branch assignments saved.");
      showToast(input.successToast ?? "Assigned successfully");
      return true;
    } catch (error) {
      setMessage(operatorError(error, "Branch assignments could not be saved."));
      return false;
    }
  }

  async function loginGoogleOperator() {
    setIsAuthenticating(true);
    setMessage("Opening Google login...");
    try {
      const operator = await authService.loginGoogleOperator();
      const savedOperator = operator.signedIn ? operator : await authService.getOperatorIdentity();
      setOperatorIdentity(savedOperator);
      setMessage(savedOperator.error ? savedOperator.error : `Signed in as ${savedOperator.email}.`);
    } catch (error) {
      try {
        const savedOperator = await authService.getOperatorIdentity();
        setOperatorIdentity(savedOperator);
        setMessage(savedOperator.signedIn ? `Signed in as ${savedOperator.email}.` : operatorError(error, "Google login could not be completed."));
      } catch {
        setMessage(operatorError(error, "Google login could not be completed."));
      }
    } finally {
      setIsAuthenticating(false);
    }
  }

  async function logoutGoogleOperator() {
    setIsAuthenticating(true);
    setMessage("Signing out Google operator...");
    try {
      const operator = await authService.logoutGoogleOperator();
      setOperatorIdentity(operator);
      setPreviewResult(null);
      setResult(null);
      setPostStatus("");
      setMessage(operator.error ? operator.error : "Google operator signed out.");
      setActiveModal(null);
    } catch (error) {
      setMessage(operatorError(error, "Google logout could not be completed."));
    } finally {
      setIsAuthenticating(false);
    }
  }

  async function resetDuplicateHistory() {
    if (!duplicateResetConfirmed) return;
    if (!isAdmin) {
      setMessage("Admin access is required for this action.");
      return;
    }
    setBusy(true);
    setMessage("Resetting local duplicate history...");
    try {
      const reset = await simsoftApi.resetDuplicateHistory("Reset Duplicate History", operatorIdentity);
      setDuplicateStatus(reset);
      setPreviewResult(null);
      setResult(null);
      setPostStatus("");
      setDuplicateResetText("");
      setActiveModal(null);
      setMessage(reset.error ? reset.error : "Local duplicate history was reset. Rebuild Google previews.");
    } catch (error) {
      setMessage(operatorError(error, "Duplicate history could not be reset."));
    } finally {
      setBusy(false);
    }
  }

  return {
    state: {
      status,
      filePath,
      filePaths,
      folderUrl,
      savedFolderUrl,
      scanResult,
      sheetStats,
      sheetStatsByBranch,
      selectedBranchId,
      result,
      previewResult,
      activeTab,
      postStatus,
      duplicateStatus,
      healthCheck,
      ibpParticulars,
      ibpPaymentBreakdowns,
      operatorIdentity,
      duplicateResetText,
      activeModal,
      busy,
      isScanning: scanStatus === "scanning",
      isPosting,
      isAuthenticating,
      isGeneratingPreview,
      isLoadingCache,
      showPostingGateDetails,
      showAdvancedSettings,
      scanStatus,
      sheetUpdateStatus,
      scanSource,
      scanError,
      scanCompletedAt,
      toastMessage,
      validationOverlay,
      folderLinkValidation,
      effectiveGoogleAuthMode,
      userRole,
      isAdmin,
      assignedBranchIds,
      governanceUser,
      governance,
      setupComplete,
      ibpReviewRequired,
      branchUploadMessage,
      message
    },
    derived: {
      summaryRows,
      branchOptions,
      activeRows,
      activeColumns,
      previewCounts,
      passedRowCount,
      duplicateRowCount,
      hasNewRowsToPost,
      setupChecklist,
      emptyPreviewMessage,
      ibpReviewRows,
      duplicateResetConfirmed
    },
    actions: {
      setFilePath: updateFilePath,
      setFolderUrl,
      saveFolderUrl,
      unsaveFolderUrl,
      setSelectedBranchId: (branchId: string) => {
        setSelectedBranchId(branchId);
        setPreviewResult(null);
        setSheetStats(branchId ? sheetStatsByBranch[branchId] ?? null : null);
        setSheetUpdateStatus("idle");
      },
      setActiveTab,
      setDuplicateResetText,
      setIbpParticulars,
      setIbpPaymentBreakdowns,
      setActiveModal,
      setShowPostingGateDetails,
      setShowAdvancedSettings,
      loginGoogleOperator,
      logoutGoogleOperator,
      chooseFile,
      parseFile,
      scanFolder,
      refreshScan: () => scanFolder(true, true),
      buildGooglePreviews,
      updateGoogleSheet,
      postGooglePreviews,
      prepareNextPost,
      copyServiceAccountEmail,
      clearCache,
      runHealthCheck,
      requestAccess,
      openSupportFolder,
      openGoogleTestUsersPage,
      saveAccessConfig,
      resetDuplicateHistory
    }
  };
}

export type SimsoftDashboardModel = ReturnType<typeof useSimsoftDashboard>;
