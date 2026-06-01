import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { appConfig } from "../config";
import { logger } from "../logging/logger";
import {
  BranchInfo,
  DuplicateHistoryStatus,
  FolderScanResult,
  GoogleSheetStats,
  GoogleSheetPreviewResult,
  OperatorIdentity,
  ParseResult,
  PostingResult
} from "../../shared/types";

interface BridgeResponse<T> {
  ok: boolean;
  result?: T;
  error?: string;
}

function parseBridgeResponse<T>(stdout: string): BridgeResponse<T> {
  const trimmed = stdout.trim();
  try {
    return JSON.parse(trimmed) as BridgeResponse<T>;
  } catch {
    const jsonStart = trimmed.lastIndexOf('{"ok"');
    if (jsonStart >= 0) {
      return JSON.parse(trimmed.slice(jsonStart)) as BridgeResponse<T>;
    }
    throw new Error("Python bridge returned invalid JSON.");
  }
}

function existingPath(candidates: string[]): string | null {
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? null;
}

export function packagedBridgeExecutable(): string | null {
  if (process.env.SIMSOFT_PYTHON_BRIDGE_EXE) {
    return existingPath([process.env.SIMSOFT_PYTHON_BRIDGE_EXE]);
  }
  const resourceRoot = process.env.SIMSOFT_RESOURCE_DIR || "";
  if (!resourceRoot && process.env.SIMSOFT_PACKAGED !== "1") {
    return null;
  }
  return existingPath([
    path.join(resourceRoot, "python_bridge", "simsoft-python-bridge.exe"),
    path.resolve("dist-python", "simsoft-python-bridge", "simsoft-python-bridge.exe")
  ].filter(Boolean));
}

async function callBridge<T>(payload: Record<string, unknown>): Promise<T> {
  const bridgeExe = packagedBridgeExecutable();
  const scriptPath = path.resolve("scripts", "python_bridge.py");
  const command = bridgeExe ?? appConfig.pythonExecutable;
  const args = bridgeExe ? [] : [scriptPath];
  const started = performance.now();
  return await new Promise<T>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env: {
        ...process.env,
        SIMSOFT_SERVICE_ACCOUNT_JSON_PATH: appConfig.serviceAccountJsonPath,
        SIMSOFT_OAUTH_CLIENT_JSON_PATH: appConfig.oauthClientJsonPath,
        SIMSOFT_OAUTH_TOKEN_DIR: appConfig.oauthTokenDir,
        SIMSOFT_DUPLICATE_HISTORY_PATH: appConfig.duplicateHistoryPath,
        SIMSOFT_POSTED_BATCHES_PATH: appConfig.postedBatchesPath,
        SIMSOFT_POSTING_LOCKS_PATH: appConfig.postingLocksPath,
        SIMSOFT_LOG_DIR: appConfig.logDir
      },
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      logger.info("Python bridge completed", { command: payload.command, durationMs: performance.now() - started, exitCode: code });
      try {
        const response = parseBridgeResponse<T>(stdout);
        if (response.ok && response.result !== undefined) {
          resolve(response.result);
        } else {
          reject(new Error(response.error || stderr || "Python bridge failed."));
        }
      } catch (error) {
        reject(new Error(stderr || (error instanceof Error ? error.message : String(error))));
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

export async function parseWithPythonBackend(filePath: string, duplicateHistory: string[] = []): Promise<ParseResult> {
  return await callBridge<ParseResult>({
    command: "parse_simsoft",
    filePath,
    duplicateHistory
  });
}

export async function scanFolderWithPythonBackend(input: {
  folderUrl: string;
  authMode?: string;
  operatorIdentity?: OperatorIdentity | null;
}): Promise<FolderScanResult> {
  return await callBridge<FolderScanResult>({
    command: "scan_google_folder",
    ...input
  });
}

export async function buildPreviewsWithPythonBackend(input: {
  filePath: string;
  folderUrl: string;
  branchId: string;
  branchIndex: Record<string, BranchInfo>;
  authMode?: string;
  operatorIdentity?: OperatorIdentity | null;
  testMode?: boolean;
}): Promise<GoogleSheetPreviewResult> {
  return await callBridge<GoogleSheetPreviewResult>({
    command: "build_google_previews",
    ...input
  });
}

export async function getSheetStatsWithPythonBackend(input: {
  folderUrl: string;
  branchId: string;
  branchIndex: Record<string, BranchInfo>;
  authMode?: string;
  operatorIdentity?: OperatorIdentity | null;
  testMode?: boolean;
}): Promise<GoogleSheetStats> {
  return await callBridge<GoogleSheetStats>({
    command: "google_sheet_stats",
    ...input
  });
}

export async function postWithPythonBackend(input: {
  filePath: string;
  folderUrl: string;
  branchId: string;
  branchIndex: Record<string, BranchInfo>;
  confirmation: string;
  ibpParticulars?: Record<string, string>;
  ibpPaymentBreakdowns?: Record<string, { rebate?: string; amount?: string; penalty?: string }>;
  authMode?: string;
  operatorIdentity?: OperatorIdentity | null;
  testMode?: boolean;
}): Promise<PostingResult> {
  return await callBridge<PostingResult>({
    command: "post_google_previews",
    ...input
  });
}

export async function getOperatorIdentityWithPythonBackend(): Promise<OperatorIdentity> {
  return await callBridge<OperatorIdentity>({
    command: "operator_identity"
  });
}

export async function loginGoogleOperatorWithPythonBackend(): Promise<OperatorIdentity> {
  return await callBridge<OperatorIdentity>({
    command: "operator_login_google"
  });
}

export async function logoutGoogleOperatorWithPythonBackend(): Promise<OperatorIdentity> {
  return await callBridge<OperatorIdentity>({
    command: "operator_logout_google"
  });
}

export async function getDuplicateHistoryStatusWithPythonBackend(): Promise<DuplicateHistoryStatus> {
  return await callBridge<DuplicateHistoryStatus>({
    command: "duplicate_history_status"
  });
}

export async function resetDuplicateHistoryWithPythonBackend(confirmation: string): Promise<DuplicateHistoryStatus> {
  return await callBridge<DuplicateHistoryStatus>({
    command: "reset_duplicate_history",
    confirmation
  });
}
