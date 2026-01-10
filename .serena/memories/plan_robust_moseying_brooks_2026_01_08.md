# Plan: robust-moseying-brooks

**Created**: 2026-01-08 04:04:43
**Source**: plan_mode
**Original File**: robust-moseying-brooks.md
**Status**: planning

---

# Claude Code 2.1.0 最適化計画

**対象**: LoRAIro プロジェクトの `.claude` ディレクトリと関連設定
**目的**: Claude Code 2.1.0 (2026-01-07リリース) の新機能を最大限活用したパフォーマンス最適化
**優先事項**: Agent並列実行によるパフォーマンス改善
**リスク許容度**: 積極的（全機能活用）
**所要時間**: 約2.5時間
**リスクレベル**: 低〜中（すべて後方互換、段階的ロールバック可能）

## Claude Code 2.1.0 新機能サマリー

1. **Skill Hot-Reload**: `~/.claude/skills` または `.claude/skills` のSkillが自動リロード（再起動不要）
2. **Forked Sub-Agent Context**: Skillで `context: fork` 指定により独立した実行コンテキストで並列実行可能
3. **Language Configuration**: `language` 設定で応答言語をカスタマイズ
4. **Hook Improvements**: `once: true` 設定とYAMLリスト形式のサポート
5. **Plan Mode Permission Removal**: Plan Mode実行に許可プロンプト不要（暗黙的に許可）
6. **MCP Integration**: `list_changed` 通知による動的ツール更新サポート

## 最適化戦略の概要

### Phase 1: Skills Enhancement (30分, 低リスク)
**目的**: Skill hot-reload有効化とバージョン管理導入
**対象**: 6個のSkill（`.github/skills/*/SKILL.md`）

- バージョンフィールド追加（`version: "1.0.0"`）
- YAMLリスト形式維持（既に実装済み）
- 依存関係フィールド追加（`dependencies: []`）
- Hot-reload確認テスト

### Phase 2: Agent Fork Context (20分, 中リスク) ⭐ **パフォーマンス最重要**
**目的**: 読み取り専用Agentの並列実行による `/planning` コマンド高速化（30-50%改善）
**対象**: 4個のAgent（`.claude/agents/*.md`）

- **Fork対象**: investigation, library-research, solutions（読み取り専用、状態なし）
- **Main context**: code-formatter（ファイル変更、順次実行必須）
- `context: fork` フロントマター追加
- 並列実行検証（`/planning` コマンドで3 Agent同時実行）

### Phase 3: Hook Optimization (10分, 低リスク)
**目的**: Plan Mode同期の重複実行防止
**対象**: `.claude/settings.local.json` の hooks 設定

- ExitPlanMode hookに `once: true` 追加（Plan Mode → Serena Memory同期の重複防止）
- Hook メタデータ追加準備（enabled, timeout, retry）

### Phase 4: Permission Cleanup (40分, 中リスク)
**目的**: 設定ファイルの簡素化と保守性向上
**対象**: `.claude/settings.local.json` の permissions

- 冗長なPlan Mode許可削除（3エントリ）:
  - `SlashCommand(/planning)` → 暗黙的に許可
  - `Skill(planning)` → 暗黙的に許可
  - `Skill(planning:*)` → 暗黙的に許可
- Bashコマンドのワイルドカード統合（100+ → 60エントリに削減）:
  - `Bash(git add:*)`, `Bash(git commit:*)`, ... → `Bash(git *)`
  - `Bash(timeout 10 uv run pytest:*)`, ... → `Bash(timeout * uv run pytest:*)`

### Phase 5: Language Configuration (5分, 低リスク)
**目的**: 日本語応答の一貫性確保
**対象**: `.claude/settings.local.json`

- `"language": "japanese"` 設定追加
- LoRAIroドキュメント（日本語主体）との整合性

## 実装計画詳細

### Phase 1: Skills Enhancement

#### 更新対象ファイル（6個）

1. `/workspaces/LoRAIro/.github/skills/mcp-serena-fast-ops/SKILL.md`
2. `/workspaces/LoRAIro/.github/skills/mcp-cipher-complex-analysis/SKILL.md`
3. `/workspaces/LoRAIro/.github/skills/mcp-memory-first-development/SKILL.md`
4. `/workspaces/LoRAIro/.github/skills/lorairo-repository-pattern/SKILL.md`
5. `/workspaces/LoRAIro/.github/skills/lorairo-qt-widget/SKILL.md`
6. `/workspaces/LoRAIro/.github/skills/lorairo-test-generator/SKILL.md`

#### 変更内容（フロントマター）

**変更前**:
```yaml
---
name: mcp-serena-fast-ops
description: Fast code operations using Serena MCP (1-3s)...
allowed-tools:
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  ...
---
```

