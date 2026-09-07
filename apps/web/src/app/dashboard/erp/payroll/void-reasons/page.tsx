import type { Metadata } from "next";

import { ModuleAccessBoundary } from "@/components/dashboard/shared/module-access-boundary";
import { VoidReasonReportClient } from "./void-reason-report";

export const metadata: Metadata = {
  title: "Void reasons",
};

export default function VoidReasonsPage() {
  return (
    <ModuleAccessBoundary module="erp" permission="erp.payroll.approve">
      <VoidReasonReportClient />
    </ModuleAccessBoundary>
  );
}