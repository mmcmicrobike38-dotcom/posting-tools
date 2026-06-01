export type AuthMode = "service_account" | "user_oauth";
export type UserRole = "admin" | "member";

export interface ScanProgress {
  currentFile: string;
  totalFiles: number;
  completedFiles: number;
  failedFiles: number;
  percent: number;
}

export interface PerformanceReport {
  scanDurationMs: number;
  cacheHits: number;
  cacheMisses: number;
  failedFileCount: number;
  perFileDurationsMs: Record<string, number>;
  googleRequestDurationsMs: Record<string, number>;
}

export interface ParseResult {
  rows: Record<string, unknown>[];
  errors: string[];
  summary?: Record<string, unknown>;
  parser: "python-core";
  performance?: PerformanceReport;
}

export interface AiPostingResolverSuggestion {
  tab: string;
  severity: "review" | "warning" | "blocker" | string;
  rowKey: string;
  issue: string;
  suggestion: string;
  confidence: number;
  proposedUpdates: Record<string, unknown>[];
  reason: string;
}

export interface AiPostingResolverReport {
  enabled: boolean;
  status: "disabled" | "skipped" | "ready" | "error" | string;
  model: string;
  summary: string;
  suggestions: AiPostingResolverSuggestion[];
  warnings: string[];
  error?: string;
}

export interface SheetLayoutPreview {
  rows: unknown[][];
  updatedCells: Array<{
    row: number;
    col: number;
    kind?: string;
    previousValue: unknown;
    value: unknown;
  }>;
}

export interface GoogleSheetPreviewResult {
  parsedRows: Record<string, unknown>[];
  accountsPreviewRows: Record<string, unknown>[];
  receiptPreviewRows: Record<string, unknown>[];
  dailyPreviewRows: Record<string, unknown>[];
  scrPreviewRows: Record<string, unknown>[];
  fullyPaidCashRows: Record<string, unknown>[];
  scrUpdates: Record<string, unknown>[];
  sheetLayouts?: Record<string, SheetLayoutPreview>;
  aiResolver?: AiPostingResolverReport;
  errors: string[];
  lockReasons: string[];
  summary: Record<string, unknown>;
  sheet: {
    targetBranchId: string;
    targetBranchName: string;
    targetSpreadsheetId: string;
    activeReceiptTab: string;
    activeDailyTab: string;
    googleReady: boolean;
    accountsRowCount?: number;
  };
  cache: Record<string, unknown>;
  performanceTimings: Record<string, number>;
  canPost: boolean;
  postLockReason: string;
  error?: string;
}

export interface PostingResult extends GoogleSheetPreviewResult {
  postedCount: number;
  postedAt: string;
  lastPostStatus: string;
}

export type IbpParticulars = Record<string, string>;

export interface IbpPaymentBreakdown {
  rebate: string;
  amount: string;
  penalty: string;
}

export type IbpPaymentBreakdowns = Record<string, IbpPaymentBreakdown>;

export interface DuplicateHistoryStatus {
  duplicateHistoryPath: string;
  duplicateTransactionCount: number;
  postedBatchRowCount: number;
  backups?: string[];
  error?: string;
}

export interface OperatorIdentity {
  email: string;
  name: string;
  signedIn: boolean;
  tokenUserEmail: string;
  authMode: AuthMode;
  error?: string;
}

export interface KnownOperator {
  email: string;
  name: string;
  firstSeenAt: string;
  lastSeenAt: string;
}

export interface AccessRequest {
  email: string;
  name: string;
  requestedAt: string;
  lastRequestedAt: string;
  status: "pending";
}

export interface BranchInfo {
  branch_id: string;
  branch_name: string;
  spreadsheet_id: string;
  file_name: string;
  modified_time?: string;
  status?: string;
  issue?: string;
  matching_file_names?: string[];
}

