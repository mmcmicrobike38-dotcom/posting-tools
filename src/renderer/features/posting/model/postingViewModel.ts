import {
  AppStatus,
  BranchInfo,
  GoogleSheetPreviewResult,
  GoogleSheetStats,
  IbpPaymentBreakdowns,
  IbpParticulars,
  OperatorIdentity,
  ParseResult,
  UserRole
} from "../../../../shared/types";
import { resolveUserFromAccess, User } from "../../../../core/auth/roleSystem";
import { canPostAction } from "../../../../core/auth/postingPermissions";
import { PreviewTab } from "../../../lib/previewTabs";

export type ScanStatus = "idle" | "invalid" | "scanning" | "completed" | "error";
export type SheetUpdateStatus = "idle" | "loading" | "completed" | "error";
export type ValidationOverlayState = {
  status: "loading" | "success" | "error";
  title: string;
  message: string;
} | null;

export interface IbpReviewRow {
  key: string;
  orNumber: string;
  accountNo: string;
  customer: string;
  amount: string;
  collectingBranch: string;
  generatedReference: string;
}

export interface AccessViewState {
  userRole: UserRole;
  isAdmin: boolean;
  assignedBranchIds: string[];
  hasLimitedBranchAssignment: boolean;
}

export interface GovernanceUiAccess {
  canCreatePosting: boolean;
  canEditPendingPosting: boolean;
  canDeletePosting: boolean;
  canFinalizePosting: boolean;
  canViewAllBranchData: boolean;
  canViewBranchData: boolean;
  memberPrimaryViews: string[];
  adminPrimaryViews: string[];
}

export const SAVED_FOLDER_URL_KEY = "simsoft.savedGoogleFolderUrl";

export function recordText(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  return value === undefined || value === null ? "" : String(value).trim();
}

export function isExcelFilePath(path: string): boolean {
  return /\.(xlsx|xlsm)$/i.test(path.trim());
}

export function resolveAccessViewState(status: AppStatus | null, operatorIdentity: OperatorIdentity | null): AccessViewState {
  const adminEmails = status?.adminEmails ?? [];
  const memberEmails = status?.memberEmails ?? [];
  const userBranches = status?.userBranches ?? {};
  const operatorEmail = operatorIdentity?.email.trim().toLowerCase() ?? "";
  const operatorIsAdmin = Boolean(operatorEmail && adminEmails.includes(operatorEmail));
  const operatorIsMember = Boolean(operatorEmail && memberEmails.includes(operatorEmail));
  const userRole: UserRole = operatorIsAdmin || (!adminEmails.length && !operatorIsMember) ? "admin" : "member";
  const isAdmin = userRole === "admin";
  const explicitAssignedBranchIds = userBranches[operatorEmail] ?? [];
  const hasLimitedBranchAssignment =
    explicitAssignedBranchIds.length > 0 && !explicitAssignedBranchIds.some((branch) => branch.toUpperCase() === "*");
  const assignedBranchIds = hasLimitedBranchAssignment ? explicitAssignedBranchIds : isAdmin ? ["*"] : explicitAssignedBranchIds;
  return { userRole, isAdmin, assignedBranchIds, hasLimitedBranchAssignment };
}

export function resolveGovernanceUser(status: AppStatus | null, operatorIdentity: OperatorIdentity | null): User {
  return resolveUserFromAccess(operatorIdentity, {
    adminEmails: status?.adminEmails ?? [],
    memberEmails: status?.memberEmails ?? [],
    userBranches: status?.userBranches ?? {}
  });
}

export function resolveGovernanceUiAccess(user: User, selectedBranchId = ""): GovernanceUiAccess {
  return {
    canCreatePosting: canPostAction(user, { type: "CREATE_POSTING", branchId: selectedBranchId || user.branchId }),
    canEditPendingPosting: canPostAction(user, { type: "EDIT_POSTING", branchId: selectedBranchId || user.branchId, postingStatus: "pending" }),
    canDeletePosting: canPostAction(user, "DELETE_POSTING"),
    canFinalizePosting: canPostAction(user, "FINALIZE_POSTING"),
    canViewAllBranchData: canPostAction(user, "VIEW_ALL_BRANCH_DATA"),
    canViewBranchData: canPostAction(user, { type: "VIEW_BRANCH_DATA", branchId: selectedBranchId || user.branchId }),
    memberPrimaryViews: ["Create Posting", "My Branch Records"],
    adminPrimaryViews: ["Dashboard", "Approval Queue", "Audit Logs"]
  };
}

