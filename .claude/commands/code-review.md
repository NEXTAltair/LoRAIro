---
allowed-tools: Task, Bash, Read, Grep, Glob, mcp__serena__search_for_pattern, mcp__serena__find_symbol
description: PRレビュー相当のコード品質検査を実行。security-reviewerとcode-reviewerエージェントを並列で実行し、包括的なレビューを提供します。
---

## 使用方法
```bash
/code-review [対象パス]
```

**例:**
- `/code-review src/lorairo/services/` - サービス層をレビュー
- `/code-review` - 変更されたファイルをレビュー

## 説明
対象: $ARGUMENTS

指定されたパス（または変更ファイル）に対して、以下の品質検査を実行します:
1. **security-reviewer agent**: セキュリティ脆弱性の検出
2. **code-reviewer agent**: コード品質とスタイルの検証
3. **静的解析ツール**: Ruff/mypy による自動チェック

## 実行内容

### Phase 1: 対象ファイルの特定
```bash
# 引数がある場合はそのパスを対象
# 引数がない場合は変更ファイルを対象
git diff --name-only HEAD~1
```

### Phase 2: 並列エージェント実行
以下のエージェントを並列で起動:

#### security-reviewer Agent
- API Key/機密情報の漏洩チェック
- OWASP Top 10 準拠確認
- Python固有のセキュリティリスク検出

#### code-reviewer Agent
- LoRAIro コーディング規約準拠
- 型ヒント・docstring 完備確認
- アーキテクチャパターン準拠

### Phase 3: 静的解析実行
```bash
# Ruff lint チェック
uv run ruff check $ARGUMENTS --output-format=grouped

# mypy 型チェック
uv run mypy $ARGUMENTS --pretty
```

### Phase 4: 結果統合
全ての結果を以下の形式で統合:

```markdown
# Code Review Report

## Summary
- Security Issues: X (Critical: X, High: X, Medium: X)
- Code Quality Issues: X
- Lint Errors: X
- Type Errors: X

## Security Findings
[security-reviewer の結果]

## Code Quality Findings
[code-reviewer の結果]

## Static Analysis
### Ruff
[Ruff の出力]

### mypy
[mypy の出力]

## Recommendations
[優先度順の修正提案]
```

## 出力形式
- 重大度別に問題を分類
- 各問題に修正提案を付与
- 全体評価とアクションアイテム

## 関連コマンド
- `/security-review` - セキュリティ専門レビューのみ
- `/build-fix` - 検出されたエラーの自動修正支援
- `/verify` - 修正後の包括的検証
