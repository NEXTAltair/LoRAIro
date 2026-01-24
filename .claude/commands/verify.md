---
allowed-tools: Bash, Read, Grep
description: 実装完了後の包括的検証ループ。Ruff/mypy/pytest を実行し、品質基準を満たしているか確認します。
---

## 使用方法
```bash
/verify [対象パス]
```

**例:**
- `/verify` - 全体検証
- `/verify src/lorairo/services/` - サービス層のみ検証

## 説明
対象: $ARGUMENTS

実装完了後の品質ゲートとして、以下の検証を順次実行します:
1. **Ruff**: Lint検証
2. **mypy**: 型チェック
3. **pytest**: テスト実行 + カバレッジ確認

## 成功基準
- Ruff: エラー0件
- mypy: エラー0件
- pytest: 全テストパス
- カバレッジ: 75%以上

## 実行内容

### Step 1: Ruff Lint検証
```bash
echo "=== Ruff Lint Check ==="
uv run ruff check src/ tests/ --output-format=grouped
```

**期待結果**: エラー0件
**失敗時**: `/build-fix` で修正案を取得

### Step 2: mypy 型チェック
```bash
echo "=== mypy Type Check ==="
uv run mypy -p lorairo --pretty
```

**期待結果**: エラー0件
**失敗時**: `/build-fix` で修正案を取得

### Step 3: pytest テスト実行
```bash
echo "=== pytest Test Execution ==="
uv run pytest --cov=src --cov-report=term-missing -v
```

**期待結果**: 全テストパス、カバレッジ75%以上
**失敗時**: テスト失敗の詳細を確認

### Step 4: カバレッジ確認
```bash
echo "=== Coverage Summary ==="
uv run pytest --cov=src --cov-report=json -q
python -c "import json; d=json.load(open('coverage.json')); print(f'Coverage: {d[\"totals\"][\"percent_covered\"]:.1f}%')"
```

## 出力形式

```markdown
# Verification Report

## Results Summary
| Check | Status | Details |
|-------|--------|---------|
| Ruff  | ✅/❌ | X errors |
| mypy  | ✅/❌ | X errors |
| pytest | ✅/❌ | X passed, Y failed |
| Coverage | ✅/❌ | XX.X% (target: 75%) |

## Details

### Ruff
[出力詳細]

### mypy
[出力詳細]

### pytest
[出力詳細]

### Coverage
[カバレッジレポート]

## Overall Status
✅ All checks passed - Ready for commit
❌ Checks failed - See details above
```

## 検証失敗時のアクション

### Ruff エラー
```bash
# 自動修正
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

### mypy エラー
```bash
# エラー詳細確認
uv run mypy -p lorairo --show-error-codes
```

### pytest 失敗
```bash
# 失敗テストのみ再実行
uv run pytest --lf -v
```

### カバレッジ不足
```bash
# カバレッジの低いファイル確認
uv run pytest --cov=src --cov-report=html
# htmlcov/index.html を確認
```

## 関連コマンド
- `/code-review` - コードレビュー（検証前に推奨）
- `/build-fix` - エラー修正支援
- `/test` - テストのみ実行
