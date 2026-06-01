import { EmptyState } from "../components/common/EmptyState";
import { PageContainer } from "../components/common/PageContainer";
import { SectionHeader } from "../components/common/SectionHeader";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import type { RouteDefinition } from "../types/navigation";

type PlaceholderPageProps = {
  route: RouteDefinition;
};

export function PlaceholderPage({ route }: PlaceholderPageProps) {
  const Icon = route.icon;

  return (
    <PageContainer route={route} actions={<Button variant="secondary">Configure Module</Button>}>
      <Card>
        <SectionHeader
          title={`${route.title} Workspace`}
          description="This placeholder page reserves the route, layout, and component contract for future implementation."
        />
        <EmptyState
          icon={Icon}
          title="No module functionality implemented yet"
          description="Database access, authentication, business rules, payment processing, reports, and backend behavior are intentionally excluded from this foundation."
        />
      </Card>
    </PageContainer>
  );
}
