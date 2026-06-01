import { describe, expect, it } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildBranchIndex } from "../src/backend/scan/scanService";
import { scanIncrementally } from "../src/backend/scan/incrementalScanner";
import { runScanPipeline, ScanIndex, ScanProcessor, ScanSource } from "../src/backend/scan/scanPipeline";

describe("branch scan adapter", () => {
  it("keeps existing branch filename detection behavior", () => {
    const index = buildBranchIndex([
      {
        id: "sheet1",
        name: "MMC038 - POZORRUBIO REALTIME 2026",
        mimeType: "application/vnd.google-apps.spreadsheet",
        modifiedTime: "2026-01-01T00:00:00Z"
      }
    ]);

    expect(index.MMC038.branch_id).toBe("MMC038");
    expect(index.MMC038.branch_name).toBe("POZORRUBIO");
    expect(index.MMC038.spreadsheet_id).toBe("sheet1");
  });
});

describe("incremental file scanner", () => {
  it("indexes changed files and skips unchanged files on the next run", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "simsoft-scan-"));
    const cachePath = path.join(rootDir, "file-index.json");
    const receiptPath = path.join(rootDir, "receipt.jpg");
    await fs.writeFile(receiptPath, "receipt-one", "utf8");

    const first = await scanIncrementally({
      rootDir,
      cachePath,
      extensions: [".jpg"],
      concurrency: 2
    });
    const second = await scanIncrementally({
      rootDir,
      cachePath,
      extensions: [".jpg"],
      concurrency: 2
    });

    expect(first.changedFiles.map((file) => path.basename(file.path))).toEqual(["receipt.jpg"]);
    expect(first.skippedFiles).toBe(0);
    expect(second.changedFiles).toEqual([]);
    expect(second.skippedFiles).toBe(1);
  });
});

describe("scan pipeline performance guard", () => {
  it("keeps processing bounded instead of buffering every discovered item", async () => {
    type Item = { id: string };
    let active = 0;
    let maxActive = 0;

    const source: ScanSource<Item> = {
      async *items() {
        for (let index = 0; index < 40; index += 1) {
          yield { id: String(index) };
        }
      }
    };
    const index: ScanIndex<Item> = {
      isFresh: () => false,
      save: () => undefined
    };
    const processor: ScanProcessor<Item, string> = {
      async process(item) {
        active += 1;
        maxActive = Math.max(maxActive, active);
        await new Promise((resolve) => setTimeout(resolve, 2));
        active -= 1;
        return item.id;
      }
    };

    const result = await runScanPipeline(source, index, processor, {
      concurrency: 3,
      jobKeyPrefix: "test",
      maxBufferedJobs: 6
    });

    expect(result.processed).toHaveLength(40);
    expect(maxActive).toBeLessThanOrEqual(3);
  });
});
