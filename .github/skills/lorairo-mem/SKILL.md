---
name: lorairo-mem
version: "1.0.0"
description: LoRAIro long-term memory operations. Use when you need to store structured project memories via the local Moltbot webhook (/hooks/lorairo-memory), de-duplicate by hash, or search/retrieve entries from the Notion database "LoRAIro-Long-Term Memory (Shared)".
metadata:
  short-description: LoRAIro長期記憶パイプライン（Moltbot webhook → Notion DB書き込み・検索・重複排除）。
  clawdbot:
    emoji: "🧠"
---

# lorairo-mem

This skill documents the **LoRAIro long-term memory pipeline**:

- **Write**: `POST /hooks/lorairo-memory` (local gateway) → validates payload → writes to Notion DB → de-dupes by `Hash`.
- **Read**: query the Notion DB (data source) to retrieve relevant memories (see `clawd/skills/notion/SKILL.md` for request details).

## Authentication

Scripts automatically load tokens from `.github/skills/lorairo-mem/.env` on import.
Environment variables already set in the shell take precedence over `.env` values.

Setup:
1. Copy `.env.example` to `.env` in this skill directory
2. Fill in your token values
3. `.env` is gitignored — secrets will not be committed

Required:
- `HOOK_TOKEN` (used for `/hooks/lorairo-memory`)

Optional:
- `GW_TOKEN` (used for `/v1/responses` if you enable the gateway responses endpoint)
- `NOTION_API_KEY` (direct Notion fallback; optional)
- `LORAIRO_MEM_GATEWAY_URL` (override gateway base URL; optional)

The scripts use Moltbot Gateway as a proxy for Notion API access. No separate Notion API key is required.

## Fixed IDs (current)

Notion DB:
- **Data source id** (query endpoint): `2f544994-92c3-80d4-a975-000b5fcf09e9`
- **Database id** (create page): `2f544994-92c3-8040-9666-ea28223daac6`

Webhook:
- Endpoint: `http://host.docker.internal:18789/hooks/lorairo-memory`
- Auth header: `Authorization: Bearer $HOOK_TOKEN`
- `match.path` (config): `lorairo-memory`

## Payload spec (v1)

Required:
- `title` (string)
- `summary` (string)
- `body` (string)

Optional:
- `type` (string) — enum
- `status` (string) — enum
- `importance` (string) — enum
- `source` (string) — enum
- `tags` (string[]) — **free-form**, but will be **lowercased** and de-duped
- `environment` (string[]) — enum
- `author` (string)
- `link` (url string)
- `sourceMessageUrl` (url string)

Server-side rules:
- `project` is fixed to `lorairo` (Notion select)
- `Hash` is computed from normalized payload and used for de-duplication
- `created` / `updated` are auto-filled when omitted

### Enums (must match Notion select options)

- `type`: `decision | howto | bug | idea | note | reference`
- `status`: `inbox | curated | archived`
- `importance`: `High | Medium | Low`
- `source`: `Discord | WSL | Windows | Container | Other`
- `environment`:
  - `WSL | Windows | Container | CI | Mobile | Linux | macOS | Cloud`

## Write a memory (curl)

```bash
# Ensure HOOK_TOKEN is set in the environment (do not store secrets in this repo)

curl -sS -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Build failure: peer dependency conflict",
    "summary":"npm install fails due to peer dependency mismatch.",
    "body":"- Symptom: ...\n- Fix: ...",
    "type":"bug",
    "status":"inbox",
    "importance":"High",
    "source":"Container",
    "environment":["Container","CI"],
    "tags":["Deps","NPM","Build"],
    "link":"https://..."
  }'
```

## Write a memory (script)

```bash
python3 {baseDir}/scripts/ltm_write.py <<'JSON'
{
  "title":"Build failure: peer dependency conflict",
  "summary":"npm install fails due to peer dependency mismatch.",
  "body":"- Symptom: ...\n- Fix: ...",
  "type":"bug",
  "status":"inbox",
  "importance":"High",
  "source":"Container",
  "environment":["Container","CI"],
  "tags":["Deps","NPM","Build"],
  "link":"https://..."
}
JSON
```

