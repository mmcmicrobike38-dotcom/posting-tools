import { configService } from "./configService";

export const cloudSyncService = {
  isConfigured(): boolean {
    return Boolean(configService.cloudEndpoint);
  },

  async syncAuditMetadata(): Promise<{ ok: boolean; mode: "local" | "cloud" }> {
    // Future cloud sync can plug in here without changing local posting behavior.
    return { ok: true, mode: this.isConfigured() ? "cloud" : "local" };
  }
};
