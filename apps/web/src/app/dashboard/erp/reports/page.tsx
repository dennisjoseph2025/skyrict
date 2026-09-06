import { BarChart3 } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { ReportsWorkspace } from "@/features/reports/reports-workspace";

export default function ErpReportsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Cross-department dashboards and exports for your business."
        icon={BarChart3}
      />
      <ReportsWorkspace />
    </div>
  );
}