Notes:
- If you get `401 Unauthorized`, your hook token header is wrong.
- If you get `404 Not Found`, mapping likely mismatched; in current config `match.path` is `lorairo-memory` while the endpoint is `/hooks/lorairo-memory`.

## Confirm de-dupe behavior

Send the same payload twice; the second should be skipped.

The transform logs messages like:
- `[hooks:lorairo-memory] create ...`
- `[hooks:lorairo-memory] dedupe skip ...`

## Read/search memories

For raw Notion API request formats, see the Notion skill:
- `{baseDir}/../notion/SKILL.md`

For deterministic querying, use the bundled scripts in this skill.

### Retrieval behavior (agent)

- Prefer items that match the **requester's environment/source** when available.
- Return a **short summary of the most relevant items**; strict reproducibility is not required.

### Query schema (v1, recommended)

```json
{
  "query": "free text",
  "limit": 10,
  "sort": "Created|Updated",
  "direction": "descending|ascending",
  "filters": {
    "type": ["decision","howto","bug","idea","note","reference"],
    "status": ["inbox","curated","archived"],
    "importance": ["High","Medium","Low"],
    "source": ["Discord","WSL","Windows","Container","Other"],
    "environment": ["WSL","Windows","Container","CI","Mobile","Linux","macOS","Cloud"],
    "tags": ["build","ci","deps"],
    "project": ["lorairo","general","other"]
  }
}
```

Notes:
- `filters` are AND across fields, OR within each list (see `scripts/ltm_search.py`).
- `query` can be omitted; use filters + sort for latest items.

### Latest N

```bash
python3 {baseDir}/scripts/ltm_latest.py <<'JSON'
{"limit": 5}
JSON
```

### Filtered query

```bash
python3 {baseDir}/scripts/ltm_search.py <<'JSON'
{
  "limit": 10,
  "filters": {
    "type": ["bug"],
    "status": ["inbox"],
    "environment": ["WSL"],
    "tags": ["build", "ci"],
    "project": ["lorairo"]
  }
}
JSON
```

### Get by hash

```bash
python3 {baseDir}/scripts/ltm_get.py <<'JSON'
{"hash": "<sha256>"}
JSON
```

## Recommended workflow (agent)

0) **Preflight**: verify which gateway endpoint is reachable from the current agent environment.
   - Try `http://localhost:18789/health` first (local host).
   - If that fails, try `http://host.docker.internal:18789/health` (container/VM).
   - Set `LORAIRO_MEM_GATEWAY_URL` to the reachable base URL before writing.
1) When you need to remember something, **write** it via `/hooks/lorairo-memory`.
2) When asked a question, use `ltm_search.py` / `ltm_latest.py` to fetch **5–15 candidates**.
3) Only inspect the **Body** of the top candidates.
4) Summarize and cite the Notion URLs.

## Free-text query (sync via gateway)

If you want **free-text search with a synchronous response**, use the gateway `POST /v1/responses` endpoint instead of `/hooks`.

0) Prerequisite: enable responses endpoint

Enable the gateway responses endpoint in your gateway config (outside of this skill).

1) Call (sync response)

Auth uses the gateway token (`GW_TOKEN` from the environment):

```bash
curl -sS http://host.docker.internal:18789/v1/responses \
  -H "Authorization: Bearer $GW_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai-codex/gpt-5.2",
    "input": "LoRAIro LTMを自由文で検索。query=\\"docker compose 遅い\\"。関連上位5件をJSONで返して。"
  }'
```

2) Making `query` actually effective (recommended)

Notion data source queries are **filter-oriented**, so full-text search is weak.
Use a two-stage approach:

- Stage 1: `POST /v1/search` with `query` to collect candidate pages
- Stage 2: cross-check candidates against the LoRAIro data source (Hash/Tags/Type), then return a cleaned list

3) Prompt template (for stability)

```
OP: lorairo-memory-query
QUERY: docker compose 遅い
LIMIT: 5
OUTPUT: json_only
FIELDS: title,summary,url,hash,created,type,status,tags,environment
```
