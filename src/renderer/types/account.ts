export type AccountStatus = "active" | "fully-paid" | "past-due" | "closed";

export type AccountSummary = {
  accountId: string;
  customerName: string;
  branchName: string;
  status: AccountStatus;
  collectionStatus: string;
};
