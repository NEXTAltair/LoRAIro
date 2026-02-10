# OpenClaw LTM + Web Research - 使用例

## Example 1: ライブラリドキュメント取得

```json
{"search_query":[{"q":"PySide6 Signal Slot QThread official docs"}]}
```

## Example 2: 過去の設計知識検索

```bash
# OpenClaw LTM検索でQt Workerパターンの過去実装を確認
python3 .github/skills/lorairo-mem/scripts/ltm_search.py "Qt Worker pattern QThreadPool"
```

## Example 3: 設計決定の長期記憶化

```bash
# 重要な設計決定をOpenClaw LTMに保存
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

# Step 2: web.runで公式ドキュメント取得
# {"search_query":[{"q":"SQLAlchemy Alembic async migration official docs"}]}

# Step 3: 調査結果をLTMに保存
# curl POST /hooks/lorairo-memory with type="decision"
```

## Example 5: Serena + OpenClaw LTM併用パターン

```python
# 1. [Serena] 現在のコード構造を確認
mcp__serena__get_symbols_overview(relative_path="src/lorairo/gui/workers/")

# 2. [OpenClaw LTM] 過去事例検索
# python3 ltm_search.py "worker pattern implementation"

# 3. [Web] ライブラリ調査
# {"search_query":[{"q":"PySide6 QRunnable QThreadPool official docs"}]}

# 4. [Serena] 関連シンボル検索
mcp__serena__find_symbol(name_path_pattern="WorkerManager", include_body=True)

# 5. [OpenClaw LTM] 長期記憶化
# curl POST /hooks/lorairo-memory with type="decision"
```

## ベストプラクティス

### 効率的な使用パターン
1. **LTM検索優先**: 新規調査前に必ず過去知識を確認
2. **Web検索 + OpenClaw補強**: ライブラリドキュメントは web.run で確認し、保存時に OpenClaw が補強
3. **必ず記録**: 重要な判断は OpenClaw LTM で永続化

### タイミング特性
| 操作 | ツール | 応答時間 |
|------|--------|----------|
| LTM検索 | ltm_search.py | 2-5s |
| LTM保存 | POST /hooks/lorairo-memory | 1-3s |
| ライブラリドキュメント | web.run | 2-5s |
| ローカル分析 | Serena | 0.3-0.5s |
