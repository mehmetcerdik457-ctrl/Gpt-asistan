import { authorized, jsonError } from "@/lib/auth";
import { config } from "@/lib/system-config";
export const runtime = "nodejs";
export async function GET(request: Request) {
  if (!authorized(request)) return jsonError("UNAUTHORIZED", 401);
  const url = new URL(request.url).searchParams.get("url") ?? "";
  let parsed: URL;
  try { parsed = new URL(url); } catch { return jsonError("INVALID_URL", 400); }
  if (!["https:", "http:"].includes(parsed.protocol) || !["youtube.com","www.youtube.com","youtu.be","m.youtube.com"].includes(parsed.hostname)) return jsonError("YOUTUBE_URL_REQUIRED", 400);
  try {
    const base = new URL(config.youtubeWorkerUrl());
    if (base.protocol !== "https:") return jsonError("YOUTUBE_WORKER_HTTPS_REQUIRED", 503);
    const response = await fetch(new URL("/metadata", base), { method: "POST", headers: { Authorization: `Bearer ${config.youtubeWorkerToken()}`, "Content-Type": "application/json" }, body: JSON.stringify({ url }), signal: AbortSignal.timeout(95000), cache: "no-store" });
    if (!response.ok) return jsonError("YOUTUBE_WORKER_FAILED", 502);
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch { return jsonError("YOUTUBE_WORKER_NOT_CONFIGURED_OR_UNAVAILABLE", 503); }
}