import { authorized, jsonError } from "@/lib/auth";
import { verifyApproval } from "@/lib/approval-manager";
import { approveWorkflow } from "@/lib/agent-workflow";
export const runtime = "nodejs";
export async function POST(request: Request, context: { params: Promise<{ taskId: string }> }) {
  if (!authorized(request)) return jsonError("UNAUTHORIZED", 401);
  const { taskId } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(taskId)) return jsonError("INVALID_TASK_ID", 400);
  let body: Record<string, unknown>;
  try { body = await request.json(); } catch { return jsonError("INVALID_JSON", 400); }
  const decision = body.decision;
  const timestamp = request.headers.get("x-omega-approval-timestamp") ?? "";
  const proof = request.headers.get("x-omega-approval-proof") ?? "";
  if (decision !== "approve" && decision !== "reject") return jsonError("INVALID_DECISION", 400);
  if (!verifyApproval(taskId, decision, timestamp, proof)) return jsonError("APPROVAL_PROOF_DENIED", 403);
  try {
    const result = await approveWorkflow(taskId, decision);
    return result ? Response.json({ ok: true, ...result }) : jsonError("TASK_NOT_PENDING", 409);
  } catch { return jsonError("WORKFLOW_STORAGE_UNAVAILABLE", 503); }
}