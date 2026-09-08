/**
 * Payroll API client (settings, runs, entries, compensation).
 *
 * Mirrors identity-api.ts: calls go through the same-origin /api/v1/* BFF
 * proxy, payloads are mapped from snake_case over the wire to camelCase here,
 * and every failure surfaces an `ApiError` the UI can render inline.
 */

import { ApiError, apiFetch, apiFetchRaw, apiList, apiPost, buildQueryString, type Paginated } from "@/lib/api/http";

export type PayrollRunStatus = "draft" | "computed" | "approved" | "paid" | "void";
export type PayrollJeBridgeStatus = "none" | "pending" | "draft";

export type PayrollRounding = "nearest" | "up" | "down";

export interface Money {
  amount: string;
  currency: string;
}

export interface PayrollSettings {
  tenantId: string;
  defaultCurrency: string;
  pfRate: string;
  taxRate: string;
  rounding: PayrollRounding;
  aiAutomationEnabled: boolean;
  jeBridgeEnabled: boolean;
}

export interface PayrollRun {
  id: string;
  runCode: string;
  periodStart: string;
  periodEnd: string;
  status: PayrollRunStatus;
  totalGross: Money | null;
  totalNet: Money | null;
  computedBy: string | null;
  approvedBy: string | null;
  paidBy: string | null;
  computedAt: string | null;
  approvedAt: string | null;
  paidAt: string | null;
  voidReason: string | null;
  skippedEmployees: SkippedEmployee[];
  jeBridgeStatus: PayrollJeBridgeStatus;
  createdAt: string;
}

export type SkippedCategory = "skip" | "risk";

export interface SkippedEmployee {
  employeeId: string;
  reason: string;
  reasonCode: string;
  category: SkippedCategory;
}

export interface PayrollEntry {
  id: string;
  employeeId: string;
  baseSalary: Money;
  payDays: number;
  gross: Money;
  deductions: Money;
  net: Money;
  adjustments: Record<string, unknown> | null;
  createdAt: string;
}

export interface RunComputeResult {
  run: PayrollRun;
  entries: PayrollEntry[];
  skipped: SkippedEmployee[];
}

export interface DepartmentProjection {
  departmentId: string | null;
  departmentName: string;
  predictedGross: Money;
  predictedNet: Money;
  employeeCount: number;
  previousNet: Money | null;
  deltaPct: string | null;
  drifted: boolean;
}

export interface RunPrediction {
  runId: string;
  predictedTotalGross: Money;
  predictedTotalNet: Money;
  driftThresholdPct: string;
  departments: DepartmentProjection[];
  previousRun: PayrollRun | null;
  predictedSkipped: SkippedEmployee[];
}

export interface Compensation {
  id: string;
  employeeId: string;
  monthlySalary: Money;
  effectiveFrom: string;
  isActive: boolean;
  createdAt: string;
}

export interface Payslip {
  employeeId: string;
  employeeNumber: string;
  employeeName: string;
  gross: Money;
  deductions: Money;
  net: Money;
}

export type PayslipReviewStatus = "draft" | "approved" | "rejected";

export interface PayslipReview {
  id: string;
  runId: string;
  employeeId: string;
  employeeNumber: string;
  employeeName: string;
  gross: Money;
  deductions: Money;
  net: Money;
  status: PayslipReviewStatus;
  version: number;
  rejectedReason: string | null;
  reviewedBy: string | null;
  reviewedAt: string | null;
  rejectedBy: string | null;
  rejectedAt: string | null;
  createdAt: string;
}

interface MoneyPayload {
  amount?: unknown;
  currency?: unknown;
}

interface PayrollSettingsPayload {
  tenant_id?: unknown;
  default_currency?: unknown;
  pf_rate?: unknown;
  tax_rate?: unknown;
  rounding?: unknown;
  ai_automation_enabled?: unknown;
  je_bridge_enabled?: unknown;
}

interface PayrollRunPayload {
  id?: unknown;
  run_code?: unknown;
  period_start?: unknown;
  period_end?: unknown;
  status?: unknown;
  total_gross?: MoneyPayload | null;
  total_net?: MoneyPayload | null;
  computed_by?: unknown;
  approved_by?: unknown;
  paid_by?: unknown;
  computed_at?: unknown;
  approved_at?: unknown;
  paid_at?: unknown;
  void_reason?: unknown;
  skipped_employees?: unknown;
  je_bridge_status?: unknown;
  created_at?: unknown;
}

