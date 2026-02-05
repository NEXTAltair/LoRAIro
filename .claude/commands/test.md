---
allowed-tools: mcp__serena__find_symbol, mcp__serena__find_referencing_symbols, mcp__serena__get_symbols_overview, mcp__serena__search_for_pattern, mcp__serena__read_memory, mcp__serena__write_memory, Read, Edit, Write, Bash, TodoWrite, Task, Glob, Grep
description: テスト実行・同期・品質チェック。クイックチェック、包括的テスト、テスト同期（追加・修正・削除）に対応。

---
# テスト・検証フェーズ

## 使用方法

```bash
/test                    # クイック品質チェック（Ruff/mypy/pytest）
/test sync               # テスト同期（追加・修正・削除）
/test sync <パス>        # 指定パスのテスト同期
/test <対象の説明>       # 包括的テスト実行
```

**例:**
- `/test` - Ruff/mypy/pytest のクイックチェックのみ
- `/test sync` - 変更されたコードに対するテスト同期
- `/test sync src/lorairo/services/tag_management_service.py` - 特定ファイルのテスト同期
- `/test 新しいタグ管理機能` - 機能全体の包括的テスト

---

## モード1: クイック品質チェック（引数なし）

引数なしで `/test` を実行した場合、以下のクイックチェックのみを実行します：

### Step 1: Ruff Lint検証
```bash
uv run ruff check src/ tests/ --output-format=grouped
```

### Step 2: mypy 型チェック
```bash
uv run mypy -p lorairo --pretty
```

### Step 3: pytest テスト実行
```bash
uv run pytest --cov=src --cov-report=term-missing -v
```

### 出力形式
```markdown
# Quick Verification Report

| Check | Status | Details |
|-------|--------|---------|
| Ruff  | ✅/❌ | X errors |
| mypy  | ✅/❌ | X errors |
| pytest | ✅/❌ | X passed, Y failed |
| Coverage | ✅/❌ | XX.X% (target: 75%) |

## Overall Status
✅ All checks passed - Ready for commit
❌ Checks failed - See details above
```

**エラー時**: `/build-fix` で修正案を取得

---

## モード2: テスト同期（`sync` 引数）

コード修正後に、テストの追加・修正・削除を自動判定・実行します。

### 実行手順

#### Step 1: 変更検出
```bash
# git diffで変更ファイルを特定
git diff --name-only HEAD~1..HEAD -- 'src/**/*.py'
git diff --name-status HEAD~1..HEAD -- 'src/**/*.py'
```

変更種別を分類:
- **A (Added)**: 新規ファイル → テスト追加が必要
- **M (Modified)**: 変更ファイル → テスト修正が必要な可能性
- **D (Deleted)**: 削除ファイル → テスト削除が必要

#### Step 2: 影響分析

**Serena活用**: 変更されたシンボルと参照関係を解析
```
1. get_symbols_overview で変更ファイルの構造把握
2. find_symbol で変更されたクラス・関数を特定
3. find_referencing_symbols で影響範囲を特定
```

**テストファイル対応表作成**:
- `src/lorairo/services/foo.py` → `tests/unit/services/test_foo.py`
- `src/lorairo/gui/widgets/bar.py` → `tests/unit/gui/widgets/test_bar.py`

#### Step 3: テスト同期アクション

| 変更種別 | アクション |
|---------|-----------|
| 新規クラス/関数追加 | 対応するテストを追加 |
| 既存関数のシグネチャ変更 | テストを修正 |
| 関数/クラス削除 | 対応テストを削除 |
| 内部実装のみ変更 | テスト実行で確認（変更不要の場合多） |
| 依存関係変更 | 統合テストの確認・修正 |

#### Step 4: テスト追加

新規コードに対するテストを生成:

```python
# テスト生成の原則
# 1. 正常系: 基本的な動作確認
# 2. 境界値: 空リスト、None、最大値等
# 3. 異常系: 例外発生ケース
# 4. 統合: 他コンポーネントとの連携（必要な場合）
```

**テスト配置規則**:
- Unit: `tests/unit/<module_path>/test_<filename>.py`
- Integration: `tests/integration/test_<feature>.py`
- GUI: `tests/unit/gui/<widget_path>/test_<widget>.py`

#### Step 5: テスト修正

