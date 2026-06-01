import type { ReactNode } from "react";
import { Breadcrumbs } from "./Breadcrumbs";
import type { RouteDefinition } from "../../types/navigation";

type PageContainerProps = {
  route: RouteDefinition;
  children: ReactNode;
  actions?: ReactNode;
};

export function PageContainer({ route, children, actions }: PageContainerProps) {
  return (
    <section className="slv3-page">
      <Breadcrumbs route={route} />
      <div className="slv3-page__header">
        <div>
          <h1>{route.title}</h1>
          <p>{route.description}</p>
        </div>
        {actions ? <div className="slv3-page__actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