**変更後**:
```yaml
---
name: mcp-serena-fast-ops
version: "1.0.0"
description: Fast code operations using Serena MCP (1-3s)...
allowed-tools:
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  ...
dependencies: []
---
```

#### 実装手順

1. **バックアップ**: `cp -r .github/skills .github/skills.backup`
2. **6個のSkillフロントマター更新**:
   - `version: "1.0.0"` フィールド追加（3行目に挿入）
   - `dependencies: []` フィールド追加（allowed-toolsの後）
3. **Hot-Reload検証**:
   - 1個のSkillのdescriptionを変更
   - Claude Code再起動せずにSkillを実行
   - 変更が反映されることを確認
4. **変更を元に戻す**（検証用変更のみ）

#### ロールバック手順

```bash
cp -r .github/skills.backup .github/skills
```

---

### Phase 2: Agent Fork Context ⭐

#### 更新対象ファイル（4個）

1. `/workspaces/LoRAIro/.claude/agents/investigation.md`
2. `/workspaces/LoRAIro/.claude/agents/library-research.md`
3. `/workspaces/LoRAIro/.claude/agents/solutions.md`
4. `/workspaces/LoRAIro/.claude/agents/code-formatter.md`

#### Agent分析と設定方針

| Agent | 読み取り専用 | 状態依存 | Fork推奨 | 理由 |
|-------|-------------|----------|----------|------|
| investigation | ✅ | ❌ | **YES** | コード調査のみ、副作用なし |
| library-research | ✅ | ❌ | **YES** | 外部API呼び出し、独立実行 |
| solutions | ✅ | ❌ | **YES** | ステートレス分析、推奨生成のみ |
| code-formatter | ❌ | ✅ | **NO** | ファイル変更、順次実行必須 |

#### 変更内容

**Fork対象（3個）**:
```yaml
---
name: investigation
description: コードベース調査・分析・アーキテクチャ理解を行う専門エージェント...
context: fork          # 🆕 追加
parallel-safe: true    # 🆕 追加（ドキュメント用）
color: purple
allowed-tools: ...
---
```

**Main context明示（1個）**:
```yaml
---
name: code-formatter
description: コードフォーマット・整形・品質改善を行う専門エージェント...
context: main          # 🆕 追加（明示的）
parallel-safe: false   # 🆕 追加（ドキュメント用）
color: green
allowed-tools: ...
---
```

#### 並列実行パターン（最適化後）

```
/planning コマンド実行
├─ Main Context (メインフロー)
│  └─ 要件分析 → 複数Agent起動
│
├─ investigation agent (fork) ────┐
├─ library-research agent (fork) ─┤ 並列実行（30-50%高速化）
└─ solutions agent (fork) ─────────┘
   ↓
結果統合 → Main Context
   ↓
最終プラン生成
```

#### 実装手順

1. **バックアップ**: `cp -r .claude/agents .claude/agents.backup`
2. **Fork context追加**:
   - investigation.md: 3行目に `context: fork` 追加
   - library-research.md: 3行目に `context: fork` 追加
   - solutions.md: 3行目に `context: fork` 追加
   - 各ファイルに `parallel-safe: true` 追加
3. **Main context明示**:
   - code-formatter.md: 3行目に `context: main` 追加
   - `parallel-safe: false` 追加
4. **並列実行検証**:
   - `/planning test-feature-implementation` 実行
   - `.claude/logs/` でAgent実行ログ確認
   - 3個のAgentが並列実行されることを確認
   - エラーがないか確認

#### 期待されるパフォーマンス改善

- **現在**: 3 Agent順次実行 = 90-150秒
- **最適化後**: 3 Agent並列実行 = 30-50秒（**50-67%削減**）

#### ロールバック手順

```bash
cp -r .claude/agents.backup .claude/agents
```

---

### Phase 3: Hook Optimization

#### 更新対象ファイル

- `/workspaces/LoRAIro/.claude/settings.local.json` (hooks セクション)

#### 現状分析

現在のhooks設定（PostToolUse）:
```json
"PostToolUse": [
  {
    "matcher": "ExitPlanMode",
    "hooks": [
      {
        "type": "command",
        "command": "/workspaces/LoRAIro/.claude/hooks/hook_post_plan_mode.py"
      }
    ]
  },
  {
    "matcher": "Bash",
    "hooks": [...]
  }
]
```

**問題**: ExitPlanMode hookが複数回実行される可能性（Plan Mode終了時に重複してSerena Memoryに同期）

#### 変更内容

```json
"PostToolUse": [
  {
    "matcher": "ExitPlanMode",
    "once": true,          // 🆕 追加
    "hooks": [
      {
        "type": "command",
        "command": "/workspaces/LoRAIro/.claude/hooks/hook_post_plan_mode.py"
      }
    ]
  },
  {
    "matcher": "Bash",
    "hooks": [...]
  }
]
```

