import { Bell, Menu, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { theme } from "../../app/theme";
import { useAppStore } from "../../store/useAppStore";

export function Header() {
  const sidebarCollapsed = useAppStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const operatorName = useAppStore((state) => state.operatorName);

  return (
    <header className="slv3-header">
      <div className="slv3-header__brand">
        <button className="slv3-icon-button" type="button" onClick={toggleSidebar} aria-label="Toggle sidebar">
          {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <div>
          <strong>{theme.appName}</strong>
          <span>Loan Servicing and Collection CRM</span>
        </div>
      </div>
      <div className="slv3-header__search">
        <Search size={16} />
        <input placeholder="Search account, customer, receipt, collector" aria-label="Global search" />
      </div>
      <div className="slv3-header__actions">
        <button className="slv3-icon-button" type="button" aria-label="Open notifications"><Bell size={18} /></button>
        <button className="slv3-icon-button slv3-header__menu" type="button" aria-label="Open menu"><Menu size={18} /></button>
        <div className="slv3-user-chip">
          <span>{operatorName.slice(0, 1)}</span>
          <strong>{operatorName}</strong>
        </div>
      </div>
    </header>
  );
}
