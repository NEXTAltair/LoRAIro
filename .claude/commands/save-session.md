---
allowed-tools: mcp__serena__read_memory, mcp__serena__list_memories, mcp__serena__write_memory, Read, Glob, Grep, Bash, Task, TodoWrite
description: セッション終了前に実装結果・テスト結果・設計意図・問題解決方法を要約し、Moltbot LTM（Notion）に永続保存します。
---

# セッション記録・LTM保存

## 使用方法

```bash
/save-session [トピックやコンテキスト]
```

引数を省略した場合、会話履歴から自動的にトピックを推定します。

## 説明

実装完了後・テスト完了後にセッションの成果を要約し、以下の2箇所に保存します：

1. **Serena Memory**（短期・プロジェクト固有）: セッション記録として保存
2. **Moltbot LTM**（長期・クロスプロジェクト）: 設計意図・問題解決方法を永続保存

## タスクフロー

### Phase 1: セッション情報の収集

1. **git diff の確認**: 今セッションでの変更ファイルを把握
   ```bash
   git diff --stat HEAD~N  # 直近のコミットから変更を把握
   git log --oneline -10   # 今セッションのコミットを確認
   ```

2. **Serena Memory の確認**: 関連する plan memory があれば読み込み
   - `plan_*` で始まるメモリから、今セッションで使用した計画を特定
   - 計画の Status を確認（planning → implemented に更新予定）

3. **テスト結果の確認**: 直近のテスト結果があればサマリーを取得
   - カバレッジ情報
   - 成功/失敗テスト数
   - 修正した問題

### Phase 2: セッションサマリーの構築

4. 収集した情報から以下のセクションを構成:

```markdown
## 実装結果
- 変更ファイル一覧と概要
- 追加/変更/削除した機能

## テスト結果
- テスト実行結果（成功/失敗/スキップ）
- カバレッジ（変更前→変更後）

## 設計意図
- なぜこのアプローチを選んだか
- 検討した代替案とその却下理由
- アーキテクチャ上の決定事項

## 問題と解決
- 遭遇した問題とその解決方法
- ワークアラウンドや注意点

## 未完了・次のステップ
- 残タスクや TODO
- 次セッションへの申し送り事項
```

### Phase 3: Serena Memory 保存

5. セッション記録を Serena Memory に保存:
   - ファイル名: `session_{sanitized_topic}_{YYYY_MM_DD}.md`
   - 全セクションを含むフル記録

6. 関連する plan memory の Status を更新:
   - `planning` → `implemented`（実装完了の場合）
   - `planning` → `in_progress`（部分実装の場合）

### Phase 4: Moltbot LTM 保存

7. **設計意図と問題解決方法**を抽出し、Moltbot LTM に保存:
   - LTM に保存すべき内容: 再利用可能な知識（設計判断、問題解決パターン、教訓）
   - LTM に保存しない内容: 一時的な実装詳細、ファイル一覧、テスト数値

8. `ltm_write.py` スクリプトを使用して保存:
   ```bash
   python3 .github/skills/lorairo-mem/scripts/ltm_write.py <<'JSON'
   {
     "title": "...",
     "summary": "...",
     "body": "...",
     "type": "decision|howto|note",
     "status": "curated",
     "importance": "High|Medium|Low",
     "source": "Container",
     "environment": ["Container"],
     "tags": ["..."],
     "author": "claude-code"
   }
   JSON
   ```

9. LTM ペイロードの構成ルール:
   - **title**: 簡潔に（50文字以内）。例: "SearchFilterService: 遅延初期化パターン採用"
   - **summary**: 1-2文で要点。例: "Qt依存サービスの初期化順序問題をCompositionパターンで解決"
   - **body**: Markdown形式で詳細を記述。設計意図・代替案・理由を中心に
   - **type**: 設計判断 → `decision`、問題解決 → `howto`、一般記録 → `note`
   - **importance**: アーキテクチャ影響あり → `High`、局所的 → `Medium`、参考情報 → `Low`
   - **tags**: 関連技術・コンポーネント名（小文字、例: `["pyside6", "service-layer", "initialization"]`）

### Phase 5: 確認と完了

10. 保存結果を表示:
    - Serena Memory ファイル名
    - Moltbot LTM 保存結果（成功/失敗）
    - 保存された内容の要約

11. Moltbot LTM が失敗した場合のフォールバック:
    - エラー内容を表示
    - Serena Memory には保存済みであることを確認
    - 手動で curl コマンドを提示（後から再試行可能）

## 出力フォーマット

### Serena Memory Template

```markdown
# Session: {topic}

**Date**: {YYYY-MM-DD}
**Branch**: {current branch}
**Status**: completed | partial

---

## 実装結果
{implementation summary}

## テスト結果
{test results}

## 設計意図
{design decisions}

## 問題と解決
{issues and solutions}

## 未完了・次のステップ
{remaining tasks}
```

### Moltbot LTM Payload 例

```json
{
  "title": "Qt-Free Core Pattern: ServiceContainer DI設計",
  "summary": "ビジネスロジックをQt非依存にする Composition over Inheritance パターンを採用。CLI/API再利用を実現。",
  "body": "## 設計意図\n- GUI依存を排除し、CLIツールでも同じビジネスロジックを使用可能にする\n- InheritanceではなくCompositionを使い、テスタビリティを向上\n\n## 代替案と却下理由\n- Abstract Base Class: テスト時のモック作成が煩雑\n- Mixin: 多重継承の複雑性\n\n## 教訓\n- Signal/Slotは薄いラッパーに閉じ込め、コアロジックには持ち込まない",
  "type": "decision",
  "status": "curated",
  "importance": "High",
  "source": "Container",
  "environment": ["Container"],
  "tags": ["architecture", "dependency-injection", "qt-free", "service-layer"],
  "author": "claude-code"
}
```

## 使用例

### 例1: 実装完了後のセッション保存
```bash
/save-session SearchFilterService遅延初期化の実装
```

### 例2: 引数なし（自動推定）
```bash
/save-session
```

### 例3: 部分実装の記録
```bash
/save-session MainWindow UI redesign Phase 2（途中）
```

## エラーハンドリング

### Moltbot LTM 書き込み失敗
```
⚠️ Moltbot LTM への保存に失敗しました: [error details]

✅ Serena Memory には保存済み: session_search_filter_2026_01_30.md

手動再試行:
  python3 .github/skills/lorairo-mem/scripts/ltm_write.py <<'JSON'
  {payload}
  JSON
```

### git 変更なし
```
ℹ️ git に未コミットの変更がありません。
セッション中のコミット履歴から記録を生成します。
```

## 判断基準: LTM に保存すべき内容

### 保存すべき（再利用可能な知識）
- アーキテクチャ決定とその理由
- 繰り返し使えるパターン・アンチパターン
- 非自明な問題の解決方法
- 外部ライブラリの使い方の注意点
- パフォーマンス最適化の知見

### 保存しない（一時的な情報）
- 具体的なファイルパスやコード行番号
- テストの数値結果（カバレッジ%等）
- 一時的なワークアラウンド
- 自明なバグ修正

## 関連コマンド

- `/sync-plan`: Plan を Serena Memory に同期
- `/planning`: 包括的な設計フェーズ（LTM 直接保存あり）
- `/implement`: 実装フェーズ
- `/test`: テスト・検証フェーズ

## ワークフロー上の位置付け

```
/planning → /sync-plan → /implement → /test → /save-session
                                                    ↑ ここ
```

セッション終了前の最終ステップとして使用。
次のセッション開始時に Serena Memory や Moltbot LTM から前回の記録を参照可能。
