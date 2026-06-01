import path from "node:path";
import fs from "node:fs";
import dotenv from "dotenv";

dotenv.config();

const existingPath = (candidates: string[]): string | null => candidates.find((candidate) => candidate && fs.existsSync(candidate)) ?? null;

const resourcePath = (...parts: string[]): string => path.join(process.env.SIMSOFT_RESOURCE_DIR || "", ...parts);
const localAppDataConfigPath = (fileName: string): string =>
  path.join(process.env.LOCALAPPDATA || process.cwd(), "SIMSOFT Posting", "config", fileName);

const defaultConfigPath = (fileName: string): string =>
  existingPath([
    process.env.SIMSOFT_CONFIG_DIR ? path.join(process.env.SIMSOFT_CONFIG_DIR, fileName) : "",
    localAppDataConfigPath(fileName),
    path.join("config", fileName),
    resourcePath("config", fileName)
  ]) ?? (process.env.SIMSOFT_CONFIG_DIR ? path.join(process.env.SIMSOFT_CONFIG_DIR, fileName) : localAppDataConfigPath(fileName));

const numberFromEnv = (name: string, fallback: number): number => {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const booleanFromEnv = (name: string, fallback = false): boolean => {
  const raw = process.env[name];
  if (!raw) return fallback;
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
};

const listFromEnv = (name: string): string[] =>
  (process.env[name] ?? "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);

const userBranchesFromEnv = (name: string): Record<string, string[]> => {
  const raw = process.env[name] ?? "";
  return Object.fromEntries(
    raw
      .split(";")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => {
        const [emailPart, branchesPart = ""] = entry.split(":");
        const email = emailPart.trim().toLowerCase();
        const branches = branchesPart
          .split(",")
          .map((branch) => branch.trim().toUpperCase())
          .filter(Boolean);
        return [email, branches] as const;
      })
      .filter(([email, branches]) => email && branches.length)
  );
};

const defaultPythonExecutable = (): string => {
  const localVenvPython = path.resolve(".venv", "Scripts", "python.exe");
  if (fs.existsSync(localVenvPython)) return localVenvPython;
  return "python";
};

export const appConfig = {
  authMode: process.env.SIMSOFT_AUTH_MODE === "service_account" ? "service_account" : "user_oauth",
  serviceAccountJsonPath: process.env.SIMSOFT_SERVICE_ACCOUNT_JSON_PATH ?? defaultConfigPath("service_account.json"),
  oauthClientJsonPath: process.env.SIMSOFT_OAUTH_CLIENT_JSON_PATH ?? defaultConfigPath("oauth_client.json"),
  oauthTokenDir: process.env.SIMSOFT_OAUTH_TOKEN_DIR ?? path.join("data", "oauth_tokens"),
  cacheDbPath: process.env.SIMSOFT_CACHE_DB_PATH ?? path.join("data", "cache", "simsoft_cache.sqlite"),
  duplicateHistoryPath: process.env.SIMSOFT_DUPLICATE_HISTORY_PATH ?? path.join("data", "duplicate_history.csv"),
  postedBatchesPath: process.env.SIMSOFT_POSTED_BATCHES_PATH ?? path.join("data", "posted_batches.csv"),
  postingLocksPath: process.env.SIMSOFT_POSTING_LOCKS_PATH ?? path.join("data", "posting_locks.json"),
  accessControlPath: process.env.SIMSOFT_ACCESS_CONTROL_PATH ?? path.join("data", "access_control.json"),
  logDir: process.env.SIMSOFT_LOG_DIR ?? "logs",
  storageCacheDir: process.env.SIMSOFT_STORAGE_CACHE_DIR ?? path.join("storage", "cache"),
  storageTempDir: process.env.SIMSOFT_STORAGE_TEMP_DIR ?? path.join("storage", "temp"),
  receiptOriginalsDir: process.env.SIMSOFT_RECEIPT_ORIGINALS_DIR ?? path.join("storage", "receipts", "originals"),
  receiptCompressedDir: process.env.SIMSOFT_RECEIPT_COMPRESSED_DIR ?? path.join("storage", "receipts", "compressed"),
  receiptThumbnailsDir: process.env.SIMSOFT_RECEIPT_THUMBNAILS_DIR ?? path.join("storage", "receipts", "thumbnails"),
  maxExcelFileMb: numberFromEnv("SIMSOFT_MAX_EXCEL_FILE_MB", 50),
  scanConcurrency: numberFromEnv("SIMSOFT_SCAN_CONCURRENCY", 4),
  googleConcurrency: numberFromEnv("SIMSOFT_GOOGLE_CONCURRENCY", 3),
  googleTimeoutMs: numberFromEnv("SIMSOFT_GOOGLE_TIMEOUT_MS", 30_000),
  requireUserOAuth: booleanFromEnv("SIMSOFT_REQUIRE_USER_OAUTH_FOR_POSTING"),
  adminEmails: listFromEnv("SIMSOFT_ADMIN_EMAILS"),
  memberEmails: listFromEnv("SIMSOFT_MEMBER_EMAILS"),
  userBranches: userBranchesFromEnv("SIMSOFT_USER_BRANCHES"),
  pythonExecutable: process.env.SIMSOFT_PYTHON ?? defaultPythonExecutable(),
  cloudEndpoint: process.env.SIMSOFT_CLOUD_ENDPOINT ?? ""
} as const;