既存テストの修正が必要な場合:
1. 失敗するテストを特定
2. 変更されたAPIに合わせてテストを更新
3. 新しい動作に対するアサーションを追加/修正

#### Step 6: テスト削除

削除されたコードに対応するテストを処理:
1. 対応するテストファイル/テスト関数を特定
2. **ユーザーに確認**: 削除前に確認を取る
3. 削除実行（またはスキップマーク付与）

### 出力形式（テスト同期）

```markdown
# Test Sync Report

## 変更検出結果
| ファイル | 変更種別 | 影響テスト |
|---------|---------|-----------|
| src/lorairo/services/foo.py | Modified | tests/unit/services/test_foo.py |
| src/lorairo/gui/widgets/bar.py | Added | (新規作成必要) |
| src/lorairo/utils/old.py | Deleted | tests/unit/utils/test_old.py |

## 実行アクション
### 追加したテスト
- `tests/unit/gui/widgets/test_bar.py` - BarWidgetのユニットテスト

### 修正したテスト
- `tests/unit/services/test_foo.py::test_process_data` - シグネチャ変更に対応

### 削除提案（要確認）
- `tests/unit/utils/test_old.py` - old.py削除に伴う不要テスト

## 検証結果
| Check | Status |
|-------|--------|
| 新規テスト | ✅ 全パス |
| 修正テスト | ✅ 全パス |
| 回帰テスト | ✅ 影響なし |
```

---

## モード3: 包括的テスト（対象説明を指定）

テスト対象: $ARGUMENTS

### 実行フロー

#### Phase 1: テスト準備
1. 実装結果確認（Serena Memory参照）
2. 既存テストスイート実行（基線確認）
3. テスト対象の特定（investigation agent活用）

#### Phase 2: 段階的テスト実行

```bash
# Unit Tests
uv run pytest -m unit -v

# Integration Tests
uv run pytest -m integration -v

# GUI Tests (headless)
QT_QPA_PLATFORM=offscreen uv run pytest -m gui -v

# Full Coverage
uv run pytest --cov=src --cov-report=html -v
```

#### Phase 3: 品質確認

```bash
# Lint
uv run ruff check src/ tests/

# Type Check
uv run mypy -p lorairo

# Coverage Threshold
uv run pytest --cov=src --cov-fail-under=75
```

### テスト種別と責務

| 種別 | 場所 | 責務 | モック |
|-----|------|------|-------|
| Unit | tests/unit/ | 単一クラス・関数 | 外部依存のみ |
| Integration | tests/integration/ | モジュール間連携 | 外部API |
| GUI | tests/unit/gui/ | Widget動作 | QMessageBox等 |
| BDD | tests/bdd/ | E2Eシナリオ | 最小限 |

### 異常系テスト観点

- エラーハンドリング・不正入力
- ファイルシステムエラー
- AI API エラー・タイムアウト
- データベース接続・整合性エラー

### 出力形式（包括的テスト）

```markdown
# Comprehensive Test Report

## Test Results
| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Unit | XX | X | X |
| Integration | XX | X | X |
| GUI | XX | X | X |

## Coverage
- Overall: XX.X%
- New Code: XX.X%
- Target: 75% ✅/❌

## Quality Checks
| Check | Status |
|-------|--------|
| Ruff | ✅/❌ |
| mypy | ✅/❌ |

## Issues Found
1. [issue description]

## Recommendations
1. [recommendation]
```

---

## テスト作成ガイドライン

### pytest-qt ベストプラクティス

```python
# シグナル待機
with qtbot.waitSignal(widget.completed, timeout=5000):
    widget.start_operation()

# UI状態待機
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=5000)

# ダイアログモック
monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
```

### モック戦略

**モック対象**: 外部API、ファイルシステム（大量）、ネットワーク
**モック非対象**: 内部サービス連携、DB操作（テストDB使用）、Qt Signal/Slot

### 命名規則

```python
# ファイル: test_<module_name>.py
# 関数: test_<機能>_<条件>_<期待結果>
def test_search_with_empty_query_returns_all_items():
    ...
```

---

## 必読ファイル

- `.claude/rules/testing.md` - テスト規約
- `tests/conftest.py` - 共通フィクスチャ
- `pyproject.toml` - pytest設定

## 次のコマンド

- テスト失敗時: `/build-fix` で修正案取得
- 問題調査: `/check-existing` で原因調査
- 改善実装: `/planning` で計画策定
