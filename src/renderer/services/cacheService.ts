import { scanService } from "./scanService";

export const cacheService = {
  clearLocalCaches(): void {
    scanService.clear();
  }
};
