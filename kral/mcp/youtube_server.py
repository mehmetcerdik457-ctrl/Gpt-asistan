#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SERVER_NAME = "kral-youtube"
SERVER_VERSION = "1.0.0"
_TOKEN_CACHE: dict[str, object] = {"token": None, "expires_at": 0.0}

READ_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
WRITE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def status() -> dict:
    return {
        "client_id_configured": bool(os.getenv("YOUTUBE_CLIENT_ID", "").strip()),
        "client_secret_configured": bool(os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()),
        "refresh_token_configured": bool(os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()),
        "write_enabled": _bool_env("YOUTUBE_WRITE_ENABLED"),
        "required_read_scopes": READ_SCOPES,
        "required_write_scope": WRITE_SCOPE,
    }


def _http_json(req: urllib.request.Request, timeout: int = 30) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == 2:
                reason = f"HTTP {exc.code}"
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    message = (payload.get("error") or {}).get("message")
                    if message:
                        reason += f": {message}"
                except Exception:
                    pass
                raise RuntimeError(f"YouTube/Google API {reason}") from None
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 2:
                raise RuntimeError("YouTube/Google API network connection failed") from exc
        time.sleep(2 ** attempt)
    raise RuntimeError("YouTube/Google API request failed") from last_error


def access_token() -> str:
    explicit = os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip()
    if explicit:
        return explicit

    cached = _TOKEN_CACHE.get("token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0)
    if isinstance(cached, str) and cached and time.time() < expires_at - 60:
        return cached

    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not client_id or not refresh_token:
        raise RuntimeError(
            "YouTube OAuth is not configured. Set YOUTUBE_CLIENT_ID and "
            "YOUTUBE_REFRESH_TOKEN in the agent secret environment."
        )

    form = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if client_secret:
        form["client_secret"] = client_secret

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    payload = _http_json(req)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Google OAuth token refresh returned no access token")
    ttl = int(payload.get("expires_in", 3600))
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = time.time() + max(60, ttl)
    return token


def api_request(
    path: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    body: dict | None = None,
    analytics: bool = False,
) -> dict:
    url = YOUTUBE_ANALYTICS_API if analytics else YOUTUBE_API + "/" + path.lstrip("/")
    if params:
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""},
            doseq=True,
        )
        if query:
            url += ("&" if "?" in url else "?") + query

    data = None
    headers = {
        "Authorization": "Bearer " + access_token(),
        "Accept": "application/json",
        "User-Agent": "kral-youtube-mcp/1",
    }
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    return _http_json(req)


def own_channel() -> dict:
    data = api_request(
        "channels",
        params={
            "part": "snippet,contentDetails,statistics",
            "mine": "true",
            "maxResults": 1,
        },
    )
    items = data.get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel is available for the authenticated account")
    return items[0]


def playlists_list(args: dict) -> dict:
    max_results = max(1, min(int(args.get("max_results", 25)), 50))
    return api_request(
        "playlists",
        params={
            "part": "snippet,contentDetails,status",
            "mine": "true",
            "maxResults": max_results,
            "pageToken": args.get("page_token"),
        },
    )


