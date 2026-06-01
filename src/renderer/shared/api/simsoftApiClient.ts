import { SimsoftApi } from "../../../shared/types";

export type SimsoftApiClient = SimsoftApi;

let activeClient: SimsoftApiClient | null = null;
const SIMSOFT_API_METHODS = new Set<keyof SimsoftApi>([
  "getStatus",
  "saveAccessConfig",
  "requestAccess",
  "openGoogleTestUsersPage",
  "openSupportFolder",
  "chooseSimsoftFile",
  "chooseSimsoftFiles",
  "parseSimsoftFile",
  "parseSimsoftFiles",
  "scanGoogleFolder",
  "getGoogleSheetStats",
  "buildGooglePreviews",
  "postGooglePreviews",
  "getOperatorIdentity",
  "loginGoogleOperator",
  "logoutGoogleOperator",
  "getDuplicateHistoryStatus",
  "resetDuplicateHistory",
  "clearCache",
  "runHealthCheck"
]);

export function getSimsoftApiClient(): SimsoftApiClient {
  if (activeClient) return activeClient;
  if (!window.simsoft) throw new Error("SIMSOFT desktop API is not ready.");
  return window.simsoft;
}

export function setSimsoftApiClient(client: SimsoftApiClient): void {
  activeClient = client;
}

export function resetSimsoftApiClient(): void {
  activeClient = null;
}

export const simsoftApi = new Proxy({} as SimsoftApiClient, {
  get(_target, property: keyof SimsoftApiClient) {
    if (!SIMSOFT_API_METHODS.has(property)) {
      throw new Error("Blocked unknown SIMSOFT API method.");
    }
    const value = getSimsoftApiClient()[property];
    if (typeof value !== "function") {
      throw new Error("SIMSOFT API method is unavailable.");
    }
    return value.bind(getSimsoftApiClient());
  }
});
