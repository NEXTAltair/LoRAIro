#!/usr/bin/env python3
"""Search/query the LoRAIro LTM via Open Response API.

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
  },
  "query": "free text search"
}

Notes:
- Uses Open Response API (/v1/responses) to query via LLM.
- filters and query are combined into a structured prompt.
"""

from ltm_common import DATA_SOURCE_ID, DEFAULT_PAGE_SIZE, query_via_responses, read_stdin_json, out_text


def _build_prompt(inp: dict) -> str:
    """入力パラメータから検索プロンプトを構築する。"""
    limit = int(inp.get("limit") or DEFAULT_PAGE_SIZE)
    limit = max(1, min(limit, 50))

    sort_prop = inp.get("sort") or "Created"
    if sort_prop not in ("Created", "Updated"):
        sort_prop = "Created"

    direction = inp.get("direction") or "descending"
    if direction not in ("descending", "ascending"):
        direction = "descending"

    query = (inp.get("query") or "").strip()
    filters = inp.get("filters") or {}

    # プロンプト構築
    parts = [
        f"OP: lorairo-memory-query",
        f"LIMIT: {limit}",
        f"SORT: {sort_prop} {direction}",
        f"OUTPUT: json_only",
        f"FIELDS: title,summary,url,hash,created,type,status,tags,environment",
    ]

    if query:
        parts.insert(1, f"QUERY: {query}")

    # フィルタ条件を追加
    filter_lines = []
    for key, values in filters.items():
        if values and isinstance(values, list):
            filter_lines.append(f"  {key}: {', '.join(str(v) for v in values)}")
    if filter_lines:
        parts.append("FILTERS:")
        parts.extend(filter_lines)

    return "\n".join(parts)


def main():
    inp = read_stdin_json()
    prompt = _build_prompt(inp)
    result = query_via_responses(prompt)
    out_text(result)


if __name__ == "__main__":
    main()
