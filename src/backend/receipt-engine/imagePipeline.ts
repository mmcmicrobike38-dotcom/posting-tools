import fs from "node:fs/promises";
import path from "node:path";
import { appConfig } from "../config";
import { DedupedJobQueue } from "../workers/dedupedJobQueue";

export interface ReceiptImageJob {
  sourcePath: string;
  receiptId?: string;
}

export interface ReceiptImageResult {
  originalPath: string;
  compressedPath: string;
  thumbnailPath: string;
  generatedAt: string;
}

const queue = new DedupedJobQueue(2);

function safeReceiptName(job: ReceiptImageJob): string {
  const parsed = path.parse(job.sourcePath);
  const base = (job.receiptId || parsed.name).replace(/[^a-z0-9_-]+/gi, "-").slice(0, 80);
  return `${base || "receipt"}${parsed.ext.toLowerCase()}`;
}

export async function processReceiptImage(job: ReceiptImageJob): Promise<ReceiptImageResult> {
  const sourcePath = path.resolve(job.sourcePath);
  return await queue.enqueue(
    async () => {
      const fileName = safeReceiptName(job);
      const originalPath = path.join(appConfig.receiptOriginalsDir, fileName);
      const compressedPath = path.join(appConfig.receiptCompressedDir, fileName);
      const thumbnailPath = path.join(appConfig.receiptThumbnailsDir, fileName);

      await Promise.all([
        fs.mkdir(appConfig.receiptOriginalsDir, { recursive: true }),
        fs.mkdir(appConfig.receiptCompressedDir, { recursive: true }),
        fs.mkdir(appConfig.receiptThumbnailsDir, { recursive: true })
      ]);

      // This preserves pipeline semantics without adding a native image dependency yet.
      // Swap these copies for sharp/Jimp transforms once receipt preview requirements are finalized.
      await fs.copyFile(sourcePath, originalPath);
      await fs.copyFile(sourcePath, compressedPath);
      await fs.copyFile(sourcePath, thumbnailPath);

      return {
        originalPath,
        compressedPath,
        thumbnailPath,
        generatedAt: new Date().toISOString()
      };
    },
    { key: `receipt:${sourcePath}` }
  );
}

