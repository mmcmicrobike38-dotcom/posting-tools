import { safeDisplayText } from "./googleLinks";

const fallbackMessage = "The action could not be completed. Please try again.";

export function operatorError(error: unknown, fallback = fallbackMessage): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const clean = safeDisplayText(raw).trim();
  if (!clean || clean === "[object Object]") return fallback;
  if (/failed to fetch|networkerror|econnreset|etimedout|timeout/i.test(clean)) {
    return "Connection problem. Check internet access, then try again.";
  }
  if (/permission|access denied|forbidden|unauthorized|invalid_grant|login/i.test(clean)) {
    return "Google access is not ready. Sign in again or check access to the selected folder/sheet.";
  }
  if (/credential|token|private_key|client_secret/i.test(clean)) {
    return "Authentication configuration needs attention. Check Google login and credential settings.";
  }
  return clean;
}
