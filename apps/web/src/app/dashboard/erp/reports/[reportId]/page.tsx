import { ReportsDetail } from "@/features/reports/report-detail";

interface ReportDetailPageProps {
  params: Promise<{ reportId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ReportDetailPage({
  params,
  searchParams,
}: ReportDetailPageProps) {
  const { reportId } = await params;
  const query = await searchParams;

  const initialParams: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    if (typeof value === "string") initialParams[key] = value;
  }

  return <ReportsDetail slug={reportId} initialParams={initialParams} />;
}