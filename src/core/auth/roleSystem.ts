export type Role = "ADMIN" | "MEMBER";

export interface User {
  id: string;
  name: string;
  role: Role;
  branchId: string;
}

export interface AccessControlSnapshot {
  adminEmails?: string[];
  memberEmails?: string[];
  userBranches?: Record<string, string[]>;
}

export interface OperatorLike {
  email?: string;
  tokenUserEmail?: string;
  name?: string;
}

export function normalizeRole(value: unknown): Role {
  return String(value ?? "").trim().toUpperCase() === "ADMIN" ? "ADMIN" : "MEMBER";
}

export function normalizeUserId(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

export function normalizeBranchId(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

export function isAdmin(user: Pick<User, "role">): boolean {
  return user.role === "ADMIN";
}

export function branchMatches(user: Pick<User, "role" | "branchId">, branchId: string): boolean {
  if (isAdmin(user)) return true;
  const normalizedUserBranch = normalizeBranchId(user.branchId);
  return normalizedUserBranch === "*" || normalizedUserBranch === normalizeBranchId(branchId);
}

export function buildUser(input: {
  id: string;
  name?: string;
  role?: Role | string;
  branchId?: string;
}): User {
  const id = normalizeUserId(input.id);
  return {
    id,
    name: String(input.name ?? id).trim() || id,
    role: normalizeRole(input.role),
    branchId: normalizeBranchId(input.branchId ?? "")
  };
}

export function resolveUserFromAccess(operator: OperatorLike | null | undefined, access: AccessControlSnapshot): User {
  const email = normalizeUserId(operator?.email || operator?.tokenUserEmail || "");
  const tokenEmail = normalizeUserId(operator?.tokenUserEmail || "");
  const adminEmails = new Set((access.adminEmails ?? []).map(normalizeUserId).filter(Boolean));
  const memberEmails = new Set((access.memberEmails ?? []).map(normalizeUserId).filter(Boolean));
  const candidates = [email, tokenEmail].filter(Boolean);
  const isOperatorAdmin = candidates.some((candidate) => adminEmails.has(candidate));
  const isOperatorMember = candidates.some((candidate) => memberEmails.has(candidate));
  const role: Role = isOperatorAdmin || (!adminEmails.size && !isOperatorMember) ? "ADMIN" : "MEMBER";
  const branchAssignments = candidates.flatMap((candidate) => access.userBranches?.[candidate] ?? []);
  const branchId = role === "ADMIN" ? "*" : normalizeBranchId(branchAssignments[0] ?? "");
  return buildUser({
    id: email || tokenEmail || "anonymous",
    name: operator?.name || email || tokenEmail || "Operator",
    role,
    branchId
  });
}
