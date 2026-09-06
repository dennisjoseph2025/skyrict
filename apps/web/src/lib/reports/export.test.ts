import { describe, expect, it } from "vitest";

import { filenameFromDisposition } from "@/lib/reports/export";

describe("filenameFromDisposition", () => {
  it("falls back when no disposition header exists", () => {
    expect(filenameFromDisposition(null, "cash_received.csv")).toBe("cash_received.csv");
    expect(filenameFromDisposition(undefined, "cash_received.csv")).toBe("cash_received.csv");
  });

  it("parses the plain filename= form", () => {
    expect(filenameFromDisposition('attachment; filename="ar_aging.csv"', "fallback.csv")).toBe(
      "ar_aging.csv",
    );
    expect(filenameFromDisposition("attachment; filename=ar_aging.csv", "fallback.csv")).toBe(
      "ar_aging.csv",
    );
  });

  it("prefers and decodes the RFC 5987 filename*= form", () => {
    expect(
      filenameFromDisposition("attachment; filename*=UTF-8''cash%20received.csv", "fallback.csv"),
    ).toBe("cash received.csv");
    expect(
      filenameFromDisposition('attachment; filename*=UTF-8\'\'"cash%20received.csv"', "fallback.csv"),
    ).toBe("cash received.csv");
  });

  it("falls back on malformed percent-encoding", () => {
    expect(
      filenameFromDisposition("attachment; filename*=UTF-8''bad%2", "fallback.csv"),
    ).toBe("fallback.csv");
  });

  it("falls back when neither form is present", () => {
    expect(filenameFromDisposition("attachment", "fallback.csv")).toBe("fallback.csv");
  });
});