#!/usr/bin/env python3
"""Get a single memory by hash (preferred) or by page_id via Open Response API."""
from ltm_common import query_via_responses, read_stdin_json, out_text


def main():
    inp = read_stdin_json()
    h = (inp.get("hash") or "").strip()
    page_id = (inp.get("page_id") or "").strip()

    if h:
        prompt = (
            f"OP: lorairo-memory-get\n"
            f"HASH: {h}\n"
            f"OUTPUT: json_only\n"
            f"FIELDS: title,summary,body,url,hash,created,type,status,tags,environment"
        )
        result = query_via_responses(prompt)
        out_text(result)
        return

    if page_id:
        prompt = (
            f"OP: lorairo-memory-get\n"
            f"PAGE_ID: {page_id}\n"
            f"OUTPUT: json_only\n"
            f"FIELDS: title,summary,body,url,hash,created,type,status,tags,environment"
        )
        result = query_via_responses(prompt)
        out_text(result)
        return

    raise SystemExit('Provide either {"hash": ...} or {"page_id": ...} on stdin')


if __name__ == "__main__":
    main()
