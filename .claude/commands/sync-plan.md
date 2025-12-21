---
allowed-tools: mcp__serena__write_memory, mcp__serena__read_memory, mcp__serena__list_memories, Read, Glob, Bash
description: Plan Mode の計画を手動で Serena Memory に同期します。Auto-sync が失敗した場合や過去の計画を同期する際に使用。
---

## 使用方法
```bash
/sync-plan [plan-file-name]
```

引数を省略すると、`.claude/plans/` 内の最新ファイルを同期します。

## 説明

Claude Code の Plan Mode で作成した計画ファイルを `.serena/memories/` に同期します。

PostToolUse hook による自動同期が既に設定されていますが、以下の場合に手動同期が必要です：
- Hook が無効化されている場合
- 過去の計画ファイルを遡って同期する場合
- 自動同期が失敗した場合のリカバリー

## タスクフロー

### 1. Plan File 特定
1. 引数が指定されている場合、そのファイル名で検索
2. 引数がない場合、`.claude/plans/` 内の最新ファイルを取得
3. ファイルが存在しない場合はエラーメッセージを表示して終了

### 2. Plan Content 読み込み
4. 指定された plan file を読み込み
5. ファイル名からトピックを抽出（例: "moonlit-munching-yeti.md" → "moonlit-munching-yeti"）
6. 内容の妥当性を確認（空ファイルでないか、フォーマットが正しいか）

### 3. Serena Memory 作成
7. トピック名をサニタイズ（ハイフン → アンダースコア、特殊文字除去）
8. 今日の日付を取得（YYYY_MM_DD形式）
9. Memory ファイル名を生成: `plan_{topic}_{date}.md`
10. 既に同じ名前のメモリが存在する場合は上書き確認

### 4. Metadata 追加
11. Plan content に以下の metadata を追加:
    - Created: 作成日時
    - Source: plan_mode（手動同期の場合は manual_sync）
    - Original File: 元のファイル名
    - Status: planning（初期状態）

### 5. Memory 書き込み
12. `.serena/memories/` ディレクトリの存在確認
13. `mcp__serena__write_memory` を使用して保存
14. 成功メッセージを表示

### 6. 確認と次ステップ提示
15. 同期されたメモリファイル名を表示
16. 他の Agent からの参照方法を説明
17. （オプション）Cipher Memory への抽出を提案

## 出力フォーマット

### Memory File Template

```markdown
# Plan: {original-topic}

**Created**: {YYYY-MM-DD HH:MM:SS}
**Source**: manual_sync
**Original File**: {plan-file}.md
**Status**: planning

---

{original plan content}
```

## 使用例

### 例1: 最新のplanを同期
```bash
/sync-plan
```

出力:
```
✅ Plan synced to Serena Memory: plan_moonlit_munching_yeti_2025_12_21.md

📋 Next steps:
- 他のAgentから参照: mcp__serena__read_memory("plan_moonlit_munching_yeti_2025_12_21")
- 実装後、重要な設計決定を Cipher Memory に抽出することを推奨
```

### 例2: 特定のplanを同期
```bash
/sync-plan my-feature-plan.md
```

## エラーハンドリング

### ケース1: Plan file が見つからない
```
❌ Plan file not found: my-feature-plan.md
Available files in .claude/plans/:
  - moonlit-munching-yeti.md (2025-12-21)
  - previous-feature.md (2025-12-20)
```

### ケース2: Memory が既に存在する
```
⚠️ Memory file already exists: plan_my_feature_2025_12_21.md
Overwrite? (y/n)
```

### ケース3: 書き込みエラー
```
❌ Failed to write to Serena Memory: [error details]
Please check:
- .serena/memories/ directory exists
- Serena MCP is running
- Sufficient disk space
```

## 制約と注意事項

1. **Serena Memory のみ**:
   - このコマンドは Serena Memory（短期、プロジェクト固有）にのみ保存
   - Cipher Memory（長期、クロスプロジェクト）への保存は手動で実行

2. **上書き動作**:
   - 同じ日付・トピックの Memory が存在する場合、確認後に上書き
   - 元のファイルは `.claude/plans/` に残る

3. **Auto-sync との併用**:
   - PostToolUse hook による auto-sync と競合しない
   - Hook が有効な場合、Plan Mode 終了時に自動で同期される
   - このコマンドは補助的な手動同期用

## 関連コマンド

- `/planning`: 包括的な設計フェーズ（Cipher Memory に直接保存）
- Plan Mode: Claude Code ネイティブ機能（このコマンドで同期可能）

## 技術仕様

### ファイル名サニタイズルール
- ハイフン（-）→ アンダースコア（_）
- 特殊文字（英数字・アンダースコア以外）→ 除去
- 全て小文字に変換

### Memory File 命名規則
```
plan_{sanitized_topic}_{YYYY_MM_DD}.md
```

例:
- Input: "moonlit-munching-yeti.md"
- Output: "plan_moonlit_munching_yeti_2025_12_21.md"

## 実装後のワークフロー

1. Plan Mode または `/planning` で計画策定
2. （Auto-sync または手動で）Serena Memory に同期
3. 実装中、Memory を参照しながら開発
4. 実装完了後、重要な設計決定を Cipher Memory に抽出
5. Memory-First workflow の Phase 3 として知識を永続化
