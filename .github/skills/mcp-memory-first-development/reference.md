# Memory-First Development - リファレンス

## 2重メモリ戦略の全体像

```
開発フロー:

1. 実装前 ─┬─ [Serena] current-project-status 確認
          └─ [OpenClaw] 過去の類似実装検索（ltm_search.py）

2. 実装中 ─┬─ [Serena] active-development-tasks 継続更新
          └─ [Serena] 一時的判断・デバッグ情報記録

3. 完了後 ─┬─ [OpenClaw] 実装知識の長期記憶化（POST /hooks/lorairo-memory）
          └─ [Serena] プロジェクト状況更新
```

## Serena Memory（短期・プロジェクト固有）

### 標準メモリ名

#### current-project-status
**用途**: プロジェクト全体の状況記録

**構造**:
```markdown
# LoRAIro Project Status - YYYY-MM-DD

## 最新の開発状況
- ブランチ: [現在のブランチ名]
- 最新作業: [最新の実装内容]

## 完了した作業
✅ [完了項目1]
✅ [完了項目2]

## 次の優先事項
1. [優先度1]
2. [優先度2]

## 技術課題
- [課題1]
- [課題2]
```

**更新頻度**: 毎日の開発終了時、大きな実装完了時

---

#### active-development-tasks
**用途**: 現在の開発タスクと進捗

**構造**:
```markdown
# 現在の開発タスク - YYYY-MM-DD

## 進行中タスク
- [現在作業中の内容]

## 完了した作業
✅ [完了項目]

## 次のステップ
1. [次に実装すること]
2. [その後の作業]

## 技術的判断
- [判断内容]
  理由: [なぜその判断をしたか]

## 課題・ブロッカー
- [現在の問題点]
- [解決策候補]
```

**更新頻度**: 1-2時間ごと、重要な判断後、作業終了時

---

#### {feature}_wip_{YYYY_MM_DD}
**用途**: 特定機能の作業中メモ

**例**: `filtering_wip_2025_10_20`

**構造**: active-development-tasksと同様、特定機能に特化

**削除タイミング**: 機能完了後（またはarchivedに移行）

---

#### debug_{issue}_{YYYY_MM_DD}
**用途**: デバッグ情報と解決策

**構造**:
```markdown
# [問題の簡潔な説明] - デバッグ記録

## 症状
- [観察された問題]

## 調査結果
1. [調査項目1]
2. [調査項目2]

## 原因
- [問題の根本原因]

## 解決策
[実装した解決策]

## 教訓
- [将来のための知見]
```

**削除タイミング**: 解決後、OpenClaw LTMに記録してから削除

---

### Serena Memory操作

#### list_memories
```python
mcp__serena__list_memories()
→ ["current-project-status", "active-development-tasks", ...]
```

#### read_memory
```python
mcp__serena__read_memory(memory_file_name="current-project-status")
→ プロジェクト状況の詳細
```

#### write_memory
```python
mcp__serena__write_memory(
  memory_name="active-development-tasks",
  content="[Markdown形式の内容]"
)
→ メモリ作成または更新
```

---

## OpenClaw LTM（長期・Notion DB）

### 記憶形式

#### タイトル形式
```
LoRAIro [機能名] [内容] [種別]

例:
- "LoRAIro Direct Widget Communication パターン採用"
- "LoRAIro Repository Pattern データベース設計"
- "LoRAIro 画像フィルタリング機能実装"
```

#### 内容構造（bodyフィールド）
```markdown
# [実装概要]

## 背景・動機
[なぜこの実装が必要だったか]

## 設計アプローチ
[どのような設計判断をしたか]

## 技術選定
[使用した技術とその選定理由]

## 実装詳細
[重要な実装パターン、コード例]

## 結果・効果
[実装による改善、パフォーマンス、コード削減]

## 課題と解決策
[実装中の課題とその解決方法]

## 教訓・ベストプラクティス
[将来の実装で活用できる知見]

## アンチパターン
[避けるべき実装方法、失敗から学んだこと]
```

---

### OpenClaw LTM操作

#### 書き込み（POST /hooks/lorairo-memory）
```bash
HOOK_TOKEN="<hooks.token>"

curl -sS -X POST http://host.docker.internal:18789/hooks/lorairo-memory \
  -H "Authorization: Bearer $HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "LoRAIro [機能名] [内容]",
    "summary": "[1-2行の要約]",
    "body": "[Markdown形式の詳細内容]",
    "type": "decision",
    "importance": "High",
    "tags": ["技術分野", "パターン名"],
    "source": "Container"
  }'
```

**type選択ガイド**:
- `decision` - アーキテクチャ決定、技術選定理由
- `howto` - 実装パターン、ベストプラクティス
- `note` - 実装記録、進捗マイルストーン
- `reference` - 技術仕様、API仕様
- `bug` - バグ解決記録、デバッグ教訓

