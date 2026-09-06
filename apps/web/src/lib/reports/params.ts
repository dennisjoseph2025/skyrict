/*
 * Pure helpers that translate a report definition's param names into form
 * fields, defaults, and deep-link query strings for the reports workspace.
 * Kept side-effect free so the param -> URL round-trip is unit-tested in
 * isolation.
 */

export interface ReportParamField {
  name: string;
  kind: "date" | "text";
  label: string;
  /**
   * Every declared param is treated as required - Core's definitions do not
   * carry per-param optional flags, and tenant_id (the only server-managed
   * param) is filtered out before this list is built.
   */
  required: boolean;
  defaultValue: string;
}

const SERVER_PARAMS = new Set(["tenant_id"]);

export function isServerParam(name: string): boolean {
  return SERVER_PARAMS.has(name);
}

export function paramKind(name: string): "date" | "text" {
  return name.endsWith("_date") ? "date" : "text";
}

export function paramLabel(name: string): string {
  return name
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function firstDayOfMonthIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
    .toISOString()
    .slice(0, 10);
}

/** Sensible per-param defaults the Run form starts from. */
export function defaultParamValue(name: string): string {
  if (name === "as_of_date" || name === "to_date") return todayIso();
  if (name === "from_date") return firstDayOfMonthIso();
  return "";
}

/** Build the ordered, tenant-filtered form fields for a definition. */
export function buildParamFields(params: string[]): ReportParamField[] {
  return params
    .filter((name) => !isServerParam(name))
    .map((name) => ({
      name,
      kind: paramKind(name),
      label: paramLabel(name),
      required: true,
      defaultValue: defaultParamValue(name),
    }));
}

/**
 * Serialize parameter values into a URL query string. Only declared params
 * survive - unknown keys and server-managed params (tenant_id) are never
 * written to the URL, so a crafted query cannot smuggle extra params.
 */
export function toQueryString(values: Record<string, string>, declared: string[]): string {
  const declaredSet = new Set(declared);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (!declaredSet.has(key) || isServerParam(key) || value === "") continue;
    query.set(key, value);
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

/**
 * Parse a search string into a param record restricted to the definition's
 * declared params. Server-managed and unknown keys are dropped.
 */
export function parseQueryParams(search: string, declared: string[]): Record<string, string> {
  const declaredSet = new Set(declared);
  const params: Record<string, string> = {};
  for (const [key, value] of new URLSearchParams(search)) {
    if (declaredSet.has(key) && !isServerParam(key) && value !== "") {
      params[key] = value;
    }
  }
  return params;
}

/** Merge deep-link URL values over the field defaults for a fresh run form. */
export function initialParamValues(
  fields: ReportParamField[],
  urlParams: Record<string, string>,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of fields) {
    values[field.name] = urlParams[field.name] ?? field.defaultValue;
  }
  return values;
}