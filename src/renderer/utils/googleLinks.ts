const GOOGLE_HOSTS = new Set(["drive.google.com", "docs.google.com"]);
const SECRET_VALUE_PATTERNS = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/gi,
  /("?(?:access_token|refresh_token|client_secret|private_key|api_key|authorization)"?\s*[:=]\s*)("[^"]+"|'[^']+'|[^\s,}]+)/gi,
  /ya29\.[A-Za-z0-9._~+/=-]+/gi
];

function redactSecretMatch(_match: string, prefix?: string): string {
  return typeof prefix === "string" && prefix ? `${prefix}[REDACTED]` : "[REDACTED]";
}

export type GoogleLinkValidation =
  | { ok: true; normalizedUrl: string }
  | { ok: false; reason: "empty" | "invalid" };

export function validateGoogleFolderLink(value: string): GoogleLinkValidation {
  const trimmed = value.trim();
  if (!trimmed) return { ok: false, reason: "empty" };

  try {
    const url = new URL(trimmed);
    const host = url.hostname.replace(/^www\./, "");
    const hasDriveFolder = url.protocol === "https:" && host === "drive.google.com" && /\/drive\/folders\/[A-Za-z0-9_-]+/.test(url.pathname);
    const hasDocsFolderParam = host === "docs.google.com" && Boolean(url.searchParams.get("folder"));
    if (url.protocol !== "https:" || !GOOGLE_HOSTS.has(host) || (!hasDriveFolder && !hasDocsFolderParam)) {
      return { ok: false, reason: "invalid" };
    }
    url.hash = "";
    return { ok: true, normalizedUrl: url.toString() };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}

export function safeDisplayText(value: unknown): string {
  let text = String(value ?? "");
  for (const pattern of SECRET_VALUE_PATTERNS) {
    text = text.replace(pattern, redactSecretMatch);
  }
  return text.replace(/[<>]/g, "").slice(0, 2000);
}
