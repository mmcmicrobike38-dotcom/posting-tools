import type { LucideIcon } from "lucide-react";

export type NavigationItem = {
  title: string;
  path: string;
  icon: LucideIcon;
  description: string;
};

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

export type RouteDefinition = NavigationItem & {
  group: string;
};
