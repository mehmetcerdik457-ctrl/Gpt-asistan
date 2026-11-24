import { createHash } from "node:crypto";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`CONFIG_NOT_SET:${name}`);
  return value;
}
export const config = {
  databaseUrl: () => required("DATABASE_URL"),
  apiToken: () => required("OMEGA_API_TOKEN"),
  approvalSecret: () => required("OMEGA_APPROVAL_SECRET"),
  openAiKey: () => required("OPENAI_API_KEY"),
  openAiModel: () => required("OPENAI_MODEL"),
  youtubeWorkerUrl: () => required("YOUTUBE_WORKER_URL"),
  youtubeWorkerToken: () => required("YOUTUBE_WORKER_TOKEN"),
  youtubeWriteEnabled: () => process.env.YOUTUBE_WRITE_ENABLED?.trim().toLowerCase() === "true",
};
export function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
