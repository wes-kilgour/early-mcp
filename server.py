"""MCP server for Early (Timeular) time tracking."""

import os
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.timeular.com/api/v3"

mcp = FastMCP("early-timeular")

_token: str | None = None
_http: httpx.AsyncClient | None = None


async def _client() -> httpx.AsyncClient:
    """Return an authenticated httpx client, signing in on first use."""
    global _token, _http

    if _http is not None:
        return _http

    api_key = os.environ.get("EARLY_API_KEY")
    api_secret = os.environ.get("EARLY_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("EARLY_API_KEY and EARLY_API_SECRET env vars required")

    async with httpx.AsyncClient() as tmp:
        resp = await tmp.post(
            f"{BASE_URL}/developer/sign-in",
            json={"apiKey": api_key, "apiSecret": api_secret},
        )
        resp.raise_for_status()
        _token = resp.json()["token"]

    _http = httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {_token}"},
        timeout=30,
    )
    return _http


def _to_api_ts(dt_str: str) -> str:
    """Convert YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS to API timestamp format.

    The Timeular API expects ISO 8601 with millisecond precision.
    """
    dt_str = dt_str.strip()
    if len(dt_str) == 10:  # YYYY-MM-DD
        return f"{dt_str}T00:00:00.000"
    if "." not in dt_str:
        return f"{dt_str}.000"
    return dt_str