interface PayrollEntryPayload {
  id?: unknown;
  employee_id?: unknown;
  base_salary?: MoneyPayload | null;
  pay_days?: unknown;
  gross?: MoneyPayload | null;
  deductions?: MoneyPayload | null;
  net?: MoneyPayload | null;
  adjustments?: unknown;
  created_at?: unknown;
}

interface CompensationPayload {
  id?: unknown;
  employee_id?: unknown;
  monthly_salary?: MoneyPayload | null;
  effective_from?: unknown;
  is_active?: unknown;
  created_at?: unknown;
}

interface PayslipPayload {
  employee_id?: unknown;
  employee_number?: unknown;
  employee_name?: unknown;
  gross?: MoneyPayload | null;
  deductions?: MoneyPayload | null;
  net?: MoneyPayload | null;
}

interface PayslipReviewPayload {
  id?: unknown;
  run_id?: unknown;
  employee_id?: unknown;
  employee_number?: unknown;
  employee_name?: unknown;
  gross?: MoneyPayload | null;
  deductions?: MoneyPayload | null;
  net?: MoneyPayload | null;
  status?: unknown;
  version?: unknown;
  rejected_reason?: unknown;
  reviewed_by?: unknown;
  reviewed_at?: unknown;
  rejected_by?: unknown;
  rejected_at?: unknown;
  created_at?: unknown;
}

interface DepartmentProjectionPayload {
  department_id?: unknown;
  department_name?: unknown;
  predicted_gross?: MoneyPayload | null;
  predicted_net?: MoneyPayload | null;
  employee_count?: unknown;
  previous_net?: MoneyPayload | null;
  delta_pct?: unknown;
  drifted?: unknown;
}

interface RunPredictionPayload {
  run_id?: unknown;
  predicted_total_gross?: MoneyPayload | null;
  predicted_total_net?: MoneyPayload | null;
  drift_threshold_pct?: unknown;
  departments?: unknown;
  previous_run?: PayrollRunPayload | null;
  predicted_skipped?: unknown;
}

function mapMoney(payload: MoneyPayload | null | undefined): Money | null {
  if (!payload) return null;
  return {
    amount: String(payload.amount ?? ""),
    currency: String(payload.currency ?? "USD"),
  };
}

function mapPayrollSettings(payload: PayrollSettingsPayload | null): PayrollSettings | null {
  if (!payload) return null;
  return {
    tenantId: String(payload.tenant_id ?? ""),
    defaultCurrency: String(payload.default_currency ?? "USD"),
    pfRate: String(payload.pf_rate ?? "0"),
    taxRate: String(payload.tax_rate ?? "0"),
    rounding: String(payload.rounding ?? "nearest") as PayrollRounding,
    aiAutomationEnabled: payload.ai_automation_enabled !== false,
    jeBridgeEnabled: payload.je_bridge_enabled !== false,
  };
}

function mapSkippedEmployees(value: unknown): SkippedEmployee[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const row = item as { employee_id?: unknown; reason?: unknown; reason_code?: unknown; category?: unknown };
    return {
      employeeId: String(row.employee_id ?? ""),
      reason: String(row.reason ?? ""),
      reasonCode: String(row.reason_code ?? ""),
      category: row.category === "risk" ? "risk" : "skip",
    };
  });
}

