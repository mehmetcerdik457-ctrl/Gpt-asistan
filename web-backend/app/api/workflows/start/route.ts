import { randomBytes, randomUUID } from "node:crypto";
import { authorized, jsonError } from "@/lib/auth";
import { createWorkflow } from "@/lib/storage";
import { sha256 } from "@/lib/system-config";
export const runtime = "nodejs";
export async function POST(request: Request) {
  if (!authorized(request)) return jsonError("UNAUTHORIZED", 401);
  let payload: unknown;
  try { payload = await request.json(); } catch { return jsonError("INVALID_JSON", 400); }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return jsonError("INVALID_PAYLOAD", 400);
  const body = payload as Record<string, unknown>;
  if (typeof body.prompt !== "string" || !body.prompt.trim() || body.prompt.length > 12000) return jsonError("PROMPT_REQUIRED_OR_TOO_LARGE", 400);
  const taskId = randomUUID();
  const callbackToken = randomBytes(32).toString("base64url");
  try {
    await createWorkflow(taskId, { prompt: body.prompt, metadata: body.metadata ?? null }, sha256(callbackToken));
    return Response.json({ ok: true, taskId, status: "PENDING", callbackToken }, { status: 202, headers: { "Cache-Control": "no-store" } });
  } catch { return jsonError("WORKFLOW_STORAGE_UNAVAILABLE", 503); }
}