def videos_list(args: dict) -> dict:
    channel = own_channel()
    uploads = (
        channel.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads:
        raise RuntimeError("Authenticated channel has no uploads playlist")
    max_results = max(1, min(int(args.get("max_results", 25)), 50))
    return api_request(
        "playlistItems",
        params={
            "part": "snippet,contentDetails,status",
            "playlistId": uploads,
            "maxResults": max_results,
            "pageToken": args.get("page_token"),
        },
    )


def comments_list(args: dict) -> dict:
    max_results = max(1, min(int(args.get("max_results", 50)), 100))
    params = {
        "part": "snippet,replies",
        "maxResults": max_results,
        "order": args.get("order", "time"),
        "pageToken": args.get("page_token"),
    }
    video_id = str(args.get("video_id", "")).strip()
    if video_id:
        params["videoId"] = video_id
    else:
        params["allThreadsRelatedToChannelId"] = own_channel().get("id")
    return api_request("commentThreads", params=params)


def analytics_report(args: dict) -> dict:
    start_date = str(args.get("start_date", "")).strip()
    end_date = str(args.get("end_date", "")).strip()
    metrics = str(args.get("metrics", "")).strip()
    if not start_date or not end_date or not metrics:
        raise RuntimeError("start_date, end_date and metrics are required")
    return api_request(
        "",
        params={
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": metrics,
            "dimensions": args.get("dimensions"),
            "filters": args.get("filters"),
            "sort": args.get("sort"),
            "maxResults": max(1, min(int(args.get("max_results", 200)), 200)),
        },
        analytics=True,
    )


def _require_write() -> None:
    if not _bool_env("YOUTUBE_WRITE_ENABLED"):
        raise RuntimeError(
            "YouTube write tools are fail-closed. Set the Agents variable "
            "COPILOT_MCP_YOUTUBE_WRITE_ENABLED=true only when writes are intended."
        )


def video_update_metadata(args: dict) -> dict:
    _require_write()
    video_id = str(args.get("video_id", "")).strip()
    if not video_id:
        raise RuntimeError("video_id is required")

    current = api_request("videos", params={"part": "snippet", "id": video_id})
    items = current.get("items") or []
    if not items:
        raise RuntimeError("Video not found or not accessible")
    snippet = dict(items[0].get("snippet") or {})

    if args.get("title") is not None:
        snippet["title"] = str(args["title"])
    if args.get("description") is not None:
        snippet["description"] = str(args["description"])
    if args.get("category_id") is not None:
        snippet["categoryId"] = str(args["category_id"])
    if args.get("tags") is not None:
        tags = args["tags"]
        if not isinstance(tags, list) or not all(isinstance(v, str) for v in tags):
            raise RuntimeError("tags must be a list of strings")
        snippet["tags"] = tags

    keep = {
        k: v
        for k, v in snippet.items()
        if k in {
            "title", "description", "tags", "categoryId", "defaultLanguage",
            "defaultAudioLanguage", "localized",
        }
    }
    if not keep.get("title") or not keep.get("categoryId"):
        raise RuntimeError("YouTube snippet is missing mandatory title/categoryId")

    return api_request(
        "videos",
        method="PUT",
        params={"part": "snippet"},
        body={"id": video_id, "snippet": keep},
    )


def comment_moderate(args: dict) -> dict:
    _require_write()
    comment_id = str(args.get("comment_id", "")).strip()
    moderation_status = str(args.get("moderation_status", "")).strip()
    if not comment_id:
        raise RuntimeError("comment_id is required")
    if moderation_status not in {"published", "heldForReview", "rejected"}:
        raise RuntimeError("moderation_status must be published, heldForReview or rejected")
    return api_request(
        "comments/setModerationStatus",
        method="POST",
        params={
            "id": comment_id,
            "moderationStatus": moderation_status,
            "banAuthor": "true" if bool(args.get("ban_author", False)) else "false",
        },
        body={},
    )


TOOLS = [
    {
        "name": "status",
        "description": "Show YouTube integration readiness without exposing secrets.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "channel_get",
        "description": "Read the authenticated YouTube channel profile and statistics.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "videos_list",
        "description": "List videos from the authenticated channel uploads playlist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                "page_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "playlists_list",
        "description": "List playlists owned by the authenticated channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                "page_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "comments_list",
        "description": "Read comment threads for a video or the authenticated channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
                "page_token": {"type": "string"},
                "order": {"type": "string", "enum": ["time", "relevance"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "analytics_report",
        "description": "Read YouTube Analytics reports for the authenticated channel.",
        "inputSchema": {
            "type": "object",
            "required": ["start_date", "end_date", "metrics"],
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "metrics": {"type": "string"},
                "dimensions": {"type": "string"},
                "filters": {"type": "string"},
                "sort": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "video_update_metadata",
        "description": "Update video metadata. Fails unless write mode is explicitly enabled.",
        "inputSchema": {
            "type": "object",
            "required": ["video_id"],
            "properties": {
                "video_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "category_id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "comment_moderate",
        "description": "Moderate a comment. Fails unless write mode is explicitly enabled.",
        "inputSchema": {
            "type": "object",
            "required": ["comment_id", "moderation_status"],
            "properties": {
                "comment_id": {"type": "string"},
                "moderation_status": {
                    "type": "string",
                    "enum": ["published", "heldForReview", "rejected"],
                },
                "ban_author": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
]


def call_tool(name: str, args: dict) -> dict:
    if name == "status":
        return status()
    if name == "channel_get":
        return own_channel()
    if name == "videos_list":
        return videos_list(args)
    if name == "playlists_list":
        return playlists_list(args)
    if name == "comments_list":
        return comments_list(args)
    if name == "analytics_report":
        return analytics_report(args)
    if name == "video_update_metadata":
        return video_update_metadata(args)
    if name == "comment_moderate":
        return comment_moderate(args)
    raise RuntimeError(f"Unknown tool: {name}")


def rpc_result(req_id: object, result: object) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def rpc_error(req_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_rpc(message: dict) -> dict | None:
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        version = params.get("protocolVersion") or "2025-06-18"
        return rpc_result(
            req_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return rpc_result(req_id, {})
    if method == "tools/list":
        return rpc_result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        try:
            payload = call_tool(name, args)
            return rpc_result(
                req_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                    "isError": False,
                },
            )
        except RuntimeError as exc:
            return rpc_result(
                req_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
    return rpc_error(req_id, -32601, "Method not found")


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            reply = handle_rpc(message)
        except Exception as exc:
            reply = rpc_error(None, -32603, f"Internal error: {type(exc).__name__}")
        if reply is not None:
            sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main() -> int:
    if "--status" in sys.argv:
        print(json.dumps(status(), indent=2))
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
