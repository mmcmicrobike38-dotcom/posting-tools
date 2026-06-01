import fs from "node:fs";
import path from "node:path";

export interface FileIndexEntry {
  path: string;
  size: number;
  modifiedMs: number;
  indexedAt: number;
}

export class FileIndexCache {
  private readonly entries = new Map<string, FileIndexEntry>();

  constructor(private readonly cachePath: string) {}

  load(): void {
    if (!fs.existsSync(this.cachePath)) return;
    try {
      const raw = JSON.parse(fs.readFileSync(this.cachePath, "utf8")) as FileIndexEntry[];
      this.entries.clear();
      for (const entry of raw) {
        if (entry.path) this.entries.set(path.resolve(entry.path), entry);
      }
    } catch {
      this.entries.clear();
    }
  }

  save(): void {
    fs.mkdirSync(path.dirname(this.cachePath), { recursive: true });
    fs.writeFileSync(this.cachePath, JSON.stringify([...this.entries.values()], null, 2), "utf8");
  }

  hasFreshEntry(filePath: string, stats: fs.Stats): boolean {
    const existing = this.entries.get(path.resolve(filePath));
    return Boolean(existing && existing.size === stats.size && existing.modifiedMs === stats.mtimeMs);
  }

  upsert(filePath: string, stats: fs.Stats): FileIndexEntry {
    const entry: FileIndexEntry = {
      path: path.resolve(filePath),
      size: stats.size,
      modifiedMs: stats.mtimeMs,
      indexedAt: Date.now()
    };
    this.entries.set(entry.path, entry);
    return entry;
  }

  remove(filePath: string): void {
    this.entries.delete(path.resolve(filePath));
  }

  values(): FileIndexEntry[] {
    return [...this.entries.values()];
  }
}