function mapPayrollRun(payload: PayrollRunPayload): PayrollRun {
  return {
    id: String(payload.id ?? ""),
    runCode: String(payload.run_code ?? ""),
    periodStart: String(payload.period_start ?? ""),
    periodEnd: String(payload.period_end ?? ""),
    status: String(payload.status ?? "draft") as PayrollRunStatus,
    totalGross: mapMoney(payload.total_gross),
    totalNet: mapMoney(payload.total_net),
    computedBy: typeof payload.computed_by === "string" ? payload.computed_by : null,
    approvedBy: typeof payload.approved_by === "string" ? payload.approved_by : null,
    paidBy: typeof payload.paid_by === "string" ? payload.paid_by : null,
    computedAt: typeof payload.computed_at === "string" ? payload.computed_at : null,
    approvedAt: typeof payload.approved_at === "string" ? payload.approved_at : null,
    paidAt: typeof payload.paid_at === "string" ? payload.paid_at : null,
    voidReason: typeof payload.void_reason === "string" ? payload.void_reason : null,
    skippedEmployees: mapSkippedEmployees(payload.skipped_employees),
    jeBridgeStatus: String(payload.je_bridge_status ?? "none") as PayrollJeBridgeStatus,
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapPayrollEntry(payload: PayrollEntryPayload): PayrollEntry {
  return {
    id: String(payload.id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    baseSalary: mapMoney(payload.base_salary) ?? { amount: "0", currency: "USD" },
    payDays: typeof payload.pay_days === "number" ? payload.pay_days : 0,
    gross: mapMoney(payload.gross) ?? { amount: "0", currency: "USD" },
    deductions: mapMoney(payload.deductions) ?? { amount: "0", currency: "USD" },
    net: mapMoney(payload.net) ?? { amount: "0", currency: "USD" },
    adjustments:
      payload.adjustments !== null && typeof payload.adjustments === "object"
        ? (payload.adjustments as Record<string, unknown>)
        : null,
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapCompensation(payload: CompensationPayload): Compensation {
  return {
    id: String(payload.id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    monthlySalary: mapMoney(payload.monthly_salary) ?? { amount: "0", currency: "USD" },
    effectiveFrom: String(payload.effective_from ?? ""),
    isActive: payload.is_active !== false,
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapPayslip(payload: PayslipPayload): Payslip {
  return {
    employeeId: String(payload.employee_id ?? ""),
    employeeNumber: String(payload.employee_number ?? ""),
    employeeName: String(payload.employee_name ?? ""),
    gross: mapMoney(payload.gross) ?? { amount: "0", currency: "USD" },
    deductions: mapMoney(payload.deductions) ?? { amount: "0", currency: "USD" },
    net: mapMoney(payload.net) ?? { amount: "0", currency: "USD" },
  };
}

function mapPayslipReview(payload: PayslipReviewPayload): PayslipReview {
  return {
    id: String(payload.id ?? ""),
    runId: String(payload.run_id ?? ""),
    employeeId: String(payload.employee_id ?? ""),
    employeeNumber: String(payload.employee_number ?? ""),
    employeeName: String(payload.employee_name ?? ""),
    gross: mapMoney(payload.gross) ?? { amount: "0", currency: "USD" },
    deductions: mapMoney(payload.deductions) ?? { amount: "0", currency: "USD" },
    net: mapMoney(payload.net) ?? { amount: "0", currency: "USD" },
    status: String(payload.status ?? "draft") as PayslipReviewStatus,
    version: typeof payload.version === "number" ? payload.version : 1,
    rejectedReason: typeof payload.rejected_reason === "string" ? payload.rejected_reason : null,
    reviewedBy: typeof payload.reviewed_by === "string" ? payload.reviewed_by : null,
    reviewedAt: typeof payload.reviewed_at === "string" ? payload.reviewed_at : null,
    rejectedBy: typeof payload.rejected_by === "string" ? payload.rejected_by : null,
    rejectedAt: typeof payload.rejected_at === "string" ? payload.rejected_at : null,
    createdAt: String(payload.created_at ?? ""),
  };
}

function mapRunPrediction(payload: RunPredictionPayload | null): RunPrediction | null {
  if (!payload) return null;
  const departments = Array.isArray(payload.departments)
    ? payload.departments.map((item) => {
        const row = item as DepartmentProjectionPayload;
        return {
          departmentId: typeof row.department_id === "string" ? row.department_id : null,
          departmentName: String(row.department_name ?? "Unassigned"),
          predictedGross: mapMoney(row.predicted_gross) ?? { amount: "0", currency: "USD" },
          predictedNet: mapMoney(row.predicted_net) ?? { amount: "0", currency: "USD" },
          employeeCount: typeof row.employee_count === "number" ? row.employee_count : 0,
          previousNet: mapMoney(row.previous_net),
          deltaPct: typeof row.delta_pct === "string" ? row.delta_pct : null,
          drifted: row.drifted === true,
        };
      })
    : [];
  return {
    runId: String(payload.run_id ?? ""),
    predictedTotalGross: mapMoney(payload.predicted_total_gross) ?? { amount: "0", currency: "USD" },
    predictedTotalNet: mapMoney(payload.predicted_total_net) ?? { amount: "0", currency: "USD" },
    driftThresholdPct: String(payload.drift_threshold_pct ?? "0.1"),
    departments,
    previousRun: payload.previous_run ? mapPayrollRun(payload.previous_run) : null,
    predictedSkipped: mapSkippedEmployees(payload.predicted_skipped),
  };
}

export async function getPayrollSettings(): Promise<PayrollSettings | null> {
  const raw = await apiFetch<PayrollSettingsPayload | null>("/api/v1/payroll/settings");
  return mapPayrollSettings(raw ?? null);
}

export async function updatePayrollSettings(input: {
  defaultCurrency?: string;
  pfRate?: string;
  taxRate?: string;
  rounding?: PayrollRounding;
  aiAutomationEnabled?: boolean;
  jeBridgeEnabled?: boolean;
}): Promise<PayrollSettings> {
  const raw = await apiFetch<PayrollSettingsPayload>("/api/v1/payroll/settings", {
    method: "PUT",
    body: JSON.stringify({
      default_currency: input.defaultCurrency,
      pf_rate: input.pfRate,
      tax_rate: input.taxRate,
      rounding: input.rounding,
      ai_automation_enabled: input.aiAutomationEnabled,
      je_bridge_enabled: input.jeBridgeEnabled,
    }),
  });
  const settings = mapPayrollSettings(raw ?? null);
  if (!settings) throw new ApiError(502, "Settings update returned an empty response.");
  return settings;
}

export async function createPayrollRun(input: {
  periodStart: string;
  periodEnd: string;
}): Promise<PayrollRun> {
  const raw = await apiPost<PayrollRunPayload>("/api/v1/payroll/runs", {
    period_start: input.periodStart,
    period_end: input.periodEnd,
  });
  return mapPayrollRun(raw ?? {});
}

export async function listPayrollRuns(input: {
  page?: number;
  pageSize?: number;
  status?: PayrollRunStatus;
} = {}): Promise<Paginated<PayrollRun>> {
  const result = await apiList<PayrollRunPayload>("/api/v1/payroll/runs", {
    page: input.page,
    pageSize: input.pageSize,
    query: { status: input.status },
  });
  return { items: result.items.map(mapPayrollRun), meta: result.meta };
}

export async function getPayrollRun(runId: string): Promise<PayrollRun> {
  const raw = await apiFetch<PayrollRunPayload>(`/api/v1/payroll/runs/${runId}`);
  return mapPayrollRun(raw ?? {});
}

export async function getRunPrediction(runId: string): Promise<RunPrediction | null> {
  const raw = await apiFetch<RunPredictionPayload | null>(
    `/api/v1/payroll/runs/${runId}/prediction`,
  );
  return mapRunPrediction(raw ?? null);
}

export async function computePayrollRun(runId: string): Promise<RunComputeResult> {
  const raw = await apiPost<{
    run?: PayrollRunPayload;
    entries?: PayrollEntryPayload[];
    skipped?: unknown;
  }>(`/api/v1/payroll/runs/${runId}/compute`, {});
  return {
    run: mapPayrollRun(raw?.run ?? {}),
    entries: Array.isArray(raw?.entries) ? raw.entries.map(mapPayrollEntry) : [],
    skipped: mapSkippedEmployees(raw?.skipped),
  };
}

export async function approvePayrollRun(runId: string): Promise<PayrollRun> {
  const raw = await apiPost<PayrollRunPayload>(
    `/api/v1/payroll/runs/${runId}/approve`,
    {},
  );
  return mapPayrollRun(raw ?? {});
}

export async function markPayrollRunPaid(runId: string): Promise<PayrollRun> {
  const raw = await apiPost<PayrollRunPayload>(`/api/v1/payroll/runs/${runId}/pay`, {});
  return mapPayrollRun(raw ?? {});
}

export async function voidPayrollRun(runId: string, reason: string): Promise<PayrollRun> {
  const raw = await apiPost<PayrollRunPayload>(`/api/v1/payroll/runs/${runId}/void`, {
    reason,
  });
  return mapPayrollRun(raw ?? {});
}

export type VoidReasonCategory =
  | "duplicate"
  | "wrong_period"
  | "correction_needed"
  | "unclassified";

export interface VoidMonthCounts {
  month: string;
  duplicate: number;
  wrong_period: number;
  correction_needed: number;
  unclassified: number;
}

export interface VoidRunRef {
  runId: string;
  runCode: string;
  periodStart: string;
  reason: string;
}

export interface VoidPatternReport {
  months: VoidMonthCounts[];
  totals: Record<VoidReasonCategory, number>;
  unclassifiedRecent: VoidRunRef[];
}

const VOID_CATEGORY_LABELS: Record<VoidReasonCategory, string> = {
  duplicate: "Duplicate",
  wrong_period: "Wrong period",
  correction_needed: "Correction needed",
  unclassified: "Unclassified",
};

export const voidCategoryLabel = (category: VoidReasonCategory): string =>
  VOID_CATEGORY_LABELS[category];

export async function getVoidReasonReport(
  months = 6,
): Promise<VoidPatternReport | null> {
  const raw = await apiFetch<{
    months?: Array<{
      month: string;
      duplicate: number;
      wrong_period: number;
      correction_needed: number;
      unclassified: number;
    }>;
    totals?: Record<VoidReasonCategory, number>;
    unclassified_recent?: Array<{
      run_id: string;
      run_code: string;
      period_start: string;
      reason: string;
    }>;
  } | null>(`/api/v1/payroll/void-reasons/report?months=${months}`);
  if (!raw) return null;
  return {
    months: (raw.months ?? []).map((row) => ({
      month: row.month,
      duplicate: row.duplicate,
      wrong_period: row.wrong_period,
      correction_needed: row.correction_needed,
      unclassified: row.unclassified,
    })),
    totals: raw.totals ?? {
      duplicate: 0,
      wrong_period: 0,
      correction_needed: 0,
      unclassified: 0,
    },
    unclassifiedRecent: (raw.unclassified_recent ?? []).map((row) => ({
      runId: row.run_id,
      runCode: row.run_code,
      periodStart: row.period_start,
      reason: row.reason,
    })),
  };
}

export async function listRunEntries(
  runId: string,
  employeeId?: string,
): Promise<PayrollEntry[]> {
  const items = await apiFetch<PayrollEntryPayload[]>(
    `/api/v1/payroll/runs/${runId}/entries${buildQueryString({ employee_id: employeeId })}`,
  );
  return (items ?? []).map(mapPayrollEntry);
}

export async function getRunPayslips(runId: string): Promise<Payslip[]> {
  const items = await apiFetch<PayslipPayload[]>(`/api/v1/payroll/runs/${runId}/payslips`);
  return (items ?? []).map(mapPayslip);
}

export async function updateRunEntry(
  runId: string,
  entryId: string,
  adjustments: Record<string, unknown>,
): Promise<PayrollEntry> {
  const raw = await apiFetch<PayrollEntryPayload>(
    `/api/v1/payroll/runs/${runId}/entries/${entryId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ adjustments }),
    },
  );
  return mapPayrollEntry(raw ?? {});
}

export async function listCompensation(employeeId: string): Promise<Compensation[]> {
  const items = await apiFetch<CompensationPayload[]>(
    `/api/v1/payroll/compensation?employee_id=${encodeURIComponent(employeeId)}`,
  );
  return (items ?? []).map(mapCompensation);
}

export async function createCompensationChange(input: {
  employeeId: string;
  effectiveFrom: string;
  monthlySalary: string;
  currency?: string;
}): Promise<Compensation> {
  const raw = await apiPost<CompensationPayload>("/api/v1/payroll/compensation", {
    employee_id: input.employeeId,
    effective_from: input.effectiveFrom,
    monthly_salary: input.monthlySalary,
    currency: input.currency,
  });
  return mapCompensation(raw ?? {});
}

export async function listPayslipReviews(input: {
  status?: PayslipReviewStatus;
  runId?: string;
} = {}): Promise<PayslipReview[]> {
  const items = await apiFetch<PayslipReviewPayload[]>(
    `/api/v1/payroll/payslips/reviews${buildQueryString({
      status: input.status,
      run_id: input.runId,
    })}`,
  );
  return (items ?? []).map(mapPayslipReview);
}

export async function approvePayslipReview(payslipId: string): Promise<PayslipReview> {
  const raw = await apiPost<PayslipReviewPayload>(
    `/api/v1/payroll/payslips/reviews/${payslipId}/approve`,
    {},
  );
  return mapPayslipReview(raw ?? {});
}

export async function rejectPayslipReview(
  payslipId: string,
  reason: string,
): Promise<PayslipReview> {
  const raw = await apiPost<PayslipReviewPayload>(
    `/api/v1/payroll/payslips/reviews/${payslipId}/reject`,
    { reason },
  );
  return mapPayslipReview(raw ?? {});
}

export async function downloadPayslipPdf(payslipId: string): Promise<void> {
  const response = await apiFetchRaw(`/api/v1/payroll/payslips/reviews/${payslipId}/pdf`);
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: { error?: { message?: string }; message?: string } | string;
    };
    const message =
      (typeof payload.detail === "object" && payload.detail?.error?.message) ||
      (typeof payload.detail === "object" && payload.detail?.message) ||
      (typeof payload.detail === "string" ? payload.detail : null) ||
      "Could not download the payslip PDF.";
    throw new ApiError(response.status, message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `payslip-${payslipId}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