export function getBranchOptions(
  branchIndex: Record<string, BranchInfo> | undefined,
  access: AccessViewState
): BranchInfo[] {
  const allowed = new Set(access.assignedBranchIds.map((branch) => branch.toUpperCase()));
  return Object.values(branchIndex ?? {})
    .filter(
      (branch) =>
        (access.isAdmin && !access.hasLimitedBranchAssignment) ||
        allowed.has("*") ||
        allowed.has(branch.branch_id.toUpperCase())
    )
    .sort((first, second) => first.branch_id.localeCompare(second.branch_id));
}

export function getActiveRows(
  activeTab: PreviewTab,
  previewResult: GoogleSheetPreviewResult | null,
  result: ParseResult | null
): Record<string, unknown>[] {
  if (activeTab === "ACCOUNTS") return previewResult?.accountsPreviewRows ?? [];
  if (activeTab === "RECIEPT") return previewResult?.receiptPreviewRows ?? [];
  if (activeTab === "DAILY") return previewResult?.dailyPreviewRows ?? [];
  if (activeTab === "SCR VS BR") return previewResult?.scrPreviewRows ?? [];
  return previewResult?.parsedRows ?? result?.rows ?? [];
}

export function getPreviewCounts(previewResult: GoogleSheetPreviewResult | null, result: ParseResult | null): Record<PreviewTab, number> {
  return {
    SIMSOFT: previewResult?.parsedRows.length ?? result?.rows.length ?? 0,
    ACCOUNTS: previewResult?.accountsPreviewRows.length ?? 0,
    RECIEPT: previewResult?.receiptPreviewRows.length ?? 0,
    DAILY: previewResult?.dailyPreviewRows.length ?? 0,
    "SCR VS BR": previewResult?.scrPreviewRows.length ?? 0
  };
}

function ibpBranchName(value: string): string {
  const withoutCode = value.replace(/^MMC\d{3}\s*[-/]\s*/i, "").trim() || value;
  return withoutCode.replace(/\s+\d{1,2}(?:\.\d{1,2})?$/, "").trim() || withoutCode;
}

export function buildIbpReviewRows(input: {
  previewResult: GoogleSheetPreviewResult | null;
  sheetStats: GoogleSheetStats | null;
  selectedBranchId: string;
  ibpParticulars: IbpParticulars;
}): IbpReviewRow[] {
  const collectingBranch = input.previewResult?.sheet.targetBranchName || input.sheetStats?.targetBranchName || input.selectedBranchId;
  const collectingBranchName = ibpBranchName(collectingBranch);
  return (input.previewResult?.parsedRows ?? [])
    .filter((row) => {
      const isIbp = row["is_ibp"] === true || String(row["is_ibp"] ?? "").toLowerCase() === "true";
      const status = recordText(row, "Status").toUpperCase();
      return isIbp && status === "PASSED";
    })
    .map((row, index) => {
      const key = recordText(row, "Transaction Key") || `${recordText(row, "OR Number")}-${recordText(row, "ibp_account_no")}-${index}`;
      const particular = input.ibpParticulars[key]?.trim() ?? "";
      const orNumber = recordText(row, "OR Number");
      return {
        key,
        orNumber,
        accountNo: recordText(row, "ibp_account_no"),
        customer: recordText(row, "ibp_resolved_customer") || recordText(row, "Account Name"),
        amount: recordText(row, "Actual Collection") || recordText(row, "Amount"),
        collectingBranch,
        generatedReference: particular ? `${orNumber} IBP ${collectingBranchName} - (${particular})` : ""
      };
    });
}

export function isIbpReviewRequired(rows: IbpReviewRow[], breakdowns: IbpPaymentBreakdowns, particulars: IbpParticulars): boolean {
  return rows.some((row) => {
    const breakdown = breakdowns[row.key];
    return !particulars[row.key]?.trim() || !breakdown?.amount?.trim();
  });
}

export function getEmptyPreviewMessage(activeRowsLength: number, activeTab: PreviewTab, previewResult: GoogleSheetPreviewResult | null): string {
  if (activeRowsLength) return "";
  if (!previewResult && activeTab !== "SIMSOFT") return "Validate the SIMSOFT file and update the selected branch sheet. This tab will fill in after the posting preview is built.";
  if (activeTab === "SCR VS BR") return "No SCR VS BR updates were generated for this file. If you expected updates, check the selected branch and validate again.";
  if (activeTab === "ACCOUNTS") return "No account posting rows are ready yet. After validation, account entries that can be posted will appear here.";
  if (activeTab === "RECIEPT") return "No receipt rows are ready yet. After validation, receipt entries will appear here for review.";
  if (activeTab === "DAILY") return "No 1-31 Daily rows are ready yet. After validation, daily report entries will appear here.";
  return "No SIMSOFT file loaded yet. Choose the SIMSOFT export Excel file, then click Validate.";
}
