# Plan: moonlit-munching-yeti

**Created**: 2025-12-21 09:33:14
**Source**: plan_mode
**Original File**: moonlit-munching-yeti.md
**Status**: planning

---

# Plan Mode Memory Integration

## Problem Statement

Claude Code の Plan Mode と custom `/planning` コマンドの役割が重複し、以下の問題が発生：

1. **Memory 統合の欠如**: Plan Mode は `.claude/plans/` にのみ保存され、Serena Memory に保存されない
2. **他 Agent からの参照不可**: `.claude/plans/` のファイルは他の Agent が参照・修正できない
3. **知識の分断**: Plan Mode の計画が Memory-First workflow に統合されず、設計知識が失われる

## User Requirements

- Plan Mode の結果を自動的に Memory に同期
- Serena Memory（短期、0.3-0.5秒）と Cipher Memory（長期、クロスプロジェクト）の両方に保存
- Plan Mode（軽量）と `/planning`（包括的設計）の使い分けを維持

## Solution Design

### Architecture Overview

```
Plan Mode Workflow:
┌─────────────────┐
│  Plan Mode      │ (Claude Code native)
│  .claude/plans/ │
└────────┬────────┘
         │ Auto-sync
         ↓
┌─────────────────┐
│ Serena Memory   │ (Short-term, project-specific)
│ .serena/        │ plan_{topic}_{YYYY_MM_DD}.md
│ memories/       │
└────────┬────────┘
         │ Extract after implementation
         ↓
┌─────────────────┐
│ Cipher Memory   │ (Long-term, cross-project)
│ Design patterns │ Reusable knowledge
└─────────────────┘
```

### Implementation Strategy

**Option A: Post-Tool-Use Hook (Recommended)**
- 利点: 完全自動、ユーザーアクション不要
- 実装: `.claude/hooks/hook_post_commands.py` で `ExitPlanMode` を検知
- トリガー: Plan Mode 終了時に自動実行

**Option B: Custom Slash Command `/sync-plan`**
- 利点: ユーザー制御可能、選択的な同期
- 実装: `.claude/commands/sync-plan.md` で新規コマンド作成
- トリガー: Plan Mode 後にユーザーが明示的に実行

**Recommended: Hybrid Approach**
- Post-Tool-Use Hook で自動同期（Option A）
- `/sync-plan` コマンドで手動同期も可能（Option B）
- ユーザーは hook を無効化して手動モードに切り替え可能

## Implementation Plan

### Phase 1: Post-Tool-Use Hook Implementation

**File: `.claude/hooks/hook_post_plan_mode.py`** (新規作成)

```python
#!/usr/bin/env python3
"""
Post-Tool-Use Hook for Plan Mode Memory Sync

Plan Mode 終了時に .claude/plans/ の計画を Serena Memory に自動同期
"""

import json
import sys
from datetime import datetime
from pathlib import Path

def sync_plan_to_serena(plan_file_path: Path, log_file: Path):
    """Plan Mode の計画を Serena Memory に同期"""
    # 1. Plan file を読み込み
    # 2. Topic を抽出（ファイル名またはタイトル行から）
    # 3. .serena/memories/plan_{topic}_{YYYY_MM_DD}.md として保存
    # 4. Metadata 追加（created_at, context, source: plan_mode）
    # 5. ログ出力

def main():
    """メイン処理"""
    # hook_pre_commands.py と同様の構造
    # - 標準入力から hook data を読み取り
    # - ExitPlanMode 検知時に sync_plan_to_serena() 実行
    # - 成功メッセージを JSON で返却
    pass
```

**Hook Configuration** (`.claude/settings.local.json` に追加):

```json
"hooks": {
  "PreToolUse": [...existing...],
  "PostToolUse": [
    {
      "matcher": "ExitPlanMode",
      "hooks": [
        {
          "type": "command",
          "command": "/workspaces/LoRAIro/.claude/hooks/hook_post_plan_mode.py"
        }
      ]
    }
  ]
}
```

### Phase 2: Custom `/sync-plan` Command

**File: `.claude/commands/sync-plan.md`**

```yaml
---
description: Sync Plan Mode results to Serena Memory
allowed-tools:
  - mcp__serena__write_memory
  - mcp__serena__read_memory
  - Read
  - Glob
---

## Workflow
1. Find latest plan in .claude/plans/
2. Extract plan content + metadata
3. Write to Serena Memory with standardized naming
4. Optionally prompt for Cipher extraction (important design decisions)
```

### Phase 3: Memory Template Enhancement

**File: `.claude/skills/mcp-memory-first-development/memory-templates.md`**

追加テンプレート: **Serena - Plan Mode Sync**

```markdown
# Plan: {topic}

**Created**: {YYYY-MM-DD}
**Context**: {task description}
**Status**: planning | implementing | completed

## Original Plan
{plan content from .claude/plans/}

## Implementation Notes
{updates during implementation}

## Outcome
{results after completion}
```

### Phase 4: Differentiation Documentation

