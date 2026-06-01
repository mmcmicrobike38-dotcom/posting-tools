import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import type { AppUpdateController } from "../../services/updateService";
import { useDashboardShortcuts } from "../../hooks/useDashboardShortcuts";
import { AdvancedSettingsPage } from "../dashboard/AdvancedSettingsPage";
import { Workspace } from "../dashboard/Workspace";
import { AppModals } from "../modals/AppModals";
import { ValidationOverlay } from "./ValidationOverlay";

interface DashboardLayoutProps {
  dashboard: SimsoftDashboardModel;
  updater: AppUpdateController;
}

export function DashboardLayout({ dashboard, updater }: DashboardLayoutProps) {
  useDashboardShortcuts(dashboard);

  return (
    <main className="app-shell">
      <Workspace dashboard={dashboard} updater={updater} />
      {dashboard.state.showAdvancedSettings ? <AdvancedSettingsPage dashboard={dashboard} /> : null}
      <AppModals dashboard={dashboard} />
      <ValidationOverlay dashboard={dashboard} />
    </main>
  );
}
