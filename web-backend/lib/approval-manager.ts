import { createHmac, timingSafeEqual } from "node:crypto";
import { config } from "./system-config";
export function approvalProof(taskId: string, decision: "approve" | "reject", timestamp: string): string {
  return createHmac("sha256", config.approvalSecret()).update([taskId, decision, timestamp].join("\n")).digest("hex");
}
export function verifyApproval(taskId: string, decision: "approve" | "reject", timestamp: string, proof: string): boolean {
  if (!/^\d{10}$/.test(timestamp) || Math.abs(Math.floor(Date.now()/1000)-Number(timestamp)) > 300 || !/^[a-f0-9]{64}$/.test(proof)) return false;
  const expected = Buffer.from(approvalProof(taskId, decision, timestamp), "hex");
  const actual = Buffer.from(proof, "hex");
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}
