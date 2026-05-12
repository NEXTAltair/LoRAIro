#!/usr/bin/env python3
"""Return latest N memories (by Created desc) via Open Response API."""
from ltm_common import DEFAULT_PAGE_SIZE, query_via_responses, read_stdin_json, out_text


def main():
    inp = read_stdin_json()
    limit = int(inp.get("limit") or DEFAULT_PAGE_SIZE)
    limit = max(1, min(limit, 50))

    prompt = (
        f"OP: lorairo-memory-query\n"
        f"LIMIT: {limit}\n"
        f"SORT: Created descending\n"
        f"OUTPUT: json_only\n"
        f"FIELDS: title,summary,url,hash,created,type,status,tags,environment"
    )
    result = query_via_responses(prompt)
    out_text(result)


if __name__ == "__main__":
    main()
