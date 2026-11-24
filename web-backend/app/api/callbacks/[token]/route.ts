import { consumeCallback } from "@/lib/storage";
import { sha256 } from "@/lib/system-config";
import { jsonError } from "@/lib/auth";
export const runtime = "nodejs";
export async function POST(request: Request, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  if (!/^[A-Za-z0-9_-]{40,64}$/.test(token)) return jsonError("INVALID_CALLBACK_TOKEN", 404);
  let body: unknown;
  try { body = await request.json(); } catch { return jsonError("INVALID_JSON", 400); }
  const encoded = JSON.stringify(body);
  if (encoded.length > 16000) return jsonError("CALLBACK_BODY_TOO_LARGE", 413);
  try {
    const result = await consumeCallback(sha256(token), body);
    return result ? Response.json({ ok: true, ...result }) : jsonError("CALLBACK_INVALID_OR_ALREADY_USED", 404);
  } catch { return jsonError("CALLBACK_STORAGE_UNAVAILABLE", 503); }
}