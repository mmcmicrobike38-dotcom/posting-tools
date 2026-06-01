import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { appConfig } from "../config";
import { logger } from "../logging/logger";

export interface CachedFileMetadata {
  filePath: string;
  size: number;
  modifiedMs: number;
  parserVersion: string;
}

const requireNative = createRequire(__filename);

export class SQLiteCache {
  private readonly db: any | null;
  private readonly memoryCache = new Map<string, string>();
  hits = 0;
  misses = 0;

  constructor(dbPath = appConfig.cacheDbPath) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    try {
      const Database = requireNative("better-sqlite3");
      this.db = new Database(dbPath);
      this.db.pragma("journal_mode = WAL");
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS file_metadata (
          file_path TEXT PRIMARY KEY,
          size INTEGER NOT NULL,
          modified_ms INTEGER NOT NULL,
          parser_version TEXT NOT NULL,
          cached_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS parsed_results (
          cache_key TEXT PRIMARY KEY,
          file_path TEXT NOT NULL,
          result_json TEXT NOT NULL,
          cached_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_parsed_results_file_path ON parsed_results(file_path);

        CREATE TABLE IF NOT EXISTS posting_batches (
          batch_id TEXT PRIMARY KEY,
          operator_email TEXT NOT NULL DEFAULT '',
          target_branch_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'created',
          created_at TEXT NOT NULL,
          posted_at TEXT,
          source_file TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS posting_transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_id TEXT NOT NULL,
          transaction_key TEXT NOT NULL,
          target_branch_id TEXT NOT NULL DEFAULT '',
          target_tab TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT '',
          amount TEXT NOT NULL DEFAULT '',
          posted_at TEXT,
          record_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          FOREIGN KEY(batch_id) REFERENCES posting_batches(batch_id)
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          batch_id TEXT NOT NULL DEFAULT '',
          target_branch_id TEXT NOT NULL DEFAULT '',
          actor_email TEXT NOT NULL DEFAULT '',
          event_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS duplicate_checks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          transaction_key TEXT NOT NULL,
          batch_id TEXT NOT NULL DEFAULT '',
          target_branch_id TEXT NOT NULL DEFAULT '',
          check_result TEXT NOT NULL,
          checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS branch_locks (
          lock_key TEXT PRIMARY KEY,
          target_branch_id TEXT NOT NULL,
          target_spreadsheet_id TEXT NOT NULL DEFAULT '',
          batch_id TEXT NOT NULL DEFAULT '',
          operator_email TEXT NOT NULL DEFAULT '',
          acquired_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          released_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_posting_transactions_key ON posting_transactions(transaction_key);
        CREATE INDEX IF NOT EXISTS idx_posting_transactions_batch ON posting_transactions(batch_id);
        CREATE INDEX IF NOT EXISTS idx_posting_batches_branch_posted ON posting_batches(target_branch_id, posted_at);
        CREATE INDEX IF NOT EXISTS idx_audit_events_batch_created ON audit_events(batch_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_duplicate_checks_key_checked ON duplicate_checks(transaction_key, checked_at);
        CREATE INDEX IF NOT EXISTS idx_branch_locks_branch_expires ON branch_locks(target_branch_id, expires_at);
      `);
    } catch (error) {
      this.db = null;
      logger.warn("SQLite cache unavailable; using in-memory cache for this session", { error });
    }
  }

  makeFileCacheKey(meta: CachedFileMetadata): string {
    return `${path.resolve(meta.filePath)}|${meta.size}|${meta.modifiedMs}|${meta.parserVersion}`;
  }

  getParsed<T>(meta: CachedFileMetadata): T | null {
    const key = this.makeFileCacheKey(meta);
    if (!this.db) {
      const value = this.memoryCache.get(key);
      if (!value) {
        this.misses += 1;
        logger.info("cache miss", { area: "memory_parsed_results", filePath: meta.filePath });
        return null;
      }
      this.hits += 1;
      logger.info("cache hit", { area: "memory_parsed_results", filePath: meta.filePath });
      return JSON.parse(value) as T;
    }
    const row = this.db.prepare("SELECT result_json FROM parsed_results WHERE cache_key = ?").get(key) as
      | { result_json: string }
      | undefined;
    if (!row) {
      this.misses += 1;
      logger.info("cache miss", { area: "parsed_results", filePath: meta.filePath });
      return null;
    }
    this.hits += 1;
    logger.info("cache hit", { area: "parsed_results", filePath: meta.filePath });
    return JSON.parse(row.result_json) as T;
  }

  setParsed(meta: CachedFileMetadata, value: unknown): void {
    const key = this.makeFileCacheKey(meta);
    if (!this.db) {
      this.memoryCache.set(key, JSON.stringify(value));
      logger.info("cache write", { area: "memory_parsed_results", filePath: meta.filePath });
      return;
    }
    const now = new Date().toISOString();
    const tx = this.db.transaction(() => {
      this.db.prepare(
        "INSERT OR REPLACE INTO file_metadata (file_path, size, modified_ms, parser_version, cached_at) VALUES (?, ?, ?, ?, ?)"
      ).run(path.resolve(meta.filePath), meta.size, meta.modifiedMs, meta.parserVersion, now);
      this.db.prepare(
        "INSERT OR REPLACE INTO parsed_results (cache_key, file_path, result_json, cached_at) VALUES (?, ?, ?, ?)"
      ).run(key, path.resolve(meta.filePath), JSON.stringify(value), now);
    });
    tx();
    logger.info("cache write", { area: "parsed_results", filePath: meta.filePath });
  }

  clear(): void {
    if (!this.db) {
      this.memoryCache.clear();
      this.hits = 0;
      this.misses = 0;
      logger.info("cache cleared");
      return;
    }
    this.db.exec("DELETE FROM parsed_results; DELETE FROM file_metadata; PRAGMA wal_checkpoint(TRUNCATE); VACUUM;");
    this.hits = 0;
    this.misses = 0;
    logger.info("cache cleared");
  }

  close(): void {
    this.db?.close();
  }
}