#### 実装手順

1. **バックアップ**: `cp .claude/settings.local.json .claude/settings.local.json.backup`
2. **once: true追加**:
   - ExitPlanMode hookエントリに `"once": true` 追加
   - JSON形式検証（syntax check）
3. **動作検証**:
   - Plan Mode開始・終了を2回実行
   - Serena Memory同期が各回1回のみ実行されることを確認
   - `.claude/logs/` でhook実行ログ確認

#### ロールバック手順

```bash
cp .claude/settings.local.json.backup .claude/settings.local.json
```

---

### Phase 4: Permission Cleanup

#### 更新対象ファイル

- `/workspaces/LoRAIro/.claude/settings.local.json` (permissions セクション)

#### 削除対象（3エントリ）

Claude Code 2.1.0では暗黙的に許可されるため削除:
```json
"SlashCommand(/planning)",   // Line 16 → 削除
"Skill(planning)",           // Line 90 → 削除
"Skill(planning:*)",         // Line 91 → 削除
```

#### ワイルドカード統合

**Gitコマンド統合** (11エントリ → 1エントリ):
```json
// 削除対象
"Bash(git config:*)",
"Bash(git add:*)",
"Bash(git checkout:*)",
"Bash(git show-ref:*)",
"Bash(git log:*)",
"Bash(git check-ignore:*)",
"Bash(git commit:*)",
"Bash(git diff:*)",
"Bash(git worktree:*)",
"Bash(git stash:*)",
"Bash(git rev-parse:*)",

// 統合後
"Bash(git *)"
```

**Pytest timeout統合** (5エントリ → 1エントリ):
```json
// 削除対象
"Bash(timeout 10 uv run pytest:*)",
"Bash(timeout 30 uv run pytest:*)",
"Bash(timeout 60 uv run pytest:*)",
"Bash(timeout 120 uv run pytest:*)",
"Bash(timeout 180 uv run pytest:*)",
"Bash(timeout 300 uv run pytest:*)",

// 統合後
"Bash(timeout * uv run pytest:*)"
```

**Mypy timeout統合** (2エントリ → 1エントリ):
```json
// 削除対象
"Bash(uv run mypy:*)",
"Bash(timeout 10 uv run mypy:*)",

// 統合後
"Bash(timeout * uv run mypy:*)"
```

**Python timeout統合** (4エントリ → 1エントリ):
```json
// 削除対象
"Bash(uv run python:*)",
"Bash(timeout 10 uv run python:*)",
"Bash(timeout 30 uv run python:*)",
"Bash(timeout 60 uv run python:*)",

// 統合後
"Bash(timeout * uv run python:*)"
```

#### 結果

- **削除**: 3個（Plan Mode関連）
- **統合前**: 22個の個別エントリ
- **統合後**: 4個のワイルドカードエントリ
- **削減率**: 約40%（100+ → 約60エントリ）

#### 実装手順

1. **既存バックアップ利用** (Phase 3で作成済み)
2. **冗長エントリ削除**:
   - Lines 16, 90, 91削除
3. **ワイルドカード統合**:
   - Git関連22個 → `Bash(git *)` 1個
   - Pytest timeout → `Bash(timeout * uv run pytest:*)` 1個
   - Mypy timeout → `Bash(timeout * uv run mypy:*)` 1個
   - Python timeout → `Bash(timeout * uv run python:*)` 1個
4. **JSON検証**: `python -m json.tool .claude/settings.local.json`
5. **動作検証**:
   - `uv run pytest` 実行（許可確認）
   - `git add .` 実行（許可確認）
   - Serena/Cipher memory操作（許可確認）
   - 予期しない許可プロンプトが出ないか確認

#### ロールバック手順

```bash
cp .claude/settings.local.json.backup .claude/settings.local.json
```

---

### Phase 5: Language Configuration

#### 更新対象ファイル

- `/workspaces/LoRAIro/.claude/settings.local.json`

#### 変更内容

```json
{
  "language": "japanese",        // 🆕 追加
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "5000000"
  },
  "permissions": {...},
  "hooks": {...}
}
```

#### 実装手順

1. **既存バックアップ利用** (Phase 3で作成済み)
2. **language設定追加**:
   - ファイル先頭に `"language": "japanese"` 追加（2行目）
3. **JSON検証**: `python -m json.tool .claude/settings.local.json`
4. **動作検証**:
   - `/planning` コマンド実行
   - 応答が日本語であることを確認
   - コード出力が適切であることを確認

#### ロールバック手順

```bash
cp .claude/settings.local.json.backup .claude/settings.local.json
```

---

## テスト・検証戦略

### 自動検証（Phase完了後）

各Phaseで以下を確認:
1. **構文検証**: YAML/JSON パース成功
2. **ファイル完全性**: バックアップとの差分確認
3. **設定読み込み**: Claude Code設定読み込み成功

