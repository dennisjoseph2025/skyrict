import { describe, expect, it } from "vitest";

import {
  buildParamFields,
  defaultParamValue,
  firstDayOfMonthIso,
  initialParamValues,
  isServerParam,
  paramKind,
  paramLabel,
  parseQueryParams,
  todayIso,
  toQueryString,
  type ReportParamField,
} from "@/lib/reports/params";

describe("isServerParam", () => {
  it("marks tenant_id as server-managed", () => {
    expect(isServerParam("tenant_id")).toBe(true);
  });

  it("leaves user-facing params alone", () => {
    expect(isServerParam("as_of_date")).toBe(false);
    expect(isServerParam("from_date")).toBe(false);
  });
});

describe("paramKind", () => {
  it("treats *_date names as date inputs", () => {
    expect(paramKind("as_of_date")).toBe("date");
    expect(paramKind("from_date")).toBe("date");
    expect(paramKind("to_date")).toBe("date");
  });

  it("treats everything else as text", () => {
    expect(paramKind("account_type")).toBe("text");
    expect(paramKind("department")).toBe("text");
  });
});

describe("paramLabel", () => {
  it("humanizes snake-case names", () => {
    expect(paramLabel("as_of_date")).toBe("As Of Date");
    expect(paramLabel("stock_on_hand_vs_reorder")).toBe("Stock On Hand Vs Reorder");
  });
});

describe("defaultParamValue", () => {
  it("defaults as-of and to dates to today", () => {
    expect(defaultParamValue("as_of_date")).toBe(todayIso());
    expect(defaultParamValue("to_date")).toBe(todayIso());
  });

  it("defaults from dates to the first of the month", () => {
    expect(defaultParamValue("from_date")).toBe(firstDayOfMonthIso());
  });

  it("defaults text params to empty", () => {
    expect(defaultParamValue("department")).toBe("");
  });
});

describe("buildParamFields", () => {
  it("filters tenant_id and derives field metadata", () => {
    const fields = buildParamFields(["tenant_id", "as_of_date", "account_type"]);
    expect(fields).toEqual<ReportParamField[]>([
      {
        name: "as_of_date",
        kind: "date",
        label: "As Of Date",
        required: true,
        defaultValue: todayIso(),
      },
      {
        name: "account_type",
        kind: "text",
        label: "Account Type",
        required: true,
        defaultValue: "",
      },
    ]);
  });

  it("returns an empty list for parameter-less reports", () => {
    expect(buildParamFields([])).toEqual([]);
  });
});

describe("toQueryString", () => {
  it("serializes declared params, skipping blanks", () => {
    expect(
      toQueryString(
        { as_of_date: "2026-09-30", account_type: "", region: "EMEA" },
        ["as_of_date", "account_type"],
      ),
    ).toBe("?as_of_date=2026-09-30");
  });

  it("never writes tenant_id or undeclared keys", () => {
    expect(
      toQueryString(
        { as_of_date: "2026-09-30", tenant_id: "t_123", sneaky: "x" },
        ["as_of_date"],
      ),
    ).toBe("?as_of_date=2026-09-30");
  });

  it("returns an empty string when nothing is serializable", () => {
    expect(toQueryString({ tenant_id: "t_123" }, ["tenant_id"])).toBe("");
  });

  it("URL-encodes special characters", () => {
    expect(toQueryString({ q: "a b&c" }, ["q"])).toBe("?q=a+b%26c");
  });
});

describe("parseQueryParams", () => {
  it("keeps only declared, non-server, non-empty params", () => {
    const search = "as_of_date=2026-09-30&tenant_id=t_123&sneaky=x&empty=&from_date=";
    expect(parseQueryParams(search, ["as_of_date", "from_date"])).toEqual({
      as_of_date: "2026-09-30",
    });
  });

  it("round-trips with toQueryString", () => {
    const declared = ["as_of_date", "from_date", "to_date"];
    const params = { as_of_date: "2026-09-30", from_date: "2026-09-01", to_date: "" };
    const query = toQueryString(params, declared);
    expect(parseQueryParams(query, declared)).toEqual({
      as_of_date: "2026-09-30",
      from_date: "2026-09-01",
    });
  });
});

describe("initialParamValues", () => {
  it("prefers deep-link values over defaults", () => {
    const fields = buildParamFields(["as_of_date", "from_date"]);
    expect(initialParamValues(fields, { as_of_date: "2026-09-30" })).toEqual({
      as_of_date: "2026-09-30",
      from_date: firstDayOfMonthIso(),
    });
  });

  it("ignores URL params that are not declared fields", () => {
    const fields = buildParamFields(["as_of_date"]);
    expect(initialParamValues(fields, { as_of_date: "2026-09-30", sneaky: "x" })).toEqual({
      as_of_date: "2026-09-30",
    });
  });
});