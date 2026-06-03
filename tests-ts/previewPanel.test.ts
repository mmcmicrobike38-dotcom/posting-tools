import { describe, expect, it } from "vitest";
import { shouldShowSheetLayout } from "../src/renderer/components/dashboard/PreviewPanel";
import { usefulPreviewColumns } from "../src/renderer/components/dashboard/workspaceFormatters";

describe("preview panel display decisions", () => {
  it("shows review rows instead of a sheet snapshot when no cells are planned", () => {
    expect(
      shouldShowSheetLayout(
        {
          rows: [["SCR DATE"], ["Wednesday, January 01, 2025"]],
          updatedCells: []
        },
        2
      )
    ).toBe(false);
  });

  it("keeps the sheet layout when planned cells are present", () => {
    expect(
      shouldShowSheetLayout(
        {
          rows: [["SCR DATE"], ["Monday, December 22, 2025"]],
          updatedCells: [{ row: 2, col: 2, previousValue: "", value: "1000.00" }]
        },
        1
      )
    ).toBe(true);
  });

  it("uses SCRVSBR field names for the SCRVSBR review table", () => {
    const rows = [
      {
        "SCR DATE": "2025-12-22",
        ORs: "5101",
        "SCR AMOUNT": "1000.00",
        Status: "SKIPPED",
        Issue: "DUPLICATE: Already reviewed in ACCOUNTS"
      }
    ];

    expect(usefulPreviewColumns("SCR VS BR", rows, Object.keys(rows[0]))).toEqual([
      "SCR DATE",
      "ORs",
      "SCR AMOUNT",
      "Status",
      "Issue"
    ]);
  });
});
