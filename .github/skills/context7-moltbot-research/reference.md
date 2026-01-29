# Context7 + Moltbot LTM - APIリファレンス

## 利用可能なツール

### Context7 (ライブラリドキュメント)

#### mcp__context7__resolve_library_id
ライブラリ名からContext7対応IDを解決

```python
mcp__context7__resolve_library_id(libraryName="pyside6")
# Returns: /pyside/pyside6
```

**応答時間**: 1-3秒

#### mcp__context7__get_library_docs
ライブラリドキュメントを取得

```python
mcp__context7__get_library_docs(
    context7CompatibleLibraryID="/pyside/pyside6",
    topic="Signal Slot threading"
)
```

**応答時間**: 3-10秒

### Moltbot LTM (長期記憶)

#### LTM検索

```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py "検索クエリ"
```

**応答時間**: 2-5秒

#### LTM保存

```bash
TOKEN=$(jq -r '.hooks.token' ~/.clawdbot/clawdbot.json)
curl -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "decision",
    "importance": "High",
    "title": "タイトル",
    "content": "内容（Markdown形式）"
  }'
```

**応答時間**: 1-3秒

**type値**: decision, howto, bug, idea, note, reference
**importance値**: High, Medium, Low (大文字小文字区別)

### Serena (ローカル操作)

- `mcp__serena__get_symbols_overview` - シンボル概要取得 (0.3-0.5s)
- `mcp__serena__find_symbol` - シンボル検索 (0.3-0.5s)
- `mcp__serena__search_for_pattern` - パターン検索 (0.5-1s)
- `mcp__serena__read_memory` / `write_memory` - 短期メモリ操作 (0.2-0.3s)

## パフォーマンス特性

| 操作 | ツール | 応答時間 |
|------|--------|----------|
| ローカル分析 | Serena | 0.3-0.5s |
| LTM検索 | ltm_search.py | 2-5s |
| LTM保存 | POST /hooks/lorairo-memory | 1-3s |
| ライブラリドキュメント | Context7 | 3-10s |
| Web検索 | WebSearch | 2-5s |

## 使い分け

- **Serena**: 即座の構造理解とコード操作（高速）
- **Moltbot LTM**: 設計知識の永続化と再利用（長期記憶）
- **Context7**: ライブラリドキュメント取得（外部・リアルタイム）
