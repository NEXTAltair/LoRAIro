#!/usr/bin/env python3
"""Search/query the LoRAIro LTM data source.

This is a deterministic Notion query helper; it does NOT use the Notion /search endpoint.

Input JSON (stdin):
{
  "limit": 10,
  "sort": "Created" | "Updated",
  "direction": "descending" | "ascending",
  "filters": {
    "type": ["bug","howto"],
    "status": ["inbox"],
    "importance": ["High"],
    "source": ["WSL"],
    "environment": ["WSL","CI"],
    "tags": ["build","ci"],
    "project": ["lorairo"]
  }
}

Notes:
- For multi_select filters (tags/environment) Notion supports "contains"; we OR within the list.
- If you want AND semantics (must contain all tags), call this multiple times or extend.
"""

from ltm_common import DATA_SOURCE_ID, DEFAULT_PAGE_SIZE, http_json, read_stdin_json, out


def _or(filters):
    # drop empty
    flt = [f for f in filters if f]
    if not flt:
        return None
    if len(flt) == 1:
        return flt[0]
    return {"or": flt}


def _select_any(prop, values):
    vals = [v for v in (values or []) if isinstance(v, str) and v.strip()]
    return _or([{"property": prop, "select": {"equals": v}} for v in vals])


def _multi_contains_any(prop, values):
    vals = [v for v in (values or []) if isinstance(v, str) and v.strip()]
    return _or([{"property": prop, "multi_select": {"contains": v}} for v in vals])


def main():
    inp = read_stdin_json()
    limit = int(inp.get("limit") or DEFAULT_PAGE_SIZE)
    limit = max(1, min(limit, 50))

    sort_prop = inp.get("sort") or "Created"
    if sort_prop not in ("Created", "Updated"):
        sort_prop = "Created"

    direction = inp.get("direction") or "descending"
    if direction not in ("descending", "ascending"):
        direction = "descending"

    f = (inp.get("filters") or {})

    parts = [
        _select_any("Type", f.get("type")),
        _select_any("Status", f.get("status")),
        _select_any("Importance", f.get("importance")),
        _select_any("Source", f.get("source")),
        _select_any("Project", f.get("project")),
        _multi_contains_any("Environment", f.get("environment")),
        _multi_contains_any("Tags", f.get("tags")),
    ]

    and_parts = [p for p in parts if p]
    notion_filter = None
    if and_parts:
        notion_filter = {"and": and_parts} if len(and_parts) > 1 else and_parts[0]

    payload = {
        "page_size": limit,
        "sorts": [{"property": sort_prop, "direction": direction}],
    }
    if notion_filter:
        payload["filter"] = notion_filter

    res = http_json("POST", f"/data_sources/{DATA_SOURCE_ID}/query", payload)
    out({"items": res.get("results", []), "next_cursor": res.get("next_cursor"), "has_more": res.get("has_more")})


if __name__ == "__main__":
    main()
