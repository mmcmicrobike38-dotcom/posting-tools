import fs from "node:fs/promises";
import { Stats } from "node:fs";
import path from "node:path";
import { appConfig } from "../config";
import { FileIndexCache, FileIndexEntry } from "./fileIndexCache";
import { runScanPipeline, ScanIndex, ScanItem, ScanProcessor, ScanSource } from "./scanPipeline";

export interface IncrementalScanOptions {
  rootDir: string;
  extensions?: string[];
  cachePath?: string;
  concurrency?: number;
  ignoredDirNames?: string[];
}

export interface IncrementalScanResult {
  rootDir: string;
  indexedFiles: FileIndexEntry[];
  changedFiles: FileIndexEntry[];
  skippedFiles: number;
  durationMs: number;
}

const DEFAULT_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp", ".pdf", ".xlsx", ".xlsm", ".csv"]);

async function* walk(rootDir: string, ignoredDirNames: Set<string>): AsyncGenerator<string> {
  const entries = await fs.readdir(rootDir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      if (!ignoredDirNames.has(entry.name)) yield* walk(fullPath, ignoredDirNames);
    } else if (entry.isFile()) {
      yield fullPath;
    }
  }
}

interface FileScanItem extends ScanItem {
  path: string;
  stats: Stats;
}

class FileSystemScanSource implements ScanSource<FileScanItem> {
  constructor(
    private readonly rootDir: string,
    private readonly extensions: Set<string>,
    private readonly ignoredDirNames: Set<string>
  ) {}

  async *items(): AsyncIterable<FileScanItem> {
    for await (const filePath of walk(this.rootDir, this.ignoredDirNames)) {
      if (!this.extensions.has(path.extname(filePath).toLowerCase())) continue;
      const stats = await fs.stat(filePath);
      yield { id: path.resolve(filePath), path: filePath, stats };
    }
  }
}

class FileMetadataIndex implements ScanIndex<FileScanItem> {
  constructor(private readonly cache: FileIndexCache) {}

  isFresh(item: FileScanItem): boolean {
    return this.cache.hasFreshEntry(item.path, item.stats);
  }

  save(item: FileScanItem): void {
    this.cache.upsert(item.path, item.stats);
  }

  flush(): void {
    this.cache.save();
  }
}

class FileMetadataProcessor implements ScanProcessor<FileScanItem, FileIndexEntry> {
  async process(item: FileScanItem): Promise<FileIndexEntry> {
    return {
      path: path.resolve(item.path),
      size: Number(item.stats.size),
      modifiedMs: Number(item.stats.mtimeMs),
      indexedAt: Date.now()
    };
  }
}

export async function scanIncrementally(options: IncrementalScanOptions): Promise<IncrementalScanResult> {
  const rootDir = path.resolve(options.rootDir);
  const extensions = new Set((options.extensions ?? [...DEFAULT_EXTENSIONS]).map((item) => item.toLowerCase()));
  const ignoredDirNames = new Set(options.ignoredDirNames ?? ["node_modules", "dist", "release", ".venv", "__pycache__"]);
  const cache = new FileIndexCache(options.cachePath ?? path.join(appConfig.storageCacheDir, "file-index.json"));
  cache.load();

  const result = await runScanPipeline(
    new FileSystemScanSource(rootDir, extensions, ignoredDirNames),
    new FileMetadataIndex(cache),
    new FileMetadataProcessor(),
    { concurrency: options.concurrency ?? appConfig.scanConcurrency, jobKeyPrefix: "index" }
  );

  return {
    rootDir,
    indexedFiles: cache.values(),
    changedFiles: result.processed,
    skippedFiles: result.skipped,
    durationMs: result.durationMs
  };
}
