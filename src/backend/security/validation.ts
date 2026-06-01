import fs from "node:fs";
import path from "node:path";
import { BranchInfo, OperatorIdentity } from "../../shared/types";
import { appConfig } from "../config";

const SAFE_SHEET_ID = /^[A-Za-z0-9_-]{20,}$/;
const SAFE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const SAFE_EXCEL_EXTENSIONS = new Set([".xlsx", ".xlsm"]);
const GOOGLE_HOSTS = new Set(["drive.google.com", "docs.google.com"]);
const DEFAULT_MAX_EXCEL_FILE_COUNT = 25;
const DEFAULT_MAX_EXCEL_TOTAL_MB = 100;

export function friendlyError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/credential|token|private_key|client_secret/i.test(message)) {
    return "Authentication configuration needs attention. Check settings and secure logs.";
  }
  return message || "The action could not be completed.";
}

export function validateFolderPath(folderPath: string): string {
  const resolved = path.resolve(folderPath);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    throw new Error("Folder path does not exist.");
  }
  return resolved;
}

export function validateExcelFilePath(filePath: string): string {
  const resolved = path.resolve(filePath);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
    throw new Error("SIMSOFT Excel file does not exist.");
  }
  if (!SAFE_EXCEL_EXTENSIONS.has(path.extname(resolved).toLowerCase())) {
    throw new Error("Only .xlsx and .xlsm files can be parsed.");
  }
  const maxBytes = appConfig.maxExcelFileMb * 1024 * 1024;
  const size = fs.statSync(resolved).size;
  if (size > maxBytes) {
    throw new Error(`Excel file is larger than the configured ${appConfig.maxExcelFileMb} MB limit.`);
  }
  return resolved;
}

export function validateExcelFilePaths(filePaths: unknown): string[] {
  const paths = Array.isArray(filePaths) ? filePaths : [filePaths];
  if (!paths.length) throw new Error("Choose at least one SIMSOFT Excel file.");
  const maxCount = Number(process.env.SIMSOFT_MAX_EXCEL_FILE_COUNT || DEFAULT_MAX_EXCEL_FILE_COUNT);
  if (paths.length > maxCount) throw new Error(`Choose ${maxCount} SIMSOFT Excel files or fewer.`);
  const resolved = paths.map((item) => validateExcelFilePath(assertString(item, "SIMSOFT Excel file is required.")));
  if (new Set(resolved).size !== resolved.length) throw new Error("Duplicate SIMSOFT Excel files are not allowed.");
  const totalMaxMb = Number(process.env.SIMSOFT_MAX_EXCEL_TOTAL_MB || DEFAULT_MAX_EXCEL_TOTAL_MB);
  const totalBytes = resolved.reduce((sum, filePath) => sum + fs.statSync(filePath).size, 0);
  if (totalBytes > totalMaxMb * 1024 * 1024) {
    throw new Error(`Selected Excel files are larger than the configured ${totalMaxMb} MB total limit.`);
  }
  return resolved;
}

export function assertNoPathTraversal(root: string, target: string): string {
  const resolvedRoot = path.resolve(root);
  const resolvedTarget = path.resolve(target);
  const relative = path.relative(resolvedRoot, resolvedTarget);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Unsafe path access was blocked.");
  }
  return resolvedTarget;
}

export function validateSheetId(value: string): string {
  const trimmed = value.trim();
  if (!SAFE_SHEET_ID.test(trimmed)) throw new Error("Invalid Google Sheet ID.");
  return trimmed;
}

export function validateEmail(value: string): string {
  const trimmed = value.trim();
  if (!SAFE_EMAIL.test(trimmed)) throw new Error("Invalid email address.");
  return trimmed;
}

export function validateGoogleFolderUrl(value: unknown): string {
  if (typeof value !== "string") throw new Error("Google folder link is required.");
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Google folder link is required.");
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Paste a valid Google Drive folder link.");
  }
  const host = parsed.hostname.replace(/^www\./, "");
  const hasDriveFolder = host === "drive.google.com" && /\/drive\/folders\/[A-Za-z0-9_-]+/.test(parsed.pathname);
  const hasDocsFolderParam = host === "docs.google.com" && Boolean(parsed.searchParams.get("folder"));
  if (!GOOGLE_HOSTS.has(host) || (!hasDriveFolder && !hasDocsFolderParam)) {
    throw new Error("Paste a valid Google Drive folder link.");
  }
  parsed.hash = "";
  return parsed.toString();
}