**File: `CLAUDE.md`** (更新)

```markdown
### Plan Mode vs `/planning` Command

**Plan Mode** (Quick Task Planning):
- 用途: 単一機能の実装、即座の実行タスク
- 出力: `.claude/plans/` → Serena Memory（自動同期）
- 所要時間: 5-10分
- Memory: Serena のみ（プロジェクト固有）

**/planning Command** (Comprehensive Design):
- 用途: 複雑なアーキテクチャ決定、複数フェーズ機能
- 出力: Cipher Memory（設計パターン） + Serena Memory
- 所要時間: 20-40分
- Memory: Serena + Cipher（クロスプロジェクト知識）
- Workflow: Investigation + Library Research + Solutions agents
```

## Critical Files to Modify

1. **`.claude/hooks/hook_post_plan_mode.py`** (新規)
   - Plan Mode 終了時の自動同期ロジック

2. **`.claude/commands/sync-plan.md`** (新規)
   - 手動同期用カスタムコマンド

3. **`.claude/settings.local.json`** (更新)
   - PostToolUse hook 設定追加
   - `/sync-plan` コマンド許可

4. **`.claude/skills/mcp-memory-first-development/memory-templates.md`** (更新)
   - Plan Mode Sync テンプレート追加

5. **`.claude/skills/mcp-memory-first-development/SKILL.md`** (更新)
   - Plan Mode 統合ワークフロー追記

6. **`CLAUDE.md`** (更新)
   - Plan Mode vs `/planning` 使い分けガイド追加

## Implementation Steps

### Step 1: Hook Implementation
1. Create `.claude/hooks/hook_post_plan_mode.py`
2. Follow `hook_pre_commands.py` pattern:
   - Read JSON input from stdin
   - Extract tool_name and verify it's "ExitPlanMode"
   - Locate latest plan file in `.claude/plans/` directory
3. Implement `sync_plan_to_serena()` function:
   - Parse plan file name to extract topic
   - Read plan content from `.claude/plans/{plan-file}.md`
   - Sanitize topic name (replace hyphens with underscores)
   - Generate memory file: `plan_{topic}_{YYYY_MM_DD}.md`
   - Add metadata header (created, source: plan_mode, original_file)
   - Write to `.serena/memories/`
4. Add logging to `.claude/logs/hook_post_plan_mode.log`
5. Make executable: `chmod +x .claude/hooks/hook_post_plan_mode.py`

### Step 2: Settings Configuration
1. Update `.claude/settings.local.json`
2. Add PostToolUse hook configuration:
   ```json
   "hooks": {
     "PostToolUse": {
       "path": ".claude/hooks/hook_post_commands.py",
       "triggers": ["ExitPlanMode"]
     }
   }
   ```

### Step 3: Custom Command Creation
1. Create `.claude/commands/sync-plan.md`
2. Define allowed-tools (Serena MCP only)
3. Implement 4-step workflow:
   - Find latest plan
   - Extract metadata
   - Write to Serena
   - Optionally extract to Cipher

### Step 4: Template Enhancement
1. Add Plan Mode Sync template to `memory-templates.md`
2. Include metadata fields (created, context, status)
3. Add section for implementation notes

### Step 5: Documentation Updates
1. Update `CLAUDE.md` with Plan Mode vs `/planning` comparison
2. Add quick reference guide
3. Document auto-sync behavior
4. Add troubleshooting section

### Step 6: Testing & Validation
1. Test auto-sync with real Plan Mode session
2. Verify Serena Memory file creation
3. Test manual `/sync-plan` command
4. Verify no conflicts with existing `/planning` workflow
5. Test Cipher extraction after implementation completion

## Success Criteria

- [ ] Plan Mode の計画が自動的に Serena Memory に同期される
- [ ] 他の Agent が `.serena/memories/` から計画を参照可能
- [ ] `/planning` コマンドとの使い分けが明確に文書化
- [ ] Cipher Memory への設計知識抽出フローが確立
- [ ] 既存の Memory-First workflow と整合性がある
- [ ] Hook の有効化/無効化が設定で切り替え可能

## Migration Path

1. **既存の `.claude/plans/` ファイル**:
   - `/sync-plan` で手動同期可能
   - 古い計画は archive/削除を推奨

2. **Backward Compatibility**:
   - Hook を無効化すれば従来の Plan Mode のみ使用可能
   - `/planning` コマンドは変更なし（既存ワークフロー維持）

3. **Gradual Adoption**:
   - Phase 1: Hook のみ実装（自動同期）
   - Phase 2: `/sync-plan` 追加（手動制御）
   - Phase 3: Documentation 完成（ベストプラクティス共有）

## Notes

- Hook の実装は Python で記述（既存の `hook_pre_commands.py` と同様）
- Serena Memory のファイル名は既存の命名規則に準拠
- Cipher への抽出は実装完了後の Phase 3（Memory-First workflow と同様）
- `.claude/plans/` は残す（Claude Code native 機能を尊重）
