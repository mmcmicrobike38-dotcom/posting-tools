import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { SidebarSection, UiStatus } from "../ui/Primitives";

interface TargetBranchSelectorProps {
  dashboard: SimsoftDashboardModel;
}

export function TargetBranchSelector({ dashboard }: TargetBranchSelectorProps) {
  const { state, derived, actions } = dashboard;
  const branchCount = derived.branchOptions.length;
  const hasAssignments = state.isAdmin || state.assignedBranchIds.length > 0;
  const isLoadingBranches = state.scanStatus === "scanning";
  const isUpdatingSheet = state.sheetUpdateStatus === "loading";
  const savedBranchStats = state.selectedBranchId ? state.sheetStatsByBranch[state.selectedBranchId] : null;
  const selectedSheetLoaded = Boolean(
    state.selectedBranchId &&
      savedBranchStats?.googleReady &&
      savedBranchStats.targetBranchId === state.selectedBranchId
  );
  const accountsRowCount = savedBranchStats?.accountsRowCount ?? 0;
  const status: UiStatus = isUpdatingSheet ? "loading" : selectedSheetLoaded ? "completed" : state.selectedBranchId ? "attention" : "idle";
  const statusLabel = isUpdatingSheet ? "Loading" : selectedSheetLoaded ? "Ready" : state.selectedBranchId ? "Update needed" : "No branch";

  return (
    <SidebarSection title="Target Branch" status={status} statusLabel={statusLabel} helper="Select the branch that matches the SIMSOFT export.">
      <select
        value={state.selectedBranchId}
        onChange={(event) => actions.setSelectedBranchId(event.target.value)}
        disabled={!hasAssignments || !derived.branchOptions.length || state.busy || isUpdatingSheet}
        title={!hasAssignments ? "This user has no assigned branch." : !derived.branchOptions.length ? "Scan the Drive folder first." : "Select target branch"}
      >
        <option value="">Select target branch</option>
        {derived.branchOptions.map((branch) => (
          <option key={branch.branch_id} value={branch.branch_id}>
            {branch.branch_id} - {branch.branch_name || branch.file_name}
          </option>
        ))}
      </select>
      <div className={`scan-pill branch-scan-pill ${isLoadingBranches || isUpdatingSheet ? "scanning" : selectedSheetLoaded || branchCount ? "completed" : "idle"}`}>
        {isLoadingBranches || isUpdatingSheet ? <span className="spinner" /> : <i className={selectedSheetLoaded || branchCount ? "dot online" : "dot offline"} />}
        <span>
          {isLoadingBranches ? "Loading target branches..." : null}
          {!isLoadingBranches && isUpdatingSheet ? "Loading ACCOUNTS tab..." : null}
          {!isLoadingBranches && !isUpdatingSheet && selectedSheetLoaded ? `Completed: ${accountsRowCount} Accounts` : null}
          {!isLoadingBranches && !isUpdatingSheet && !selectedSheetLoaded && state.selectedBranchId ? "Load branch sheet" : null}
          {!isLoadingBranches && !isUpdatingSheet && !selectedSheetLoaded && !state.selectedBranchId && branchCount ? "Select target branch" : null}
          {!isLoadingBranches && !isUpdatingSheet && !selectedSheetLoaded && !state.selectedBranchId && !branchCount ? "No target branch sheets loaded" : null}
        </span>
      </div>
      <span className="selected-branch">
        {!hasAssignments ? "No branch assigned to this user" : state.selectedBranchId ? state.selectedBranchId : "No branch selected"}
      </span>
      <button
        className="primary"
        onClick={() => actions.setActiveModal("updateSheetConfirm")}
        disabled={!state.selectedBranchId || state.busy || isUpdatingSheet}
        aria-label="Load selected branch sheet"
        title={state.selectedBranchId ? "Ctrl+U" : "Select target branch first."}
      >
        {isUpdatingSheet ? "Loading..." : "Load Branch Sheet"}
      </button>
    </SidebarSection>
  );
}
