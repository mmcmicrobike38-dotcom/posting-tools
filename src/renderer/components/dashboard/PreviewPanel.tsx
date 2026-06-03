import { memo, useMemo } from "react";
import { SheetLayoutPreview } from "../../../shared/types";
import { PreviewTab, PREVIEW_TABS } from "../../lib/previewTabs";
import { displayValue, previewTitle, usefulPreviewColumns } from "./workspaceFormatters";

const PREVIEW_ROW_LIMIT = 150;

export function shouldShowSheetLayout(layout: SheetLayoutPreview | undefined, rowCount: number) {
  return Boolean(layout?.rows.length && ((layout.updatedCells?.length ?? 0) > 0 || rowCount === 0));
}

function SheetPreviewDetail({
  title,
  columns,
  rows,
  layout,
  emptyMessage
}: {
  title: PreviewTab;
  columns: string[];
  rows: Record<string, unknown>[];
  layout?: SheetLayoutPreview;
  emptyMessage: string;
}) {
  const updatedCellKinds = useMemo(
    () => new Map((layout?.updatedCells ?? []).map((cell) => [`${cell.row}:${cell.col}`, cell.kind ?? "planned"])),
    [layout]
  );
  const displayedRows = useMemo(() => rows.slice(0, PREVIEW_ROW_LIMIT), [rows]);
  const showSheetLayout = shouldShowSheetLayout(layout, rows.length);

  return (
    <section className="sheet-preview-detail" aria-label={`${title} selected tab details`}>
      <div className="sheet-preview-detail-title">
        <h3>{previewTitle(title)}</h3>
        <span>{showSheetLayout ? `${layout?.updatedCells.length ?? 0} planned update(s)` : `${rows.length} row(s)`}</span>
      </div>
      {showSheetLayout ? (
        <div className="sheet-layout-table">
          <table>
            <tbody>
              {layout?.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  <th>{rowIndex + 1}</th>
                  {Array.from({ length: Math.max(row.length, 1) }).map((_, colIndex) => (
                    <td className={updatedCellKinds.has(`${rowIndex + 1}:${colIndex + 1}`) ? `planned-update-cell ${updatedCellKinds.get(`${rowIndex + 1}:${colIndex + 1}`)}` : ""} key={colIndex}>
                      {displayValue(row[colIndex])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : rows.length ? (
        <div className="sheet-preview-detail-table">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayedRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => (
                    <td key={column}>{displayValue(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="sheet-preview-detail-empty">
          <strong>{previewTitle(title)}</strong>
          <p>{emptyMessage}</p>
        </div>
      )}
    </section>
  );
}

interface PreviewPanelProps {
  activeTab: PreviewTab;
  activeColumns: string[];
  activeRows: Record<string, unknown>[];
  previewCounts: Record<PreviewTab, number>;
  activeSheetLayout?: SheetLayoutPreview;
  emptyPreviewMessage: string;
  onSelectTab(tab: PreviewTab): void;
}

export const PreviewPanel = memo(function PreviewPanel({
  activeTab,
  activeColumns,
  activeRows,
  previewCounts,
  activeSheetLayout,
  emptyPreviewMessage,
  onSelectTab
}: PreviewPanelProps) {
  const previewDetailColumns = useMemo(
    () => usefulPreviewColumns(activeTab, activeRows, activeColumns),
    [activeColumns, activeRows, activeTab]
  );

  return (
    <div className="sheet-preview-panel">
      <div className="review-panel-header">
        <div>
          <span>Google Sheet Preview</span>
          <h3>Tabs ready for review</h3>
        </div>
      </div>

      <div className="sheet-preview-collapsed" id="sheet-preview-grid">
        {PREVIEW_TABS.map((tab) => {
          const count = previewCounts[tab];
          return (
            <button
              key={tab}
              className={`sheet-preview-chip ${activeTab === tab ? "active" : ""} ${count ? "ready" : ""}`.trim()}
              onClick={() => onSelectTab(tab)}
              type="button"
            >
              <span>{count ? "OK" : PREVIEW_TABS.indexOf(tab) + 1}</span>
              <div>
                <strong>{previewTitle(tab)}</strong>
                <small>{count} row(s)</small>
              </div>
            </button>
          );
        })}
      </div>

      <SheetPreviewDetail
        title={activeTab}
        columns={previewDetailColumns}
        rows={activeRows}
        layout={activeSheetLayout}
        emptyMessage={emptyPreviewMessage}
      />
    </div>
  );
});
