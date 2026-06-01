import { invoke } from "@tauri-apps/api/core";
import {
  AppStatus,
  AuthMode,
  BranchInfo,
  DuplicateHistoryStatus,
  FolderScanResult,
  GoogleSheetPreviewResult,
  GoogleSheetStats,
  HealthCheckResult,
  IbpPaymentBreakdowns,
  IbpParticulars,
  OperatorIdentity,
  ParseResult,
  PostingResult,
  SimsoftApi
} from "../shared/types";

const api: SimsoftApi = {
  getStatus: () => invoke<AppStatus>("app_get_status"),
  saveAccessConfig: (input, operatorIdentity) => invoke<AppStatus>("app_save_access_config", { input, operatorIdentity }),
  requestAccess: (input) => invoke<{ ok: boolean; url: string; recipients: string[]; error?: string }>("app_request_access", { input }),
  openGoogleTestUsersPage: (operatorIdentity) => invoke<{ ok: boolean; url: string }>("app_open_google_test_users_page", { operatorIdentity }),
  openSupportFolder: (kind, operatorIdentity) => invoke<{ ok: boolean; path: string; error?: string }>("app_open_support_folder", { kind, operatorIdentity }),
  chooseSimsoftFile: () => invoke<string | null>("dialog_choose_simsoft_file"),
  chooseSimsoftFiles: () => invoke<string[]>("dialog_choose_simsoft_files"),
  parseSimsoftFile: (filePath: string) => invoke<ParseResult>("simsoft_parse_file", { filePath }),
  parseSimsoftFiles: (filePaths: string[]) => invoke<ParseResult>("simsoft_parse_files", { input: { filePaths } }),
  scanGoogleFolder: (input: { folderUrl: string; authMode?: AuthMode; operatorIdentity?: OperatorIdentity | null }) =>
    invoke<FolderScanResult>("google_scan_folder", { input }),
  getGoogleSheetStats: (input: {
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }) => invoke<GoogleSheetStats>("google_get_sheet_stats", { input }),
  buildGooglePreviews: (input: {
    filePath: string;
    filePaths?: string[];
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: AuthMode;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }) => invoke<GoogleSheetPreviewResult>("google_build_previews", { input }),
  postGooglePreviews: (input: {
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
  }) => invoke<PostingResult>("google_post_previews", { input }),
  getOperatorIdentity: () => invoke<OperatorIdentity>("operator_get_identity"),
  loginGoogleOperator: () => invoke<OperatorIdentity>("operator_login_google"),
  logoutGoogleOperator: () => invoke<OperatorIdentity>("operator_logout_google"),
  getDuplicateHistoryStatus: () => invoke<DuplicateHistoryStatus>("duplicates_get_status"),
  resetDuplicateHistory: (confirmation: string, operatorIdentity?: OperatorIdentity | null) =>
    invoke<DuplicateHistoryStatus>("duplicates_reset", { confirmation, operatorIdentity }),
  clearCache: (operatorIdentity?: OperatorIdentity | null) => invoke<{ ok: boolean }>("cache_clear", { operatorIdentity }),
  runHealthCheck: () => invoke<HealthCheckResult>("app_health_check")
};

window.simsoft = api;