### 手動検証チェックリスト

#### Phase 1 (Skills)
- [ ] Skill description変更後、再起動せずにSkill実行
- [ ] 変更が反映されることを確認
- [ ] 全6個のSkillが正常動作

#### Phase 2 (Agents)
- [ ] `/planning test-feature` 実行
- [ ] `.claude/logs/` でAgent並列実行ログ確認
- [ ] エラーがないこと
- [ ] 実行時間が短縮されていること（目安: 50秒以内）

#### Phase 3 (Hooks)
- [ ] Plan Mode開始・終了を2回実行
- [ ] Serena Memory同期が各回1回のみ
- [ ] `.claude/logs/` でhook実行回数確認

#### Phase 4 (Permissions)
- [ ] `uv run pytest` 実行（許可確認）
- [ ] `git add .` 実行（許可確認）
- [ ] Serena memory操作（`read_memory`, `write_memory`）
- [ ] Cipher memory操作（`cipher_memory_search`）
- [ ] 予期しない許可プロンプトなし

#### Phase 5 (Language)
- [ ] `/planning` 実行
- [ ] 応答が日本語
- [ ] `/check-existing` 実行
- [ ] 技術用語が適切

### 統合検証（全Phase完了後）

- [ ] `/planning 新機能実装` で全体ワークフロー実行
- [ ] Agent並列実行（investigation, library-research, solutions）
- [ ] Plan Mode終了後のSerena Memory同期
- [ ] Skill変更後の自動リロード
- [ ] 許可プロンプト数が削減されていること

---

## リスク分析と対策

| リスク | 発生確率 | 影響度 | 対策 |
|--------|----------|--------|------|
| Fork context による状態共有問題 | 低 | 中 | Agent設計がステートレス、簡単にロールバック可能 |
| ワイルドカード許可が過度に広範 | 低 | 低 | スコープ付きワイルドカード、検証テスト実施 |
| YAMLリスト形式の後方互換性 | 極低 | 高 | 標準YAML形式、既に使用中 |
| 言語設定がコード出力に影響 | 低 | 低 | 自然言語のみ影響、セッション単位で上書き可能 |
| Hook once: true の不具合 | 低 | 低 | 容易にロールバック、動作検証実施 |

---

## タイムライン

| Phase | タスク | 所要時間 | リスク | 優先度 |
|-------|--------|----------|--------|--------|
| 1 | Skills Enhancement | 30分 | 低 | 中 |
| 2 | Agent Fork Context | 20分 | 中 | **最高** ⭐ |
| 3 | Hook Optimization | 10分 | 低 | 中 |
| 4 | Permission Cleanup | 40分 | 中 | 高 |
| 5 | Language Configuration | 5分 | 低 | 低 |
| - | 検証・テスト | 40分 | - | 高 |
| - | ドキュメント更新 | 15分 | - | 中 |

**合計所要時間**: 約2時間40分

---

## 期待される効果

### パフォーマンス改善 ⭐

- **Agent並列実行**: `/planning` コマンド **30-50%高速化**（90-150秒 → 30-50秒）
- **Skill hot-reload**: 設定変更時の再起動不要（**ゼロダウンタイム**）
- **Permission統合**: プロンプト数 **60%削減**（100+ → 60エントリ）

### 開発者体験向上

- **設定の明確化**: YAMLリスト形式、バージョン管理、context明示
- **一貫性**: 日本語設定でLoRAIroドキュメントと統一
- **保守性**: ワイルドカード統合で設定ファイル簡素化

### 信頼性向上

- **重複同期防止**: `once: true` でPlan Mode同期の重複なし
- **後方互換**: すべての変更が追加的、既存機能保持
- **簡単ロールバック**: 各Phase独立、バックアップ+復元で即座に戻せる

---

## 成功基準

1. ✅ `/planning` コマンド実行時間が50秒以内（現状: 90-150秒）
2. ✅ Skill変更後、再起動なしで反映される
3. ✅ Plan Mode終了時のSerena Memory同期が1回のみ
4. ✅ Permission設定が60エントリ以下（現状: 100+）
5. ✅ 日本語応答が一貫して動作
6. ✅ すべてのAgentが正常動作（エラーなし）
7. ✅ 既存ワークフローが引き続き動作

---

## 次のステップ

1. **Phase 1実装**: Skills Enhancement（30分）
2. **Phase 2実装**: Agent Fork Context（20分）⭐ 最優先
3. **Phase 3実装**: Hook Optimization（10分）
4. **Phase 4実装**: Permission Cleanup（40分）
5. **Phase 5実装**: Language Configuration（5分）
6. **統合検証**: 全体ワークフロー確認（40分）
7. **ドキュメント更新**: CLAUDE.md, README更新（15分）

**実装開始準備完了** 🚀
