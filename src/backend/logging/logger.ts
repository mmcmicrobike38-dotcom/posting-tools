import fs from "node:fs";
import path from "node:path";
import winston from "winston";
import { appConfig } from "../config";

const SECRET_KEYS = /(password|token|refresh_token|access_token|private_key|client_secret|authorization|api_key)/i;
const SECRET_TEXT_PATTERNS = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/gi,
  /("?(?:access_token|refresh_token|client_secret|private_key|api_key|authorization)"?\s*[:=]\s*)("[^"]+"|'[^']+'|[^\s,}]+)/gi,
  /ya29\.[A-Za-z0-9._~+/=-]+/gi
];

function redactSecretMatch(_match: string, prefix?: string): string {
  return typeof prefix === "string" && prefix ? `${prefix}[REDACTED]` : "[REDACTED]";
}

export function sanitizeForLog(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeForLog);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        SECRET_KEYS.test(key) ? "[REDACTED]" : sanitizeForLog(item)
      ])
    );
  }
  if (typeof value === "string") {
    return SECRET_TEXT_PATTERNS.reduce(
      (text, pattern) => text.replace(pattern, redactSecretMatch),
      value
    );
  }
  return value;
}

fs.mkdirSync(appConfig.logDir, { recursive: true });

const fileTransport = new winston.transports.File({ filename: path.join(appConfig.logDir, "app.log") });
fileTransport.on("error", () => {
  // Logging must never interrupt posting or folder scanning.
});

export const logger = winston.createLogger({
  level: "info",
  exitOnError: false,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ timestamp, level, message, ...meta }) => {
      const cleanMeta = sanitizeForLog(meta);
      const metaText = Object.keys(cleanMeta as Record<string, unknown>).length
        ? ` ${JSON.stringify(cleanMeta)}`
        : "";
      return `${timestamp} ${level}: ${message}${metaText}`;
    })
  ),
  transports: [fileTransport]
});
