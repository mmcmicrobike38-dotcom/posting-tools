import { HashRouter } from "react-router-dom";
import { SimLoansV3App } from "./app/SimLoansV3App";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { LoanOfficePage } from "./components/pages/LoanOfficePage";
import { LoginPage } from "./components/pages/LoginPage";
import { useSimsoftDashboard } from "./hooks/useSimsoftDashboard";
import { useAppUpdater } from "./services/updateService";
import "./styles.css";

function PostingApp({ updater }: { updater: ReturnType<typeof useAppUpdater> }) {
  const dashboard = useSimsoftDashboard();

  if (!dashboard.state.status?.configReady || !dashboard.state.operatorIdentity?.signedIn) return <LoginPage dashboard={dashboard} />;
  return <DashboardLayout dashboard={dashboard} updater={updater} />;
}

function isSimLoansV3Route() {
  return new URLSearchParams(window.location.search).get("app") === "simloans-v3";
}

export function App() {
  const updater = useAppUpdater();

  if (isSimLoansV3Route()) {
    return (
      <HashRouter>
        <SimLoansV3App />
      </HashRouter>
    );
  }

  if (window.location.hash === "#simloans") return <LoanOfficePage />;
  return <PostingApp updater={updater} />;
}
