import type { ReactNode } from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { useAppStore } from "../../store/useAppStore";
import { cn } from "../../lib/cn";
import "../../app/simloans-v3.css";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const sidebarCollapsed = useAppStore((state) => state.sidebarCollapsed);

  return (
    <div className={cn("slv3-shell", sidebarCollapsed && "slv3-shell--collapsed")}>
      <Header />
      <Sidebar />
      <main className="slv3-main">{children}</main>
      <StatusBar />
    </div>
  );
}