def _now_api_ts() -> str:
    """Return current UTC time in API timestamp format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def _end_of_day_api_ts(date_str: str) -> str:
    """Convert YYYY-MM-DD to end-of-day API timestamp."""
    return f"{date_str.strip()}T23:59:59.999"


def _format_note(note: dict | None) -> str:
    """Format a note object from the API into readable text."""
    if not note:
        return ""
    text = note.get("text", "")
    tags = note.get("tags", [])
    mentions = note.get("mentions", [])
    # Replace tag placeholders with readable labels
    for tag in tags:
        tag_id = tag.get("id")
        key = tag.get("key", "")
        indices = tag.get("indices", [])
        if indices:
            # The text contains <{{|t|ID|}}> which we can replace
            text = text.replace(f"<{{{{|t|{tag_id}|}}}}>" , f"#{key}")
    for mention in mentions:
        m_id = mention.get("id")
        key = mention.get("key", "")
        text = text.replace(f"<{{{{|m|{m_id}|}}}}>" , f"@{key}")
    return text.strip()


def _format_entry(entry: dict) -> dict:
    """Format a time entry for display."""
    duration = entry.get("duration", {})
    return {
        "id": entry.get("id"),
        "activity_id": entry.get("activityId"),
        "activity_name": entry.get("activity", {}).get("name", ""),
        "started_at": duration.get("startedAt", ""),
        "stopped_at": duration.get("stoppedAt", ""),
        "note": _format_note(entry.get("note")),
        "note_raw": entry.get("note"),
    }


@mcp.tool()
async def early_get_activities() -> list[dict]:
    """Get all active activities (name, id, color).

    Use this to find the activity ID for time tracking (e.g. 'Development').
    """
    client = await _client()
    resp = await client.get("/activities")
    resp.raise_for_status()
    activities = resp.json().get("activities", [])
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "color": a["color"],
        }
        for a in activities
    ]


@mcp.tool()
async def early_get_current_tracking() -> dict:
    """Get the currently running time tracking entry.

    Returns the active tracking info including activity, start time, and note/tags.
    Returns empty currentTracking if nothing is being tracked.
    """
    client = await _client()
    resp = await client.get("/tracking")
    resp.raise_for_status()
    data = resp.json()
    tracking = data.get("currentTracking")
    if not tracking:
        return {"tracking": None, "message": "Nothing currently being tracked"}
    return {
        "activity_id": tracking.get("activityId"),
        "activity_name": tracking.get("activity", {}).get("name", ""),
        "started_at": tracking.get("startedAt", ""),
        "note": _format_note(tracking.get("note")),
        "note_raw": tracking.get("note"),
    }


@mcp.tool()
async def early_start_tracking(activity_id: str, started_at: str = "") -> dict:
    """Start tracking time on an activity.

    Args:
        activity_id: The activity ID to track (use early_get_activities to find IDs).
        started_at: Optional start time (ISO 8601, e.g. '2025-01-15T09:00:00.000'). Defaults to now.
    """
    client = await _client()
    ts = _to_api_ts(started_at) if started_at else _now_api_ts()
    resp = await client.post(
        f"/tracking/{activity_id}/start",
        json={"startedAt": ts},
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def early_stop_tracking(stopped_at: str = "") -> dict:
    """Stop the currently running time tracker.

    Args:
        stopped_at: Optional stop time (ISO 8601). Defaults to now.
    """
    client = await _client()
    ts = _to_api_ts(stopped_at) if stopped_at else _now_api_ts()
    resp = await client.post(
        "/tracking/stop",
        json={"stoppedAt": ts},
    )
    resp.raise_for_status()
    return _format_entry(resp.json().get("createdTimeEntry", resp.json()))


@mcp.tool()
async def early_edit_current_tracking(
    note: str = "",
    activity_id: str = "",
    started_at: str = "",
) -> dict:
    """Edit the currently running time tracking entry.

    Use this to update the note/tags on the running entry. Tags in the note
    use the format <{{|t|TAG_ID|}}> — use early_get_tags to find tag IDs.

    Args:
        note: New note text. Include tags as <{{|t|TAG_ID|}}>. Pass raw note format.
        activity_id: Change the activity being tracked.
        started_at: Change the start time.
    """
    client = await _client()
    body: dict = {}
    if note:
        body["note"] = {"text": note}
    if activity_id:
        body["activityId"] = activity_id
    if started_at:
        body["startedAt"] = _to_api_ts(started_at)
    resp = await client.patch("/tracking", json=body)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def early_get_time_entries(from_date: str, to_date: str) -> list[dict]:
    """Get time entries within a date range.

    Args:
        from_date: Start date (YYYY-MM-DD). Entries stopped after this time.
        to_date: End date (YYYY-MM-DD). Entries started before this time.

    Returns a list of time entries with activity, duration, and notes/tags.
    Use this to find entries that are missing ClickUp task tags.
    """
    client = await _client()
    stopped_after = _to_api_ts(from_date)
    started_before = _end_of_day_api_ts(to_date)
    resp = await client.get(f"/time-entries/{stopped_after}/{started_before}")
    resp.raise_for_status()
    entries = resp.json().get("timeEntries", [])
    return [_format_entry(e) for e in entries]


@mcp.tool()
async def early_create_time_entry(
    activity_id: str,
    started_at: str,
    stopped_at: str,
    note: str = "",
) -> dict:
    """Create a new time entry.

    Args:
        activity_id: The activity ID.
        started_at: Start time (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD).
        stopped_at: Stop time (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD).
        note: Optional note text. Include tags as <{{|t|TAG_ID|}}>.
    """
    client = await _client()
    body: dict = {
        "activityId": activity_id,
        "startedAt": _to_api_ts(started_at),
        "stoppedAt": _to_api_ts(stopped_at),
    }
    if note:
        body["note"] = {"text": note}
    resp = await client.post("/time-entries", json=body)
    resp.raise_for_status()
    return _format_entry(resp.json())


@mcp.tool()
async def early_update_time_entry(
    time_entry_id: str,
    activity_id: str = "",
    started_at: str = "",
    stopped_at: str = "",
    note: str = "",
) -> dict:
    """Update an existing time entry.

    Use this to add missing tags to past entries. When updating the note,
    you must provide the complete note text including any existing content.
    Tags in notes use the format <{{|t|TAG_ID|}}>.

    Args:
        time_entry_id: The time entry ID to update.
        activity_id: New activity ID (optional).
        started_at: New start time (optional).
        stopped_at: New stop time (optional).
        note: New note text. Include tags as <{{|t|TAG_ID|}}>. Replaces existing note.
    """
    client = await _client()
    body: dict = {}
    if activity_id:
        body["activityId"] = activity_id
    if started_at:
        body["startedAt"] = _to_api_ts(started_at)
    if stopped_at:
        body["stoppedAt"] = _to_api_ts(stopped_at)
    if note:
        body["note"] = {"text": note}
    resp = await client.patch(f"/time-entries/{time_entry_id}", json=body)
    resp.raise_for_status()
    return _format_entry(resp.json())


@mcp.tool()
async def early_delete_time_entry(time_entry_id: str) -> dict:
    """Delete a time entry.

    Args:
        time_entry_id: The time entry ID to delete.
    """
    client = await _client()
    resp = await client.delete(f"/time-entries/{time_entry_id}")
    resp.raise_for_status()
    return {"deleted": True, "time_entry_id": time_entry_id}


@mcp.tool()
async def early_get_tags() -> list[dict]:
    """Get all available tags and mentions.

    Returns all tags — use this to check if a ClickUp task tag (e.g. WEB-3343)
    exists before referencing it in a note. Tag IDs are needed for the
    <{{|t|TAG_ID|}}> note format.
    """
    client = await _client()
    resp = await client.get("/tags-and-mentions")
    resp.raise_for_status()
    data = resp.json()
    tags = data.get("tags", [])
    mentions = data.get("mentions", [])
    return {
        "tags": [
            {"id": t["id"], "key": t["key"], "label": t["label"]}
            for t in tags
        ],
        "mentions": [
            {"id": m["id"], "key": m["key"], "label": m["label"]}
            for m in mentions
        ],
    }


@mcp.tool()
async def early_create_tag(label: str, key: str) -> dict:
    """Create a new tag.

    Use this to create a tag for a ClickUp task ID that doesn't exist yet.
    After creating, use the returned tag ID in notes as <{{|t|TAG_ID|}}>.

    Args:
        label: Display label for the tag (e.g. 'WEB-3343').
        key: Unique key for the tag (e.g. 'WEB-3343'). Used with # in notes.
    """
    client = await _client()
    resp = await client.post(
        "/tags",
        json={"key": key, "label": label, "scope": "timeular", "space_id": 0},
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
