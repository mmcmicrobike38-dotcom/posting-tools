import fs from "node:fs";
import path from "node:path";

export interface WatchBatch {
  rootDir: string;
  changedPaths: string[];
  createdAt: number;
}

export interface DebouncedWatcherOptions {
  rootDir: string;
  debounceMs?: number;
  ignoredDirNames?: string[];
  onBatch: (batch: WatchBatch) => void | Promise<void>;
}

export class DebouncedFileWatcher {
  private readonly watchers: fs.FSWatcher[] = [];
  private readonly changedPaths = new Set<string>();
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly options: DebouncedWatcherOptions) {}

  start(): void {
    this.watchDirectory(path.resolve(this.options.rootDir));
  }

  close(): void {
    for (const watcher of this.watchers) watcher.close();
    this.watchers.length = 0;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.changedPaths.clear();
  }

  private watchDirectory(dir: string): void {
    const ignored = new Set(this.options.ignoredDirNames ?? ["node_modules", "dist", "release", ".venv", "__pycache__"]);
    if (ignored.has(path.basename(dir))) return;

    const watcher = fs.watch(dir, { persistent: false }, (_event, fileName) => {
      if (!fileName) return;
      this.changedPaths.add(path.join(dir, fileName.toString()));
      this.scheduleFlush();
    });
    this.watchers.push(watcher);

    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) this.watchDirectory(path.join(dir, entry.name));
    }
  }

  private scheduleFlush(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.flush(), this.options.debounceMs ?? 350);
  }

  private async flush(): Promise<void> {
    const changedPaths = [...this.changedPaths];
    this.changedPaths.clear();
    this.timer = null;
    if (!changedPaths.length) return;
    await this.options.onBatch({
      rootDir: path.resolve(this.options.rootDir),
      changedPaths,
      createdAt: Date.now()
    });
  }
}

