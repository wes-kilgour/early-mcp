# Early (Timeular) MCP Server

MCP server for [Early](https://early.app) (formerly Timeular) time tracking. Lets you read and update time entries, manage tags, and control tracking from Claude Code.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
cd ~/mcp-servers/early
uv sync
```

### Environment Variables

- `EARLY_API_KEY` — your Early/Timeular API key
- `EARLY_API_SECRET` — your Early/Timeular API secret

Get these from your [Early account settings](https://app.timeular.com/#/settings/account).

### Register with Claude Code

```bash
claude mcp add --scope user --transport stdio \
  -e EARLY_API_KEY=your-key \
  -e EARLY_API_SECRET=your-secret \
  early-timeular -- uv --directory ~/mcp-servers/early run server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `early_get_activities` | List all activities (name, ID, color) |
| `early_get_current_tracking` | Get currently running tracker |
| `early_start_tracking` | Start tracking an activity |
| `early_stop_tracking` | Stop current tracker |
| `early_edit_current_tracking` | Update note/tags on running entry |
| `early_get_time_entries` | Get entries in a date range |
| `early_create_time_entry` | Create a new time entry |
| `early_update_time_entry` | Update an existing entry (add tags, etc.) |
| `early_delete_time_entry` | Delete a time entry |
| `early_get_tags` | List all available tags |
| `early_create_tag` | Create a new tag (e.g. for a ClickUp task ID) |

## Tag Format

Tags in notes use the format `<{{|t|TAG_ID|}}>`. When reading entries, the server converts these to `#key` for readability. The raw note format is also included in responses for when you need to update entries.

### Workflow: Tag a time entry with a ClickUp task

1. `early_get_tags` — check if tag exists (e.g. `WEB-3343`)
2. `early_create_tag` — create it if not (key: `WEB-3343`, label: `WEB-3343`)
3. `early_get_time_entries` — find the entry to tag
4. `early_update_time_entry` — update the note with `<{{|t|TAG_ID|}}>`
