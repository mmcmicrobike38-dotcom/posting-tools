import type { ColumnDef } from "@tanstack/react-table";
import { Banknote, CalendarDays, Gauge, TrendingUp, Users, WalletCards } from "lucide-react";
import { MetricCard } from "../components/common/MetricCard";
import { PageContainer } from "../components/common/PageContainer";
import { SearchBar } from "../components/common/SearchBar";
import { SectionHeader } from "../components/common/SectionHeader";
import { DataTable } from "../components/tables/DataTable";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { findRoute } from "../routes/appRoutes";

type RecentPayment = {
  receiptNo: string;
  accountNo: string;
  customer: string;
  branch: string;
  postedBy: string;
};

type RecentActivity = {
  time: string;
  module: string;
  activity: string;
  operator: string;
};

type DueToday = {
  accountNo: string;
  customer: string;
  collector: string;
  status: string;
};

const recentPayments: RecentPayment[] = [
  { receiptNo: "OR-000184", accountNo: "ACC-2026-0011", customer: "Maria Santos", branch: "Main", postedBy: "Cashier 01" },
  { receiptNo: "OR-000185", accountNo: "ACC-2026-0042", customer: "Ramon Cruz", branch: "North", postedBy: "Cashier 02" },
  { receiptNo: "OR-000186", accountNo: "ACC-2026-0075", customer: "Lina Garcia", branch: "East", postedBy: "Cashier 01" }
];

const recentActivities: RecentActivity[] = [
  { time: "09:10", module: "Accounts", activity: "Viewed active account queue", operator: "System Operator" },
  { time: "09:28", module: "Collections", activity: "Opened due today board", operator: "System Operator" },
  { time: "10:02", module: "Reports", activity: "Prepared aging report placeholder", operator: "System Operator" }
];

const dueToday: DueToday[] = [
  { accountNo: "ACC-2026-0022", customer: "A. Santos Trading", collector: "Collector A", status: "Scheduled" },
  { accountNo: "ACC-2026-0051", customer: "Dela Cruz Store", collector: "Collector B", status: "For follow-up" },
  { accountNo: "ACC-2026-0068", customer: "Garcia Hardware", collector: "Collector C", status: "Pending" }
];

const paymentColumns: ColumnDef<RecentPayment>[] = [
  { accessorKey: "receiptNo", header: "Receipt" },
  { accessorKey: "accountNo", header: "Account" },
  { accessorKey: "customer", header: "Customer" },
  { accessorKey: "branch", header: "Branch" },
  { accessorKey: "postedBy", header: "Posted By" }
];

const activityColumns: ColumnDef<RecentActivity>[] = [
  { accessorKey: "time", header: "Time" },
  { accessorKey: "module", header: "Module" },
  { accessorKey: "activity", header: "Activity" },
  { accessorKey: "operator", header: "Operator" }
];

const dueTodayColumns: ColumnDef<DueToday>[] = [
  { accessorKey: "accountNo", header: "Account" },
  { accessorKey: "customer", header: "Customer" },
  { accessorKey: "collector", header: "Collector" },
  { accessorKey: "status", header: "Status" }
];

export function DashboardPage() {
  const dashboardRoute = findRoute("/dashboard");

  return (
    <PageContainer
      route={dashboardRoute}
      actions={<Button variant="secondary">Dashboard Settings</Button>}
    >
      <div className="slv3-dashboard-toolbar">
        <SearchBar placeholder="Search dashboard placeholder records" />
      </div>
      <section className="slv3-metric-grid">
        <MetricCard label="Total Customers" value="12,480" helper="Placeholder customer base" icon={Users} />
        <MetricCard label="Active Accounts" value="8,214" helper="Account-centric workload" icon={WalletCards} tone="success" />
        <MetricCard label="Past Due Accounts" value="642" helper="Collection monitoring queue" icon={CalendarDays} tone="warning" />
        <MetricCard label="Today's Collection" value="PHP 0.00" helper="Static placeholder value" icon={Banknote} />
        <MetricCard label="Monthly Collection" value="PHP 0.00" helper="Static placeholder value" icon={TrendingUp} tone="success" />
        <MetricCard label="Collection Rate" value="0%" helper="Pending business rules" icon={Gauge} tone="danger" />
      </section>
      <section className="slv3-dashboard-grid">
        <Card>
          <SectionHeader title="Recent Payments" description="Mock table structure for future posting data." />
          <DataTable columns={paymentColumns} data={recentPayments} />
        </Card>
        <Card>
          <SectionHeader title="Recent Activity" description="Audit-ready activity stream placeholder." />
          <DataTable columns={activityColumns} data={recentActivities} />
        </Card>
        <Card className="slv3-card--wide">
          <SectionHeader title="Due Today" description="Account-based collection queue placeholder." />
          <DataTable columns={dueTodayColumns} data={dueToday} />
        </Card>
      </section>
    </PageContainer>
  );
}
