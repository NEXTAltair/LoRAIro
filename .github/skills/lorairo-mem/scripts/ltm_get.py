#!/usr/bin/env python3
"""Get a single memory by hash (preferred) or by page_id."""
from ltm_common import DATA_SOURCE_ID, http_json, read_stdin_json, out


def main():
    inp = read_stdin_json()
    h = (inp.get("hash") or "").strip()
    page_id = (inp.get("page_id") or "").strip()

    if h:
        res = http_json(
            "POST",
            f"/data_sources/{DATA_SOURCE_ID}/query",
            {
                "page_size": 1,
                "filter": {"property": "Hash", "rich_text": {"equals": h}},
            },
        )
        items = res.get("results", [])
        out({"item": items[0] if items else None})
        return

    if page_id:
        page = http_json("GET", f"/pages/{page_id}")
        blocks = http_json("GET", f"/blocks/{page_id}/children?page_size=50")
        out({"page": page, "blocks": blocks})
        return

    raise SystemExit("Provide either {\"hash\": ...} or {\"page_id\": ...} on stdin")


if __name__ == "__main__":
    main()
