import { Database, ShieldCheck, Wifi } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useAppStore } from "../../store/useAppStore";

export function StatusBar() {
  const location = useLocation();
  const statusMessage = useAppStore((state) => state.statusMessage);

  return (
    <footer className="slv3-statusbar">
      <span><Wifi size={14} /> Local UI Mode</span>
      <span><Database size={14} /> Repository layer not connected</span>
      <span><ShieldCheck size={14} /> RBAC ready</span>
      <strong>{statusMessage}</strong>
      <code>{location.pathname}</code>
    </footer>
  );
}
