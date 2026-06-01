import { useMemo } from "react";
import {
  GoogleSheetPreviewResult,
  GoogleSheetStats,
  IbpPaymentBreakdowns,
  IbpParticulars,
  ParseResult
} from "../../../shared/types";
import {
  buildIbpReviewRows,
  getActiveRows,
  getEmptyPreviewMessage,
  getPreviewCounts,
  IbpReviewRow,
  isIbpReviewRequired
} from "../../features/posting/model/postingViewModel";
import { PreviewTab } from "../../lib/previewTabs";

export function usePreviewState(input: {
  activeTab: PreviewTab;
  previewResult: GoogleSheetPreviewResult | null;
  result: ParseResult | null;
  sheetStats: GoogleSheetStats | null;
  selectedBranchId: string;
  ibpParticulars: IbpParticulars;
  ibpPaymentBreakdowns: IbpPaymentBreakdowns;
}) {
  const summaryRows = useMemo(
    () => Object.entries(input.previewResult?.summary ?? input.result?.summary ?? {}),
    [input.previewResult, input.result]
  );

  const activeRows = useMemo(
    () => getActiveRows(input.activeTab, input.previewResult, input.result),
    [input.activeTab, input.previewResult, input.result]
  );

  const activeColumns = useMemo(() => {
    const columns = new Set<string>();
    for (const row of activeRows.slice(0, 25)) {
      for (const key of Object.keys(row)) {
        columns.add(key);
      }
    }
    return columns.size ? [...columns] : ["No rows"];
  }, [activeRows]);

  const previewCounts = useMemo(
    () => getPreviewCounts(input.previewResult, input.result),
    [input.previewResult, input.result]
  );

  const passedRowCount = useMemo(
    () => Number(input.previewResult?.summary?.["Passed Rows"] ?? input.result?.summary?.["Passed Rows"] ?? 0),
    [input.previewResult, input.result]
  );

  const duplicateRowCount = useMemo(
    () => Number(input.previewResult?.summary?.["Duplicate Rows"] ?? input.result?.summary?.["Duplicate Rows"] ?? 0),
    [input.previewResult, input.result]
  );

  const ibpReviewRows = useMemo<IbpReviewRow[]>(
    () =>
      buildIbpReviewRows({
        previewResult: input.previewResult,
        sheetStats: input.sheetStats,
        selectedBranchId: input.selectedBranchId,
        ibpParticulars: input.ibpParticulars
      }),
    [input.ibpParticulars, input.previewResult, input.selectedBranchId, input.sheetStats]
  );

  const ibpReviewRequired = isIbpReviewRequired(ibpReviewRows, input.ibpPaymentBreakdowns, input.ibpParticulars);

  const emptyPreviewMessage = useMemo(
    () => getEmptyPreviewMessage(activeRows.length, input.activeTab, input.previewResult),
    [activeRows.length, input.activeTab, input.previewResult]
  );

  return {
    summaryRows,
    activeRows,
    activeColumns,
    previewCounts,
    passedRowCount,
    duplicateRowCount,
    hasNewRowsToPost: passedRowCount > 0,
    ibpReviewRows,
    ibpReviewRequired,
    emptyPreviewMessage
  };
}
