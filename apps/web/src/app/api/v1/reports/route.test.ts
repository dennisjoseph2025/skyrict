/**
 * Contract tests for the /api/v1/reports BFF proxy segment (RPT-BE-001).
 *
 * Covers the four behaviors that make the proxy safe and useful:
 *  - GET of the bare list forwards to Core and returns the backend envelope;
 *  - Core-unreachable GET of the bare list falls back to the sample KPIs
 *    (X-Mock-Fallback header) so the widget renders while Core is down;
 *  - Core-unreachable non-list calls still return the standard 502;
 *  - state-changing methods must pass the same-origin CSRF gate.
 */

import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const callBackend = vi.fn();
const assertSameOrigin = vi.fn();
const resolveTenantSlug = vi.fn();

vi.mock("@/lib/server/auth", () => ({
  callBackend: (path: string, options?: unknown) => callBackend(path, options),
  assertSameOrigin: (request: unknown) => assertSameOrigin(request),
  resolveTenantSlug: (host: string | null | undefined) => resolveTenantSlug(host),
}));

import { DELETE, GET, PATCH, POST, PUT } from "./[...path]/route";

function nextRequest(url: string, init?: RequestInit): NextRequest {
  return new NextRequest(url, init as ConstructorParameters<typeof NextRequest>[1]);
}

describe("reports BFF proxy segment", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    resolveTenantSlug.mockReturnValue("tenant-acme");
    assertSameOrigin.mockReturnValue(true);
  });

  it("forwards the bare list GET to Core and returns the envelope", async () => {
    callBackend.mockResolvedValue({
      ok: true,
      status: 200,
      data: [{ slug: "ar_aging" }],
      payload: { data: [{ slug: "ar_aging" }], message: "1 reports" },
    });

    const response = await GET(
      nextRequest("http://tenant.localhost/api/v1/reports", {
        method: "GET",
        headers: { authorization: "Bearer abc123" },
      }),
    );

    expect(callBackend).toHaveBeenCalledWith(
      "/reports",
      expect.objectContaining({ target: "core" }),
    );
    const [path, options] = callBackend.mock.calls[0];
    expect(path).toBe("/reports");
    expect(options.token).toBe("abc123");
    expect(options.tenantSlug).toBe("tenant-acme");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      data: [{ slug: "ar_aging" }],
      message: "1 reports",
    });
  });

  it("keeps the query string when forwarding", async () => {
    callBackend.mockResolvedValue({
      ok: true,
      status: 200,
      data: [],
      payload: { data: [], message: "0 reports" },
    });

    await GET(nextRequest("http://tenant.localhost/api/v1/reports?module=finance", { method: "GET" }));

    expect(callBackend.mock.calls[0][0]).toBe("/reports?module=finance");
  });

  it("falls back to sample KPIs when Core is down for the bare list", async () => {
    callBackend.mockResolvedValue({ ok: false, status: 0, data: null, payload: {} });

    const response = await GET(
      nextRequest("http://tenant.localhost/api/v1/reports", { method: "GET" }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("x-mock-fallback")).toBe("true");
    const body = await response.json();
    expect(Array.isArray(body.data.kpis)).toBe(true);
    expect(body.data.kpis.length).toBeGreaterThan(0);
  });

  it("returns 502 when Core is down for a non-list reports call", async () => {
    callBackend.mockResolvedValue({ ok: false, status: 0, data: null, payload: {} });

    const response = await GET(
      nextRequest("http://tenant.localhost/api/v1/reports/ar_aging", { method: "GET" }),
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toMatchObject({
      detail: expect.stringContaining("unavailable"),
    });
  });

  it("forwards a run POST with the JSON body through to Core", async () => {
    callBackend.mockResolvedValue({
      ok: true,
      status: 200,
      data: { columns: ["bucket"] },
      payload: { data: { columns: ["bucket"], rows: [] } },
    });
    const request = nextRequest("http://tenant.localhost/api/v1/reports/ar_aging/run", {
      method: "POST",
      headers: { authorization: "Bearer abc123" },
      body: JSON.stringify({ params: { as_of_date: "2026-09-30" } }),
    });

    const response = await POST(request);

    expect(callBackend).toHaveBeenCalledWith(
      "/reports/ar_aging/run",
      expect.objectContaining({
        method: "POST",
        body: { params: { as_of_date: "2026-09-30" } },
      }),
    );
    expect(response.status).toBe(200);
  });

  it("requires same-origin for state-changing methods", async () => {
    assertSameOrigin.mockReturnValue(false);
    const request = nextRequest("http://tenant.localhost/api/v1/reports/ar_aging/run", {
      method: "POST",
      body: JSON.stringify({ params: {} }),
    });

    const response = await POST(request);

    expect(response.status).toBe(403);
    expect(callBackend).not.toHaveBeenCalled();
  });

  it("exports every HTTP method bound to the proxy", () => {
    expect(typeof GET).toBe("function");
    expect(typeof POST).toBe("function");
    expect(typeof PUT).toBe("function");
    expect(typeof PATCH).toBe("function");
    expect(typeof DELETE).toBe("function");
  });
});