#!/usr/bin/env python3
"""Return latest N memories (by Created desc)."""
from ltm_common import DATA_SOURCE_ID, DEFAULT_PAGE_SIZE, http_json, read_stdin_json, out


def main():
    inp = read_stdin_json()
    limit = int(inp.get("limit") or DEFAULT_PAGE_SIZE)
    limit = max(1, min(limit, 50))

    res = http_json(
        "POST",
        f"/data_sources/{DATA_SOURCE_ID}/query",
        {
            "page_size": limit,
            "sorts": [{"property": "Created", "direction": "descending"}],
        },
    )
    out({"items": res.get("results", []), "next_cursor": res.get("next_cursor"), "has_more": res.get("has_more")})


if __name__ == "__main__":
    main()
