export const PREVIEW_TABS = ["SIMSOFT", "ACCOUNTS", "RECIEPT", "DAILY", "SCR VS BR"] as const;

export type PreviewTab = (typeof PREVIEW_TABS)[number];

export type ActiveModal =
  | "resetDuplicates"
  | "logoutConfirm"
  | "rescanConfirm"
  | "saveLinkConfirm"
  | "saveLinkDone"
  | "unsaveLinkConfirm"
  | "unsaveLinkDone"
  | "updateSheetConfirm"
  | "validateFileFirst"
  | "invalidFileType"
  | "postBlocked"
  | "clearCacheConfirm"
  | "clearCacheDone"
  | "googleTestUsersConfirm"
  | "healthCheckResult"
  | "settingsSummary"
  | "aboutPostingReview"
  | "confirmPost"
  | "postAgain"
  | "settings"
  | "branchNotUploaded"
  | "rescanDone"
  | "updateDone"
  | "wrongBranch"
  | "missingAccount"
  | "updateSheetFirst"
  | "shortcuts"
  | null;
