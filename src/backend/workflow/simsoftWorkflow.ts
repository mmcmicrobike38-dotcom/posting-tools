import fs from "node:fs";
import { SQLiteCache } from "../cache/sqliteCache";
import {
  buildPreviewsWithPythonBackend,
  getOperatorIdentityWithPythonBackend,
  getDuplicateHistoryStatusWithPythonBackend,
  getSheetStatsWithPythonBackend,
  loginGoogleOperatorWithPythonBackend,
  parseWithPythonBackend,
  postWithPythonBackend,
  logoutGoogleOperatorWithPythonBackend,
  resetDuplicateHistoryWithPythonBackend,
  scanFolderWithPythonBackend
} from "../bridge/pythonBridge";
import { logger } from "../logging/logger";
import { validateExcelFilePath } from "../security/validation";
import {
  BranchInfo,
  DuplicateHistoryStatus,
  FolderScanResult,
  GoogleSheetPreviewResult,
  GoogleSheetStats,
  OperatorIdentity,
  ParseResult,
  PerformanceReport,
  PostingResult
} from "../../shared/types";
import { resolveUserFromAccess } from "../../core/auth/roleSystem";
import { canPostAction, PostingAction } from "../../core/auth/postingPermissions";
import { appConfig } from "../config";

const PARSER_VERSION = "python-core-v1";

export class SimsoftWorkflow {
  constructor(private readonly cache = new SQLiteCache()) {}

  private assertGovernancePermission(operatorIdentity: OperatorIdentity | null | undefined, action: PostingAction): void {
    const user = resolveUserFromAccess(operatorIdentity, {
      adminEmails: appConfig.adminEmails,
      memberEmails: appConfig.memberEmails,
      userBranches: appConfig.userBranches
    });
    if (!canPostAction(user, action)) {
      throw new Error("This operator does not have permission for this posting action.");
    }
  }

  async parseSimsoftFile(filePath: string): Promise<ParseResult> {
    const safePath = validateExcelFilePath(filePath);
    const stat = fs.statSync(safePath);
    const meta = {
      filePath: safePath,
      size: stat.size,
      modifiedMs: Math.trunc(stat.mtimeMs),
      parserVersion: PARSER_VERSION
    };
    const cached = this.cache.getParsed<ParseResult>(meta);
    if (cached) return cached;

    const started = performance.now();
    const result = await parseWithPythonBackend(safePath);
    const report: PerformanceReport = {
      scanDurationMs: performance.now() - started,
      cacheHits: this.cache.hits,
      cacheMisses: this.cache.misses,
      failedFileCount: 0,
      perFileDurationsMs: {
        [safePath]: performance.now() - started
      },
      googleRequestDurationsMs: {}
    };
    const finalResult: ParseResult = {
      ...result,
      parser: "python-core",
      performance: report
    };
    this.cache.setParsed(meta, finalResult);
    logger.info("SIMSOFT parse completed", { filePath: safePath, rowCount: finalResult.rows.length, durationMs: report.scanDurationMs });
    return finalResult;
  }

  clearCache(): void {
    this.cache.clear();
  }

  async scanGoogleFolder(input: {
    folderUrl: string;
    authMode?: string;
    operatorIdentity?: OperatorIdentity | null;
  }): Promise<FolderScanResult> {
    const started = performance.now();
    const result = await scanFolderWithPythonBackend(input);
    const finalResult: FolderScanResult = {
      ...result,
      performance: {
        scanDurationMs: performance.now() - started,
        cacheHits: this.cache.hits,
        cacheMisses: this.cache.misses,
        failedFileCount: 0,
        perFileDurationsMs: {},
        googleRequestDurationsMs: {}
      }
    };
    logger.info("Google Drive folder scan completed", {
      branchCount: finalResult.branchCount,
      durationMs: finalResult.performance?.scanDurationMs,
      duplicateWarningCount: finalResult.duplicateWarnings.length
    });
    return finalResult;
  }

  async buildGooglePreviews(input: {
    filePath: string;
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: string;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<GoogleSheetPreviewResult> {
    const safePath = validateExcelFilePath(input.filePath);
    this.assertGovernancePermission(input.operatorIdentity, { type: "VIEW_BRANCH_DATA", branchId: input.branchId });
    const started = performance.now();
    const result = await buildPreviewsWithPythonBackend({ ...input, filePath: safePath });
    logger.info("Google Sheet previews built", {
      branchId: input.branchId,
      durationMs: performance.now() - started,
      accountsRows: result.accountsPreviewRows.length,
      receiptRows: result.receiptPreviewRows.length,
      dailyRows: result.dailyPreviewRows.length,
      scrRows: result.scrPreviewRows.length,
      errorCount: result.errors.length
    });
    return result;
  }

  async getGoogleSheetStats(input: {
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    authMode?: string;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<GoogleSheetStats> {
    this.assertGovernancePermission(input.operatorIdentity, { type: "VIEW_BRANCH_DATA", branchId: input.branchId });
    const started = performance.now();
    const result = await getSheetStatsWithPythonBackend(input);
    logger.info("Google Sheet stats loaded", {
      branchId: input.branchId,
      accountsRowCount: result.accountsRowCount,
      durationMs: performance.now() - started
    });
    return result;
  }

  async postGooglePreviews(input: {
    filePath: string;
    folderUrl: string;
    branchId: string;
    branchIndex: Record<string, BranchInfo>;
    confirmation: string;
    ibpParticulars?: Record<string, string>;
    ibpPaymentBreakdowns?: Record<string, { rebate?: string; amount?: string; penalty?: string }>;
    authMode?: string;
    operatorIdentity?: OperatorIdentity | null;
    testMode?: boolean;
  }): Promise<PostingResult> {
    const safePath = validateExcelFilePath(input.filePath);
    this.assertGovernancePermission(input.operatorIdentity, "FINALIZE_POSTING");
    const started = performance.now();
    const result = await postWithPythonBackend({ ...input, filePath: safePath });
    logger.info("Google Sheet posting completed", {
      branchId: input.branchId,
      durationMs: performance.now() - started,
      postedCount: result.postedCount,
      lastPostStatus: result.lastPostStatus
    });
    return result;
  }

  async getOperatorIdentity(): Promise<OperatorIdentity> {
    return await getOperatorIdentityWithPythonBackend();
  }

  async loginGoogleOperator(): Promise<OperatorIdentity> {
    return await loginGoogleOperatorWithPythonBackend();
  }

  async logoutGoogleOperator(): Promise<OperatorIdentity> {
    return await logoutGoogleOperatorWithPythonBackend();
  }

  async getDuplicateHistoryStatus(): Promise<DuplicateHistoryStatus> {
    return await getDuplicateHistoryStatusWithPythonBackend();
  }

  async resetDuplicateHistory(confirmation: string): Promise<DuplicateHistoryStatus> {
    const result = await resetDuplicateHistoryWithPythonBackend(confirmation);
    this.clearCache();
    logger.warn("Local duplicate history reset", {
      duplicateHistoryPath: result.duplicateHistoryPath,
      backups: result.backups
    });
    return result;
  }

  close(): void {
    this.cache.close();
  }
}
