import { authorized, jsonError } from "@/lib/auth";
import { cancelWorkflow } from "@/lib/agent-workflow";
export const runtime = "nodejs";
export async function POST(request: Request, context: { params: Promise<{ runId: string }> }) {
  if (!authorized(request)) return jsonError("UNAUTHORIZED", 401);
  const { runId } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(runId)) return jsonError("INVALID_RUN_ID", 400);
  try {
    const result = await cancelWorkflow(runId);
    return result ? Response.json({ ok: true, ...result }) : jsonError("TASK_NOT_CANCELLABLE", 409);
  } catch { return jsonError("WORKFLOW_STORAGE_UNAVAILABLE", 503); }
}