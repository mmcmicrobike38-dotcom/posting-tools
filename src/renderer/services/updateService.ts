import { relaunch } from "@tauri-apps/plugin-process";
import { check, type DownloadEvent } from "@tauri-apps/plugin-updater";

const UPDATE_CHECK_TIMEOUT_MS = 30_000;
const UPDATE_DOWNLOAD_TIMEOUT_MS = 15 * 60_000;

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function formatUpdateMessage(version: string, notes?: string) {
  const releaseNotes = notes?.trim();
  return `Posting Tools ${version} is available.\n\nInstall this update now?${releaseNotes ? `\n\n${releaseNotes}` : ""}`;
}

export async function runStartupUpdateCheck() {
  if (!import.meta.env.PROD || !isTauriRuntime()) return;

  try {
    const update = await check({ timeout: UPDATE_CHECK_TIMEOUT_MS });
    if (!update) return;

    const shouldInstall = window.confirm(formatUpdateMessage(update.version, update.body));
    if (!shouldInstall) return;

    let downloadedBytes = 0;
    await update.downloadAndInstall((event: DownloadEvent) => {
      if (event.event === "Started") {
        downloadedBytes = 0;
      } else if (event.event === "Progress") {
        downloadedBytes += event.data.chunkLength;
      } else if (event.event === "Finished") {
        console.info("Update package downloaded", { downloadedBytes });
      }
    }, { timeout: UPDATE_DOWNLOAD_TIMEOUT_MS });

    const shouldRestart = window.confirm("The update was installed. Restart Posting Tools now to finish?");
    if (shouldRestart) await relaunch();
  } catch (error) {
    console.error("Updater check failed", error);
  }
}
