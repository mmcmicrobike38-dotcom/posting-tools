import { BranchInfo, IbpParticulars, IbpPaymentBreakdowns, OperatorIdentity, PostingResult } from "../../shared/types";
import { simsoftApi } from "../shared/api/simsoftApiClient";

export interface PostInput {
  filePath: string;
  filePaths?: string[];
  folderUrl: string;
  branchId: string;
  branchIndex: Record<string, BranchInfo>;
  ibpParticulars?: IbpParticulars;
  ibpPaymentBreakdowns?: IbpPaymentBreakdowns;
  authMode?: "service_account" | "user_oauth";
  operatorIdentity?: OperatorIdentity | null;
}

export const postService = {
  postGooglePreviews(input: PostInput): Promise<PostingResult> {
    return simsoftApi.postGooglePreviews({
      ...input,
      confirmation: "Continue Posting"
    });
  }
};
