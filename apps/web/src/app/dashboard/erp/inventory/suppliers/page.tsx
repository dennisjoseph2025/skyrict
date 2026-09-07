import { ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { SupplierRiskTable } from "@/components/dashboard/erp/inventory/supplier-risk-table";

export default function SuppliersPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="Suppliers & Risk"
                description="Supplier master and AI risk grades that drive the risk-adjusted restock model."
                icon={ShieldAlert}
            />
            <SupplierRiskTable />
        </div>
    );
}