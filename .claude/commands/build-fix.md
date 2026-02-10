---
allowed-tools: Task, Bash, Read, Grep, mcp__serena__find_symbol, mcp__serena__search_for_pattern
description: ビルド/テストエラーの自動診断と修正提案。pytest失敗、mypy/Ruffエラーを解析し、具体的な修正案を提示します。
---

## 使用方法
```bash
/build-fix [エラー出力またはファイルパス]
```

**例:**
- `/build-fix` - 直近のビルドエラーを解析
- `/build-fix tests/unit/test_service.py` - 特定テストのエラーを解析

## 説明
対象: $ARGUMENTS

ビルドエラーやテスト失敗を診断し、修正案を提示します:
1. **pytest 失敗**: テストの失敗原因を分析
2. **mypy エラー**: 型エラーの解決策を提案
3. **Ruff 違反**: lint違反の自動修正方法を提示

## 実行内容

### Phase 1: エラー収集
```bash
# テストエラーの収集
uv run pytest --tb=short 2>&1 | tail -100

# 型エラーの収集
uv run mypy -p lorairo 2>&1 | tail -50

# lint エラーの収集
uv run ruff check src/ tests/ 2>&1 | tail -50
```

### Phase 2: build-error-resolver Agent 起動
エラー情報を build-error-resolver agent に渡し、以下を分析:
- エラーの根本原因特定
- 関連コードの調査（Serena活用）
- 修正案の生成

### Phase 3: 修正提案
各エラーに対して:
1. エラー内容と場所
2. 根本原因の説明
3. 具体的な修正コード
4. 修正後の検証方法

## 出力形式

```markdown
# Build Error Resolution Report

## Error Summary
- pytest failures: X
- mypy errors: X
- Ruff violations: X

## Fixes

### Error 1: [Type] - [Brief Description]
**File**: `path/to/file.py:line`
**Error**:
```
[Error message]
```

**Root Cause**: [Explanation]

**Fix**:
```python
# Before
...

# After
...
```

**Verify**: `uv run pytest tests/unit/test_xxx.py::test_name`

---
```

## 自動修正可能なエラー

### Ruff Auto-fix
```bash
# 自動修正可能な違反を修正
uv run ruff check --fix src/ tests/

# フォーマット修正
uv run ruff format src/ tests/
```

### Import Sorting
```bash
# import の並び替え
uv run ruff check --select I --fix src/ tests/
```

## 関連コマンド
- `/code-review` - 包括的なコードレビュー
- `/verify` - 修正後の検証
- `/test` - テスト実行
