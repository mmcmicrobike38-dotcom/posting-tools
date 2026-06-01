import { useCallback, useEffect, useRef, useState } from "react";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type DownloadEvent, type Update } from "@tauri-apps/plugin-updater";

const UPDATE_CHECK_TIMEOUT_MS = 30_000;
const UPDATE_DOWNLOAD_TIMEOUT_MS = 15 * 60_000;

type UpdateStatus = "idle" | "checking" | "available" | "downloading" | "installing" | "readyToRestart" | "error";

export interface AppUpdateController {
  status: UpdateStatus;
  version?: string;
  body?: string;
  downloadedBytes: number;
  contentLength?: number;
  error?: string;
  checkForUpdates: () => Promise<void>;
  installUpdate: () => Promise<void>;
  restartApp: () => Promise<void>;
}

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function useAppUpdater(): AppUpdateController {
  const updateRef = useRef<Update | null>(null);
  const mountedRef = useRef(true);
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [version, setVersion] = useState<string>();
  const [body, setBody] = useState<string>();
  const [downloadedBytes, setDownloadedBytes] = useState(0);
  const [contentLength, setContentLength] = useState<number>();
  const [error, setError] = useState<string>();

  const updateState = useCallback((nextStatus: UpdateStatus, nextVersion?: string, nextBody?: string) => {
    if (!mountedRef.current) return;
    setStatus(nextStatus);
    setVersion(nextVersion);
    setBody(nextBody);
  }, []);

  const checkForUpdates = useCallback(async () => {
    if (!import.meta.env.PROD || !isTauriRuntime()) {
      updateRef.current = null;
      updateState("idle");
      return;
    }

    updateState("checking");
    setError(undefined);

    try {
      const update = await check({ timeout: UPDATE_CHECK_TIMEOUT_MS });
      updateRef.current = update;
      setDownloadedBytes(0);
      setContentLength(undefined);

      if (update) {
        updateState("available", update.version, update.body);
      } else {
        updateState("idle");
      }
    } catch (nextError) {
      console.error("Updater check failed", nextError);
      setError("Update check failed");
      updateRef.current = null;
      updateState("error");
    }
  }, [updateState]);

  const restartApp = useCallback(async () => {
    await relaunch();
  }, []);

  const installUpdate = useCallback(async () => {
    const update = updateRef.current;
    if (!update || status === "downloading" || status === "installing") return;

    let receivedBytes = 0;
    setError(undefined);
    updateState("downloading", update.version, update.body);

    try {
      await update.downloadAndInstall((event: DownloadEvent) => {
        if (!mountedRef.current) return;

        if (event.event === "Started") {
          receivedBytes = 0;
          setDownloadedBytes(0);
          setContentLength(event.data.contentLength);
          updateState("downloading", update.version, update.body);
        } else if (event.event === "Progress") {
          receivedBytes += event.data.chunkLength;
          setDownloadedBytes(receivedBytes);
        } else if (event.event === "Finished") {
          updateState("installing", update.version, update.body);
        }
      }, { timeout: UPDATE_DOWNLOAD_TIMEOUT_MS });

      updateState("readyToRestart", update.version, update.body);

      const shouldRestart = window.confirm("The update was installed. Restart Posting Tools now to finish?");
      if (shouldRestart) await restartApp();
    } catch (nextError) {
      console.error("Updater install failed", nextError);
      setError("Update install failed");
      updateState("available", update.version, update.body);
    }
  }, [restartApp, status, updateState]);

  useEffect(() => {
    mountedRef.current = true;
    void checkForUpdates();

    return () => {
      mountedRef.current = false;
    };
  }, [checkForUpdates]);

  return {
    status,
    version,
    body,
    downloadedBytes,
    contentLength,
    error,
    checkForUpdates,
    installUpdate,
    restartApp
  };
}
