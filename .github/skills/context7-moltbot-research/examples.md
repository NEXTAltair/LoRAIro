# Context7 + Moltbot LTM - 使用例

## Example 1: ライブラリドキュメント取得

```python
# Context7直接でPySide6のSignal/Slotドキュメントを取得
# 1. ライブラリID解決
mcp__context7__resolve_library_id(libraryName="pyside6")

# 2. ドキュメント取得
mcp__context7__get_library_docs(
    context7CompatibleLibraryID="/pyside/pyside6",
    topic="Signal Slot QThread"
)
```

## Example 2: 過去の設計知識検索

```bash
# Moltbot LTM検索でQt Workerパターンの過去実装を確認
python3 .github/skills/lorairo-mem/scripts/ltm_search.py "Qt Worker pattern QThreadPool"
```

## Example 3: 設計決定の長期記憶化

```bash
# 重要な設計決定をMoltbot LTMに保存
TOKEN=$(jq -r '.hooks.token' ~/.clawdbot/clawdbot.json)
curl -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "decision",
    "importance": "High",
    "title": "Qt Signal/Slot パターン選定",
    "content": "## 決定内容\nDirect Widget Communicationパターン採用\n\n## 理由\n- シンプルで保守しやすい\n- デバッグが容易\n- LoRAIro規模に適合"
  }'
```

## Example 4: 技術研究ワークフロー

```python
# Step 1: LTM検索で過去の類似調査を確認
# python3 ltm_search.py "database migration SQLAlchemy"

# Step 2: Context7でライブラリドキュメント取得
mcp__context7__resolve_library_id(libraryName="sqlalchemy")
mcp__context7__get_library_docs(
    context7CompatibleLibraryID="/sqlalchemy/sqlalchemy",
    topic="Alembic migration async"
)

# Step 3: 調査結果をLTMに保存
# curl POST /hooks/lorairo-memory with type="decision"
```

## Example 5: Serena + Moltbot LTM併用パターン

```python
# 1. [Serena] 現在のコード構造を確認
mcp__serena__get_symbols_overview(relative_path="src/lorairo/gui/workers/")

# 2. [Moltbot LTM] 過去事例検索
# python3 ltm_search.py "worker pattern implementation"

# 3. [Context7] ライブラリ調査
mcp__context7__resolve_library_id(libraryName="pyside6")
mcp__context7__get_library_docs(
    context7CompatibleLibraryID="/pyside/pyside6",
    topic="QRunnable QThreadPool"
)

# 4. [Serena] 関連シンボル検索
mcp__serena__find_symbol(name_path_pattern="WorkerManager", include_body=True)

# 5. [Moltbot LTM] 長期記憶化
# curl POST /hooks/lorairo-memory with type="decision"
```

## ベストプラクティス

### 効率的な使用パターン
1. **LTM検索優先**: 新規調査前に必ず過去知識を確認
2. **Context7活用**: ライブラリドキュメントはContext7直接
3. **必ず記録**: 重要な判断は Moltbot LTM で永続化

### タイミング特性
| 操作 | ツール | 応答時間 |
|------|--------|----------|
| LTM検索 | ltm_search.py | 2-5s |
| LTM保存 | POST /hooks/lorairo-memory | 1-3s |
| ライブラリドキュメント | Context7 | 3-10s |
| ローカル分析 | Serena | 0.3-0.5s |
