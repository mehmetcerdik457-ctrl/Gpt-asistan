import { timingSafeEqual } from "node:crypto";
import { config } from "./system-config";
export function authorized(request: Request): boolean {
  const header = request.headers.get("authorization") ?? "";
  const supplied = Buffer.from(header.replace(/^Bearer\s+/i, ""));
  let expected: Buffer;
  try { expected = Buffer.from(config.apiToken()); } catch { return false; }
  return /^Bearer\s+/i.test(header) && supplied.length === expected.length && timingSafeEqual(supplied, expected);
}
export function jsonError(code: string, status: number) {
  return Response.json({ ok: false, error: code }, { status, headers: { "Cache-Control": "no-store" } });
}
