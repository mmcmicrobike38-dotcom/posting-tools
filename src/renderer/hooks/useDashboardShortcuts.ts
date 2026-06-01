import { useEffect } from "react";
import { PREVIEW_TABS } from "../lib/previewTabs";
import { SimsoftDashboardModel } from "./useSimsoftDashboard";

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return target.isContentEditable || tagName === "input" || tagName === "select" || tagName === "textarea";
}

export function useDashboardShortcuts(dashboard: SimsoftDashboardModel) {
  const { state, derived, actions } = dashboard;

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (state.activeModal) {
          actions.setActiveModal(null);
          return;
        }
        if (state.showAdvancedSettings) {
          return;
        }
        if (state.showPostingGateDetails) {
          actions.setShowPostingGateDetails(false);
        }
        return;
      }

      if (isEditableTarget(event.target) || !event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;

      const key = event.key.toLowerCase();
      const tabIndex = Number(key) - 1;
      if (tabIndex >= 0 && tabIndex < PREVIEW_TABS.length) {
        event.preventDefault();
        actions.setActiveTab(PREVIEW_TABS[tabIndex]);
        return;
      }

      if (key === "o") {
        event.preventDefault();
        if (!state.busy) void actions.chooseFile();
        return;
      }

      if (key === "r") {
        event.preventDefault();
        if (!state.busy && !state.isScanning && state.folderLinkValidation.ok) actions.setActiveModal("rescanConfirm");
        return;
      }

      if (key === "u") {
        event.preventDefault();
        if (!state.busy && state.sheetUpdateStatus !== "loading" && state.selectedBranchId) actions.setActiveModal("updateSheetConfirm");
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        if (!state.busy && (state.filePath || state.filePaths.length)) void actions.parseFile();
        return;
      }

      if (key === "p") {
        event.preventDefault();
        if (!state.busy && !state.isPosting && state.previewResult?.canPost && derived.hasNewRowsToPost) {
          actions.setActiveModal("confirmPost");
        }
        return;
      }

      if (key === "," || key === ".") {
        event.preventDefault();
        actions.setShowAdvancedSettings(true);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions, derived.hasNewRowsToPost, state]);
}
