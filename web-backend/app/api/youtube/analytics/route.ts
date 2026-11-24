import { authorized, jsonError } from "@/lib/auth";
export const runtime = "nodejs";
export async function GET(request: Request) {
  if (!authorized(request)) return jsonError("UNAUTHORIZED", 401);
  const q = new URL(request.url).searchParams;
  const startDate = q.get("startDate") ?? "", endDate = q.get("endDate") ?? "", metrics = q.get("metrics") ?? "";
  const date = /^\d{4}-\d{2}-\d{2}$/;
  if (!date.test(startDate) || !date.test(endDate) || startDate > endDate || !/^[A-Za-z,]+$/.test(metrics)) return jsonError("INVALID_ANALYTICS_QUERY", 400);
  const clientId = process.env.YOUTUBE_CLIENT_ID?.trim(), refresh = process.env.YOUTUBE_REFRESH_TOKEN?.trim();
  if (!clientId || !refresh) return jsonError("YOUTUBE_OAUTH_NOT_CONFIGURED", 503);
  try {
    const form = new URLSearchParams({ client_id: clientId, refresh_token: refresh, grant_type: "refresh_token" });
    const secret = process.env.YOUTUBE_CLIENT_SECRET?.trim();
    if (secret) form.set("client_secret", secret);
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: form, signal: AbortSignal.timeout(15000), cache: "no-store" });
    if (!tokenResponse.ok) return jsonError("YOUTUBE_OAUTH_REFRESH_FAILED", 502);
    const tokenData = await tokenResponse.json() as { access_token?: string };
    if (!tokenData.access_token) return jsonError("YOUTUBE_OAUTH_TOKEN_MISSING", 502);
    const params = new URLSearchParams({ ids: "channel==MINE", startDate, endDate, metrics });
    const response = await fetch(`https://youtubeanalytics.googleapis.com/v2/reports?${params}`, { headers: { Authorization: `Bearer ${tokenData.access_token}`, Accept: "application/json" }, signal: AbortSignal.timeout(30000), cache: "no-store" });
    if (!response.ok) return jsonError("YOUTUBE_ANALYTICS_API_FAILED", 502);
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch { return jsonError("YOUTUBE_ANALYTICS_UNAVAILABLE", 503); }
}