# YouTube integration

Kral GitHub Master includes a repository-local MCP server at `kral/mcp/youtube_server.py`.

## Available tools

Read tools:

- `youtube/status`
- `youtube/channel_get`
- `youtube/videos_list`
- `youtube/playlists_list`
- `youtube/comments_list`
- `youtube/analytics_report`

Guarded write tools:

- `youtube/video_update_metadata`
- `youtube/comment_moderate`

Writes are disabled unless the repository Agents variable
`COPILOT_MCP_YOUTUBE_WRITE_ENABLED=true`.

## OAuth contract

The cloud agent receives OAuth values only from Copilot Agents secrets:

- `COPILOT_MCP_YOUTUBE_CLIENT_ID`
- `COPILOT_MCP_YOUTUBE_CLIENT_SECRET`
- `COPILOT_MCP_YOUTUBE_REFRESH_TOKEN`

Do not paste these values into chat, issues, pull requests, Actions logs, or source files.

Required read scopes:

- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`

Additional write scope:

- `https://www.googleapis.com/auth/youtube.force-ssl`

A refresh token requires one Google OAuth consent by the channel owner. Repository code cannot manufacture that consent. After the three Agents secrets are present, Kral GitHub Master can call the YouTube MCP tools directly from GitHub Copilot cloud agent.

## Safety

- OAuth access tokens are refreshed in memory and are not written to disk.
- Write operations fail closed unless explicitly enabled.
- Video metadata updates first fetch and preserve the current snippet before changing requested fields.
- No video is uploaded, published, deleted, or made public by this MCP server.
