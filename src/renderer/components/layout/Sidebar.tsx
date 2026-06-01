import { NavLink } from "react-router-dom";
import { Landmark } from "lucide-react";
import { navigationGroups } from "../../routes/appRoutes";
import { useAppStore } from "../../store/useAppStore";

export function Sidebar() {
  const collapsed = useAppStore((state) => state.sidebarCollapsed);

  return (
    <aside className="slv3-sidebar">
      <div className="slv3-sidebar__logo">
        <span><Landmark size={20} /></span>
        {!collapsed ? <div><strong>SIMLoans V3</strong><small>Account-centric ERP</small></div> : null}
      </div>
      <nav className="slv3-nav" aria-label="Primary navigation">
        {navigationGroups.map((group) => (
          <section className="slv3-nav__group" key={group.label}>
            {!collapsed ? <p>{group.label}</p> : null}
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.path} to={item.path} className={({ isActive }) => (isActive ? "slv3-nav__item is-active" : "slv3-nav__item")} title={collapsed ? item.title : undefined}>
                  <Icon size={18} />
                  {!collapsed ? <span>{item.title}</span> : null}
                </NavLink>
              );
            })}
          </section>
        ))}
      </nav>
    </aside>
  );
}