export function validatePostingPayload(payload: unknown): void {
  if (!payload || typeof payload !== "object") throw new Error("Posting data is required.");
  const input = payload as Record<string, unknown>;
  validateExcelFilePaths(input.filePaths ?? input.filePath);
  validateGoogleFolderUrl(input.folderUrl);
  const branchId = assertString(input.branchId, "Target branch is required.").trim();
  if (!/^[A-Za-z0-9_-]{3,32}$/.test(branchId)) throw new Error("Invalid target branch.");
  assertBranchIndex(input.branchIndex);
  if (input.authMode !== undefined && input.authMode !== "service_account" && input.authMode !== "user_oauth") {
    throw new Error("Invalid authentication mode.");
  }
  if (input.operatorIdentity !== undefined && input.operatorIdentity !== null) {
    assertOperatorIdentity(input.operatorIdentity);
  }
  if (input.confirmation !== undefined && input.confirmation !== "Continue Posting") {
    throw new Error("Final posting confirmation is required.");
  }
  if (input.ibpParticulars !== undefined) {
    assertIbpParticulars(input.ibpParticulars);
  }
  if (input.ibpPaymentBreakdowns !== undefined) {
    assertIbpPaymentBreakdowns(input.ibpPaymentBreakdowns);
  }
  if (input.testMode !== undefined && typeof input.testMode !== "boolean") {
    throw new Error("Invalid test mode flag.");
  }
}

export function validateDuplicateResetConfirmation(value: unknown): string {
  if (value !== "Reset Duplicate History") throw new Error("Reset confirmation is required.");
  return value;
}

function assertString(value: unknown, message: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(message);
  return value;
}

function assertIbpParticulars(value: unknown): asserts value is Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid IBP particulars.");
  for (const [key, particular] of Object.entries(value as Record<string, unknown>)) {
    if (typeof key !== "string" || key.length > 128) throw new Error("Invalid IBP particulars.");
    if (typeof particular !== "string") throw new Error("Invalid IBP particulars.");
    const trimmed = particular.trim();
    if (!trimmed || trimmed.length > 80 || /[\r\n]/.test(trimmed)) throw new Error("Invalid IBP particulars.");
  }
}

function assertIbpPaymentBreakdowns(value: unknown): void {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid IBP payment breakdowns.");
  for (const [key, breakdown] of Object.entries(value as Record<string, unknown>)) {
    if (typeof key !== "string" || key.length > 128) throw new Error("Invalid IBP payment breakdowns.");
    if (!breakdown || typeof breakdown !== "object" || Array.isArray(breakdown)) throw new Error("Invalid IBP payment breakdowns.");
    const item = breakdown as Record<string, unknown>;
    for (const field of ["rebate", "amount", "penalty"]) {
      const value = item[field];
      if (value === undefined) continue;
      if (typeof value !== "string" || value.length > 32 || /[\r\n]/.test(value)) throw new Error("Invalid IBP payment breakdowns.");
    }
  }
}

function assertBranchIndex(value: unknown): asserts value is Record<string, BranchInfo> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Branch scan data is required.");
  if (!Object.keys(value).length) throw new Error("Branch scan data is required.");
  for (const [branchId, branch] of Object.entries(value as Record<string, unknown>)) {
    if (!/^[A-Za-z0-9_-]{3,32}$/.test(branchId) || !branch || typeof branch !== "object") {
      throw new Error("Invalid branch scan data.");
    }
    const item = branch as Record<string, unknown>;
    assertString(item.branch_id, "Invalid branch scan data.");
    assertString(item.branch_name, "Invalid branch scan data.");
    validateSheetId(assertString(item.spreadsheet_id, "Invalid branch scan data."));
    assertString(item.file_name, "Invalid branch scan data.");
  }
}

function assertOperatorIdentity(value: unknown): asserts value is OperatorIdentity {
  if (!value || typeof value !== "object") throw new Error("Invalid operator identity.");
  const operator = value as Record<string, unknown>;
  if (typeof operator.signedIn !== "boolean") throw new Error("Invalid operator identity.");
  if (operator.authMode !== "service_account" && operator.authMode !== "user_oauth") throw new Error("Invalid operator identity.");
  if (operator.email !== "") validateEmail(assertString(operator.email, "Invalid operator identity."));
  if (operator.tokenUserEmail !== "") validateEmail(assertString(operator.tokenUserEmail, "Invalid operator identity."));
}
