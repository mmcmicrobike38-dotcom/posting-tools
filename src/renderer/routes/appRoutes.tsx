import {
  Activity,
  Banknote,
  BarChart3,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Clock3,
  FileBarChart,
  FileCheck2,
  FileClock,
  FileText,
  Gauge,
  History,
  LockKeyhole,
  Receipt,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  WalletCards,
  XCircle
} from "lucide-react";
import type { NavigationGroup, RouteDefinition } from "../types/navigation";

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Dashboard",
    items: [{ title: "Dashboard", path: "/dashboard", icon: Gauge, description: "Executive overview" }]
  },
  {
    label: "Customers",
    items: [
      { title: "Customer List", path: "/customers/list", icon: Users, description: "Customer directory" },
      { title: "Customer Profile", path: "/customers/profile", icon: UserCog, description: "Customer workspace" }
    ]
  },
  {
    label: "Accounts",
    items: [
      { title: "Active Accounts", path: "/accounts/active", icon: WalletCards, description: "Open loan accounts" },
      { title: "Fully Paid", path: "/accounts/fully-paid", icon: CheckCircle2, description: "Completed accounts" },
      { title: "Past Due", path: "/accounts/past-due", icon: Clock3, description: "Accounts behind schedule" },
      { title: "Closed Accounts", path: "/accounts/closed", icon: XCircle, description: "Closed account records" }
    ]
  },
  {
    label: "Payments",
    items: [
      { title: "Payment Posting", path: "/payments/posting", icon: Banknote, description: "Collection entry workspace" },
      { title: "Payment History", path: "/payments/history", icon: History, description: "Payment search and review" },
      { title: "Official Receipts", path: "/payments/official-receipts", icon: Receipt, description: "Receipt register" }
    ]
  },
  {
    label: "Collections",
    items: [
      { title: "Due Today", path: "/collections/due-today", icon: CalendarClock, description: "Accounts due today" },
      { title: "Due This Week", path: "/collections/due-this-week", icon: FileClock, description: "Weekly collection queue" },
      { title: "Delinquent", path: "/collections/delinquent", icon: Activity, description: "Delinquent monitoring" },
      { title: "Collector Monitoring", path: "/collections/collector-monitoring", icon: ClipboardList, description: "Collector performance board" }
    ]
  },
  {
    label: "Reports",
    items: [
      { title: "Collection Report", path: "/reports/collection", icon: FileText, description: "Collection reporting" },
      { title: "Aging Report", path: "/reports/aging", icon: BarChart3, description: "Aging analysis" },
      { title: "Rebate Report", path: "/reports/rebate", icon: FileCheck2, description: "Rebate review" },
      { title: "Branch Report", path: "/reports/branch", icon: FileBarChart, description: "Branch summary" }
    ]
  },
  {
    label: "Administration",
    items: [
      { title: "Users", path: "/administration/users", icon: UserCog, description: "User directory" },
      { title: "Roles", path: "/administration/roles", icon: ShieldCheck, description: "RBAC role setup" },
      { title: "Branches", path: "/administration/branches", icon: Building2, description: "Branch master records" },
      { title: "Audit Trail", path: "/administration/audit-trail", icon: LockKeyhole, description: "Audit event review" }
    ]
  },
  {
    label: "Settings",
    items: [{ title: "Settings", path: "/settings", icon: Settings, description: "Application preferences" }]
  }
];

export const appRoutes: RouteDefinition[] = navigationGroups.flatMap((group) =>
  group.items.map((item) => ({ ...item, group: group.label }))
);

export function findRoute(pathname: string): RouteDefinition {
  return appRoutes.find((route) => route.path === pathname) ?? appRoutes[0];
}
