/*
 * RFC 6238 time-based one-time password generator (SHA-1, 30-second period,
 * 6 digits). Used by the Playwright auth setup to complete mandatory MFA
 * enrollment without an external authenticator app.
 */

import { createHmac } from "node:crypto";

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(secret: string): Buffer {
  const cleaned = secret.toUpperCase().replace(/[^A-Z2-7]/g, "");
  const bits: number[] = [];
  for (const ch of cleaned) {
    const val = BASE32.indexOf(ch);
    if (val < 0) continue;
    for (let shift = 4; shift >= 0; shift -= 1) {
      bits.push((val >>> shift) & 1);
    }
  }
  const bytes: number[] = [];
  for (let i = 0; i + 7 < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) {
      byte = (byte << 1) | (bits[i + j] ?? 0);
    }
    bytes.push(byte);
  }
  return Buffer.from(bytes);
}

/**
 * Generate a 6-digit TOTP code from a base-32 secret.
 *
 * `offset` shifts the 30-second window (0 = current, -1 = previous) to
 * survive the boundary when the enrollment script fills the OTP input.
 */
export function totp(secret: string, offset = 0): string {
  const counter = Math.floor(Date.now() / 1000 / 30) + offset;
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const mac = createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const idx = mac[mac.length - 1] & 0x0f;
  const code =
    ((mac[idx] & 0x7f) << 24) |
    ((mac[idx + 1] & 0xff) << 16) |
    ((mac[idx + 2] & 0xff) << 8) |
    (mac[idx + 3] & 0xff);
  return String(code % 1_000_000).padStart(6, "0");
}