export interface FolderScanResult {
  branchIndex: Record<string, BranchInfo>;
  serviceAccountEmail: string;
  branchCount: number;
  duplicateWarnings: string[];
  error?: string;
  performance?: PerformanceReport;
}

export interface GoogleSheetStats {
  targetBranchId: string;
  targetBranchName: string;
  targetSpreadsheetId: string;
  accountsRowCount: number;
  googleReady: boolean;
  error?: string;
}

export interface AppStatus {
  appName: string;
  appVersion: string;
  authMode: AuthMode;
  configDir: string;
  configReady: boolean;
  credentialStatus: Array<{
    fileName: string;
    path: string;
    required: boolean;
    ok: boolean;
    message: string;
  }>;
  cachePath: string;
  duplicateHistoryPath: string;
  postedBatchesPath: string;
  postingLocksPath: string;
  accessControlPath: string;
  logDir: string;
  serviceAccountJsonPath: string;
  oauthClientJsonPath: string;
  oauthTokenDir: string;
  adminEmails: string[];
  memberEmails: string[];
  userBranches: Record<string, string[]>;
  knownOperators: KnownOperator[];
  accessRequests: AccessRequest[];
  livePostingSource: "python-core-settings";
  bullMqEnabled: false;
  requireUserOAuthForPosting?: boolean;
  sharedStorageConfigured: boolean;
  cloudEndpointConfigured: boolean;
}

export interface HealthCheckItem {
  label: string;
  ok: boolean;
  detail: string;
}

export interface HealthCheckResult {
  checkedAt: string;
  ok: boolean;
  items: HealthCheckItem[];
}

export interface SimsoftApi {
  getStatus(): Promise<AppStatus>;
  saveAccessConfig(
    input: {
      adminEmails: string[];
      memberEmails: string[];
      userBranches: Record<string, string[]>;
      accessRequests?: AccessRequest[];
    },
    operatorIdentity?: OperatorIdentity | null
  ): Promise<AppStatus>;
  requestAccess(input: { email: string; name?: string }): Promise<{ ok: boolean; url: string; recipients: string[]; error?: string }>;
  openGoogleTestUsersPage(operatorIdentity?: OperatorIdentity | null): Promise<{ ok: boolean; url: string }>;
  openSupportFolder(kind: "config" | "data" | "logs", operatorIdentity?: OperatorIdentity | null): Promise<{ ok: boolean; path: string; error?: string }>;
  chooseSimsoftFile(): Promise<string | null>;
  chooseSimsoftFiles(): Promise<string[]>;
  parseSimsoftFile(filePath: string): Promise<ParseResult>;
  parseSimsoftFiles(filePaths: string[]): Promise<ParseResult>;
  scanGoogleFolder(input: {
    folderUrl: string;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
  }): Promise<FolderScanResult>;
  getGoogleSheetStats(input: {
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<GoogleSheetStats>;
  buildGooglePreviews(input: {
    filePath: string;
    filePaths?: string[];
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<GoogleSheetPreviewResult>;
  postGooglePreviews(input: {
    filePath: string;
    filePaths?: string[];
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    confirmation: string;
    ibpParticulars?: IbpParticulars;
    ibpPaymentBreakdowns?: IbpPaymentBreakdowns;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<PostingResult>;
  getOperatorIdentity(): Promise<OperatorIdentity>;
  loginGoogleOperator(): Promise<OperatorIdentity>;
  logoutGoogleOperator(): Promise<OperatorIdentity>;
  getDuplicateHistoryStatus(): Promise<DuplicateHistoryStatus>;
  resetDuplicateHistory(confirmation: string, operatorIdentity?: OperatorIdentity | null): Promise<DuplicateHistoryStatus>;
  clearCache(operatorIdentity?: OperatorIdentity | null): Promise<{ ok: boolean }>;
  runHealthCheck(): Promise<HealthCheckResult>;
}

declare global {
  interface Window {
    simsoft: SimsoftApi;
  }
}