**推奨タグ**:
- `architecture`, `design-pattern`, `performance`
- `database`, `gui`, `testing`, `ai-integration`
- `refactoring`, `optimization`, `best-practice`

#### 検索（ltm_search.py）
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_search.py <<'JSON'
{
  "limit": 10,
  "filters": {
    "type": ["decision", "howto"],
    "tags": ["repository-pattern", "sqlalchemy"]
  }
}
JSON
```

**効果的な検索フィルタ**:
- タグでパターン検索: `"tags": ["repository-pattern"]`
- タイプで絞り込み: `"type": ["decision"]`
- 重要度で絞り込み: `"importance": ["High"]`

#### 最新取得（ltm_latest.py）
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_latest.py <<'JSON'
{"limit": 5}
JSON
```

#### ハッシュで取得（ltm_get.py）
```bash
python3 .github/skills/lorairo-mem/scripts/ltm_get.py <<'JSON'
{"hash": "<sha256>"}
JSON
```

---

## Memory-First開発ワークフロー

### ワークフロー1: 新機能実装

```
Phase 1: 実装前（5-10分）
├─ [S] list_memories() → 利用可能なメモリ確認
├─ [S] read_memory("current-project-status") → 現在状況確認
└─ [M] ltm_search.py → 過去事例検索

Phase 2: 実装中（1-2時間ごと）
└─ [S] write_memory("active-development-tasks") → 進捗記録

Phase 3: 完了後（10-15分）
├─ [M] POST /hooks/lorairo-memory → 知識永続化
└─ [S] write_memory("current-project-status") → 状況更新

[S] = Serena, [M] = OpenClaw
```

### ワークフロー2: リファクタリング

```
Phase 1: リファクタリング前
├─ [M] ltm_search.py → 過去のリファクタリング事例
└─ [S] write_memory("refactoring_plan") → 計画記録

Phase 2: リファクタリング中
└─ [S] write_memory("active-development-tasks") → 段階的進捗

Phase 3: リファクタリング完了
├─ [M] POST /hooks/lorairo-memory → アプローチ・効果記録
└─ [S] write_memory("current-project-status") → 状況更新
```

### ワークフロー3: デバッグ

```
調査中:
└─ [S] write_memory("debug_issue_YYYYMMDD") → 調査結果記録

解決後:
├─ [M] POST /hooks/lorairo-memory → 解決策・教訓記録
└─ [S] delete debug memory（Serenaから削除、OpenClaw LTMに移行済み）
```

---

## パフォーマンス特性

### 実行時間
- **Serena read/write**: 0.3-0.5秒（高速）
- **OpenClaw write**: 1-3秒（HTTP webhook）
- **OpenClaw search**: 2-5秒（Notion DB query）

### 推奨使用パターン
```
実装前: OpenClaw検索（過去知見の活用）
実装中: Serena優先（高速な記録）
完了後: OpenClaw必須（知識永続化）
```

---

## LoRAIro固有ガイドライン

### 記録すべき設計判断
- **アーキテクチャパターン**: Repository, Service, Direct Widget Communication
- **技術選定**: SQLAlchemy, PySide6, pytest 選択理由
- **パフォーマンス改善**: キャッシュ統一、非同期処理
- **リファクタリング**: 大規模変更の意図と効果

### OpenClaw検索キーワード例（タグ）
- `widget`, `signal-slot`, `direct-communication`
- `repository-pattern`, `sqlalchemy`, `transaction`
- `pytest`, `fixture`, `coverage`
- `pyside6`, `qthread`, `worker`, `async`

### Memory命名例
#### Serena
- `current-project-status`
- `active-development-tasks`
- `filtering_wip_2025_10_20`
- `debug_thumbnail_click_2025_10_20`

#### OpenClaw LTM（title）
- "LoRAIro Direct Widget Communication パターン採用"
- "LoRAIro Repository Pattern データベース設計"
- "LoRAIro DatasetStateManager リファクタリング"

---

## ベストプラクティス

### 実装前
1. **必ずMemory確認**: 過去の知見を活用
2. **OpenClaw検索**: 類似実装の発見
3. **計画記録**: Serenaに実装計画を記録

### 実装中
1. **定期的記録**: 1-2時間ごとにSerena更新
2. **判断記録**: 重要な技術判断は即座に記録
3. **デバッグメモ**: 複雑な問題は専用メモリに記録

### 完了後
1. **必ずOpenClaw LTM記録**: 実装知識の永続化
2. **Serena更新**: プロジェクト状況の更新
3. **不要なメモリ削除**: 完了したwip/debugメモリ削除
