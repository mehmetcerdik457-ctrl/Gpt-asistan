import { randomUUID } from "node:crypto";
import { createWorkflow, transitionWorkflow } from "./storage";
import { runModel } from "./model-router";
export async function startWorkflow(payload: unknown) {
  const id = randomUUID();
  await createWorkflow(id, payload);
  return { taskId: id, status: "PENDING" as const };
}
export async function approveWorkflow(taskId: string, decision: "approve" | "reject") {
  const next = decision === "approve" ? "APPROVED" : "REJECTED";
  return transitionWorkflow(taskId, ["PENDING"], next);
}
export async function cancelWorkflow(runId: string) {
  return transitionWorkflow(runId, ["PENDING","RUNNING","APPROVED"], "CANCELLED");
}
export async function executeApprovedWorkflow(taskId: string, prompt: string) {
  const row = await transitionWorkflow(taskId, ["APPROVED"], "RUNNING");
  if (!row) throw new Error("WORKFLOW_NOT_APPROVED_OR_ALREADY_PROCESSED");
  try {
    const result = await runModel(prompt);
    await transitionWorkflow(taskId, ["RUNNING"], "COMPLETED", result);
    return result;
  } catch (error) {
    await transitionWorkflow(taskId, ["RUNNING"], "FAILED", { code: "EXECUTION_FAILED" });
    throw error;
  }
}
