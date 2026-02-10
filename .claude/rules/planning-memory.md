# Planning Memory Rules

計画策定時のOpenClaw LTM（長期記憶）活用ルール。Plan Mode・`/planning` コマンドの両方に適用。

## 必須: 計画策定前のLTM検索

Plan Mode または `/planning` コマンドで計画を策定する際、コード調査の**前に**以下を実行すること:

### 1. OpenClaw LTM検索（過去の設計知識）

```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"type": ["decision", "howto"], "tags": ["関連タグ"]}}
JSON
```

- 類似の設計パターン・過去の実装記録・技術選定の根拠を検索
- タグは実装対象に合わせて変更（例: `repository-pattern`, `widget`, `signal-slot`, `architecture`）
- 該当なしの場合はタグなしで再検索:
  ```bash
  python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
  {"limit": 5, "filters": {"type": ["decision", "howto"]}}
  JSON
  ```

### 2. Serena Memory確認（プロジェクト状況）

- `mcp__serena__list_memories()` で関連メモリを探索
- `mcp__serena__read_memory("current-project-status")` で最新状況を確認

### 3. 最新LTMエントリ確認

直近の設計判断を把握するため、最新エントリも確認する:

```bash
python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
{"limit": 5}
JSON
```

## 適用条件

- Plan Mode（ネイティブ）での計画策定時
- `/planning` コマンド実行時
- 新機能追加、アーキテクチャ変更、設計判断を伴うタスク

## スキップ可能な条件

- 単純なバグ修正（1-2ファイルの変更で設計判断不要）
- 同一セッションで既にLTM検索済みの場合
- typo修正、コメント追加など設計判断を伴わない変更

## 計画完了後のLTM保存

計画策定完了後、重要な設計判断は OpenClaw LTM に保存すること:

```bash
python3 .github/skills/lorairo-mem/scripts/ltm_write.py <<'JSON'
{
  "title": "LoRAIro [機能名] 設計判断",
  "summary": "設計アプローチの概要",
  "body": "# 設計詳細\n\n## 背景\n...\n\n## 判断\n...\n\n## 根拠\n...",
  "type": "decision",
  "importance": "High",
  "tags": ["関連タグ"],
  "source": "Container"
}
JSON
```

保存対象: アーキテクチャ決定、技術選定の根拠、パフォーマンス考慮事項、設計パターン選択
