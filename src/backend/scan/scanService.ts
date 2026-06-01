import { drive_v3 } from "googleapis";
import { appConfig } from "../config";
import { retryGoogle } from "../google/googleClient";
import { logger } from "../logging/logger";
import { SimpleJobQueue } from "../queue/simpleJobQueue";
import { BranchInfo, PerformanceReport, ScanProgress } from "../../shared/types";

const BRANCH_ID_PATTERN = /(MMC\d{3})/i;

export function buildBranchIndex(files: drive_v3.Schema$File[]): Record<string, BranchInfo> {
  const index: Record<string, BranchInfo> = {};
  for (const file of files) {
    const name = file.name ?? "";
    const match = BRANCH_ID_PATTERN.exec(name);
    if (!match || !file.id) continue;
    const branchId = match[1].toUpperCase();
    const branchName = name.replace(/^MMC\d{3}\s*[-_]\s*/i, "").replace(/\s+REALTIME.*$/i, "").trim();
    const entry: BranchInfo = {
      branch_id: branchId,
      branch_name: branchName,
      spreadsheet_id: file.id,
      file_name: name,
      modified_time: file.modifiedTime ?? "",
      status: "OK"
    };
    if (index[branchId]) {
      index[branchId].status = "MULTIPLE_MATCHES";
      index[branchId].issue = "Multiple files for this branch ID";
    } else {
      index[branchId] = entry;
    }
  }
  return index;
}

export async function scanDriveFolder(
  drive: drive_v3.Drive,
  folderId: string,
  onProgress: (progress: ScanProgress) => void = () => undefined
): Promise<{ index: Record<string, BranchInfo>; performance: PerformanceReport }> {
  const started = performance.now();
  const queue = new SimpleJobQueue(appConfig.googleConcurrency);
  const files: drive_v3.Schema$File[] = [];
  let pageToken: string | undefined;
  do {
    const response = await queue.run(() =>
      retryGoogle("drive.files.list", () =>
        drive.files.list({
          q: `'${folderId}' in parents and (mimeType = 'application/vnd.google-apps.spreadsheet' or mimeType = 'application/vnd.google-apps.shortcut') and trashed = false`,
          fields: "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,shortcutDetails)",
          pageSize: 1000,
          supportsAllDrives: true,
          includeItemsFromAllDrives: true,
          pageToken
        })
      )
    );
    files.push(...(response.data.files ?? []));
    pageToken = response.data.nextPageToken ?? undefined;
    onProgress({
      currentFile: "Google Drive metadata",
      totalFiles: files.length,
      completedFiles: files.length,
      failedFiles: 0,
      percent: pageToken ? 50 : 100
    });
  } while (pageToken);
  const index = buildBranchIndex(files);
  const report: PerformanceReport = {
    scanDurationMs: performance.now() - started,
    cacheHits: 0,
    cacheMisses: 0,
    failedFileCount: 0,
    perFileDurationsMs: {},
    googleRequestDurationsMs: {}
  };
  logger.info("Drive folder scan completed", { folderId, fileCount: files.length, branchCount: Object.keys(index).length, durationMs: report.scanDurationMs });
  return { index, performance: report };
}
