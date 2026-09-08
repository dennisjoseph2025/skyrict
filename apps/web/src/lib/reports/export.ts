/*
 * Browser-focused helpers for saving report CSV exports. The Content-
 * Disposition filename parser is pure so its edge cases are unit-tested.
 */

/**
 * Extract a download filename from a `Content-Disposition` header value,
 * preferring the RFC 5987 `filename*` form (URL-encoded, may be quoted).
 */
export function filenameFromDisposition(
  disposition: string | null | undefined,
  fallback: string,
): string {
  if (!disposition) return fallback;

  const star = disposition.match(/filename\*=([^;]+)/i);
  if (star) {
    const encoded = star[1].trim().replace(/^UTF-8''/i, "").replace(/^"|"$/g, "");
    if (encoded) {
      try {
        return decodeURIComponent(encoded);
      } catch {
        return fallback;
      }
    }
    return fallback;
  }

  const plain = disposition.match(/filename="?([^";]+)"?/i);
  if (plain) return plain[1].trim();

  return fallback;
}

/** Download a CSV `Response` blob using its Content-Disposition filename. */
export async function saveReportCsv(response: Response, fallbackName: string): Promise<void> {
  const filename = filenameFromDisposition(
    response.headers.get("content-disposition"),
    fallbackName,
  );
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}