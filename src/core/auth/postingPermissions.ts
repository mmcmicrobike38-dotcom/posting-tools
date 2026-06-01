import { branchMatches, isAdmin, normalizeBranchId, User } from "./roleSystem";

export type PostingStatus = "pending" | "for_review" | "approved" | "rejected" | "finalized";

export type PostingActionType =
  | "CREATE_POSTING"
  | "EDIT_POSTING"
  | "DELETE_POSTING"
  | "FINALIZE_POSTING"
  | "VIEW_ALL_BRANCH_DATA"
  | "VIEW_BRANCH_DATA";

export type PostingAction =
  | PostingActionType
  | {
      type: PostingActionType;
      branchId?: string;
      postingStatus?: PostingStatus | string;
    };

export interface PermissionDecision {
  allowed: boolean;
  reason: string;
  branchScope: "all" | "branch" | "none";
}

function actionType(action: PostingAction): PostingActionType {
  return typeof action === "string" ? action : action.type;
}

function actionBranchId(action: PostingAction): string {
  return typeof action === "string" ? "" : normalizeBranchId(action.branchId ?? "");
}

function actionPostingStatus(action: PostingAction): string {
  return typeof action === "string" ? "" : String(action.postingStatus ?? "").trim().toLowerCase();
}

function allow(branchScope: PermissionDecision["branchScope"], reason = "Allowed."): PermissionDecision {
  return { allowed: true, reason, branchScope };
}

function deny(reason: string): PermissionDecision {
  return { allowed: false, reason, branchScope: "none" };
}

export function getPostingPermissionDecision(user: User, action: PostingAction): PermissionDecision {
  const type = actionType(action);
  if (isAdmin(user)) return allow("all", "Admin access.");

  if (type === "CREATE_POSTING") {
    const branchId = actionBranchId(action);
    if (!branchId) return user.branchId ? allow("branch", "Member can create pending postings for assigned branch.") : deny("Member requires a branch assignment to create postings.");
    return branchMatches(user, branchId)
      ? allow("branch", "Member can create pending postings for assigned branch.")
      : deny("Member can create postings only for the assigned branch.");
  }
  if (type === "VIEW_BRANCH_DATA") {
    const branchId = actionBranchId(action);
    return !branchId || branchMatches(user, branchId)
      ? allow("branch", "Member can view assigned branch data.")
      : deny("Member access is limited to assigned branch data.");
  }
  if (type === "EDIT_POSTING") {
    if (!branchMatches(user, actionBranchId(action))) return deny("Member can edit postings only for the assigned branch.");
    return actionPostingStatus(action) === "pending"
      ? allow("branch", "Member can edit pending postings for assigned branch.")
      : deny("Member can edit pending postings only.");
  }
  if (type === "DELETE_POSTING") return deny("Admin permission is required to delete postings.");
  if (type === "FINALIZE_POSTING") return deny("Admin permission is required to finalize postings.");
  if (type === "VIEW_ALL_BRANCH_DATA") return deny("Admin permission is required to view all branch data.");
  return deny("Permission denied.");
}

export function canPostAction(user: User, action: PostingAction): boolean {
  return getPostingPermissionDecision(user, action).allowed;
}

export function filterBranchScopedRecords<T extends { branchId?: string; branch_id?: string }>(user: User, records: T[]): T[] {
  if (isAdmin(user)) return records;
  return records.filter((record) => branchMatches(user, record.branchId ?? record.branch_id ?? ""));
}
