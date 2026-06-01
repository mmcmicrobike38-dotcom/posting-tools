import { Link } from "react-router-dom";
import type { RouteDefinition } from "../../types/navigation";

type BreadcrumbsProps = {
  route: RouteDefinition;
};

export function Breadcrumbs({ route }: BreadcrumbsProps) {
  return (
    <nav className="slv3-breadcrumbs" aria-label="Breadcrumb">
      <Link to="/dashboard">SIMLoans V3</Link>
      <span>/</span>
      <span>{route.group}</span>
      <span>/</span>
      <strong>{route.title}</strong>
    </nav>
  );
}
