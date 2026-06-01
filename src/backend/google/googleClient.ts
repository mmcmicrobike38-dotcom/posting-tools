import fs from "node:fs";
import { google, sheets_v4, drive_v3 } from "googleapis";
import { appConfig } from "../config";
import { logger } from "../logging/logger";

const SCOPES = [
  "https://www.googleapis.com/auth/drive.readonly",
  "https://www.googleapis.com/auth/spreadsheets"
];

export interface GoogleClientBundle {
  drive: drive_v3.Drive;
  sheets: sheets_v4.Sheets;
  actorEmail: string;
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("Google API request timed out.")), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function retryGoogle<T>(label: string, operation: () => Promise<T>, attempts = 5): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const started = performance.now();
    try {
      const result = await withTimeout(operation(), appConfig.googleTimeoutMs);
      logger.info("Google API call completed", { label, durationMs: performance.now() - started });
      return result;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      const transient = /429|500|502|503|504|rateLimitExceeded|userRateLimitExceeded|Quota/i.test(message);
      if (!transient || attempt === attempts - 1) break;
      const delayMs = (2 ** attempt) * 1000 + Math.floor(Math.random() * 250);
      logger.warn("Google API transient failure; retrying", { label, attempt: attempt + 1, delayMs, error });
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

export async function createGoogleClients(): Promise<GoogleClientBundle> {
  if (!fs.existsSync(appConfig.serviceAccountJsonPath)) {
    throw new Error("Google service account JSON is not configured.");
  }
  const auth = new google.auth.GoogleAuth({
    keyFile: appConfig.serviceAccountJsonPath,
    scopes: SCOPES
  });
  const authClient = await auth.getClient();
  const credentials = JSON.parse(fs.readFileSync(appConfig.serviceAccountJsonPath, "utf8")) as { client_email?: string };
  return {
    drive: google.drive({ version: "v3", auth: authClient as any }),
    sheets: google.sheets({ version: "v4", auth: authClient as any }),
    actorEmail: credentials.client_email ?? ""
  };
}
