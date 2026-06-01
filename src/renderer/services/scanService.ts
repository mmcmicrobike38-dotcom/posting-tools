import { AuthMode, FolderScanResult, OperatorIdentity } from "../../shared/types";
import { simsoftApi } from "../shared/api/simsoftApiClient";

export type ScanSource = "idle" | "fresh scan" | "cached scan" | "partially refreshed scan";

export interface CachedScanEntry {
  result: FolderScanResult;
  scannedAt: number;
  source: ScanSource;
}

const memoryCache = new Map<string, CachedScanEntry>();

function scanCacheKey(link: string, context: { authMode?: AuthMode; operatorIdentity?: OperatorIdentity | null } = {}) {
  const actor = context.operatorIdentity?.email?.trim().toLowerCase() || "anonymous";
  return `${context.authMode || "default"}|${actor}|${link.trim()}`;
}

export const scanService = {
  getCached(link: string, context: { authMode?: AuthMode; operatorIdentity?: OperatorIdentity | null } = {}): CachedScanEntry | null {
    return memoryCache.get(scanCacheKey(link, context)) ?? null;
  },

  setCached(link: string, result: FolderScanResult, context: { authMode?: AuthMode; operatorIdentity?: OperatorIdentity | null } = {}): CachedScanEntry {
    const entry: CachedScanEntry = {
      result,
      scannedAt: Date.now(),
      source: result.performance?.cacheHits ? "partially refreshed scan" : "fresh scan"
    };
    memoryCache.set(scanCacheKey(link, context), entry);
    return entry;
  },

  async scanFolder(
    link: string,
    forceRefresh = false,
    context: { authMode?: AuthMode; operatorIdentity?: OperatorIdentity | null } = {}
  ): Promise<CachedScanEntry> {
    const cached = !forceRefresh ? this.getCached(link, context) : null;
    if (cached) return { ...cached, source: "cached scan" };
    const result = await simsoftApi.scanGoogleFolder({
      folderUrl: link,
      authMode: context.authMode,
      operatorIdentity: context.operatorIdentity
    });
    return this.setCached(link, result, context);
  },

  clear(): void {
    memoryCache.clear();
  }
};
