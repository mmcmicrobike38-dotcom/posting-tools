import { PreviewTab } from "../../lib/previewTabs";

const preferredPreviewColumns: Record<PreviewTab, string[]> = {
  SIMSOFT: ["Account Name", "OR Number", "Actual Collection", "Mode of Payment", "Status", "Remarks"],
  ACCOUNTS: ["Account", "Account Name", "OR Number", "Actual Collection", "Code", "Remarks"],
  RECIEPT: ["Date", "OR Number", "Transaction", "Amount", "Remarks"],
  DAILY: ["Date", "OR Number", "Amount", "Account", "Remarks"],
  "SCR VS BR": ["Date", "OR Number", "Amount", "Account", "Remarks"]
};

export function friendlyIssueText(message: string) {
  const text = message.trim();
  const normalized = text.toLowerCase();
  if (normalized.includes("folder scan required")) return "Scan the Drive folder before validating or posting.";
  if (normalized.includes("select target branch")) return "Select the correct target branch from the branch list.";
  if (normalized.includes("preview is stale")) return "Refresh validation so the preview matches the latest sheet data.";
  if (normalized.includes("google sheet connection is not ready")) return "Update the selected sheet, then validate again.";
  if (normalized.includes("simsoft file is not parsed")) return "Choose and validate the SIMSOFT Excel file.";
  if (normalized.includes("google authentication required")) return "Sign in with Google before continuing.";
  return text;
}

export function previewTitle(tab: PreviewTab) {
  if (tab === "DAILY") return "1-31";
  if (tab === "RECIEPT") return "RECIPTS";
  if (tab === "SCR VS BR") return "SCRVSBR";
  return tab;
}

export function displayValue(value: unknown) {
  const text = value === undefined || value === null ? "" : String(value).trim();
  return text || "-";
}

export function initialsFromName(value: string) {
  const words = value
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return "OP";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

export function usefulPreviewColumns(tab: PreviewTab, rows: Record<string, unknown>[], fallbackColumns: string[]) {
  const available = new Set(Object.keys(rows[0] ?? {}));
  const preferred = preferredPreviewColumns[tab].filter((column) => available.has(column));
  const fallback = fallbackColumns.filter((column) => !preferred.includes(column)).slice(0, Math.max(0, 6 - preferred.length));
  return [...preferred, ...fallback].slice(0, 6);
}
