import type { LucideIcon } from "lucide-react";

type MetricCardProps = {
  label: string;
  value: string;
  helper: string;
  tone?: "primary" | "success" | "warning" | "danger";
  icon: LucideIcon;
};

export function MetricCard({ label, value, helper, tone = "primary", icon: Icon }: MetricCardProps) {
  return (
    <article className={`slv3-metric slv3-metric--${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{helper}</small>
      </div>
      <i><Icon size={22} /></i>
    </article>
  );
}
