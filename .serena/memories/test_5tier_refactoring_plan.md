# 5段階テスト構成リファクタリング計画

**作成日**: 2025-11-10
**対象ブランチ**: `feature/test-refactoring-5tier` (新規作成)
**優先度**: 中
**工数見積**: 2-3週間

---

## 背景

現在の3段階テスト構成（Unit/Integration/BDD）から、Logic/GUI完全分離の5段階構成に移行することで、テスト実行速度を30-40%向上させ、テスト目的を明確化する。

---

## 5段階構成設計

```
tests/
├── unit/
│   ├── logic/              # 純粋ロジック (最速 ~20秒)
│   │   ├── test_search_criteria_processor.py
│   │   ├── test_validation_logic.py
│   │   ├── test_tag_normalization.py
│   │   └── test_annotation_validation.py
│   └── gui/                # GUIユニット (高速 ~1分)
│       ├── widgets/
│       ├── services/
│       └── state/
├── integration/
│   ├── logic/              # ロジック統合 (中速 ~2分)
│   │   ├── test_configuration_integration.py
│   │   ├── test_annotation_service_integration.py
│   │   ├── test_database_integration.py
│   │   └── test_worker_service_integration.py
│   └── gui/                # GUI統合 (低速 ~3分)
│       ├── test_mainwindow_integration.py
│       ├── test_filter_search_integration.py
│       └── test_search_workflow_integration.py
└── bdd/                    # E2E包括シナリオ (最低速 ~2分)
    ├── features/
    └── step_defs/
```

---

## 移行計画

### Phase 1: ディレクトリ構造作成

```bash
mkdir -p tests/unit/logic
mkdir -p tests/integration/logic
mkdir -p tests/integration/gui
```

### Phase 2: Logic Unit Tests分離 (~10件)

**移動元**: `tests/unit/services/`, `tests/unit/database/`

**移動先**: `tests/unit/logic/`

**対象ファイル**:
1. `test_search_criteria_processor.py` → 純粋ロジック部分抽出
2. `test_annotation_service.py` → `_validate_annotation_input()` 部分抽出
3. `test_configuration_service.py` → 設定パースロジック部分抽出
4. `test_image_metadata_extractor.py` → メタデータ抽出ロジック
5. `test_tag_cleaner.py` → タグ正規化ロジック
6. `test_phash_calculator.py` → pHash計算ロジック
7. `test_date_parser.py` → 日付パースロジック
8. `test_resolution_parser.py` → 解像度パースロジック

### Phase 3: Logic Integration Tests移動 (~8件)

**移動元**: `tests/integration/`

**移動先**: `tests/integration/logic/`

**対象ファイル**:
1. `test_configuration_integration.py`
2. `test_annotation_service_integration.py`
3. `test_phase4_integration.py`
4. `test_phase5_integration_tests.py`
5. `test_database_manager_integration.py`
6. `test_worker_service_integration.py`
7. `test_batch_processor_integration.py`

### Phase 4: GUI Integration Tests移動 (~5件)

**移動元**: `tests/integration/`

**移動先**: `tests/integration/gui/`

**対象ファイル**:
1. `test_mainwindow_annotation_integration.py`
2. `test_filter_search_integration.py`
3. `test_gui_configuration_integration.py`
4. `test_dataset_state_integration.py`

### Phase 5: pytest設定更新

**ファイル**: `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = [
    "tests/unit/logic",
    "tests/unit/gui",
    "tests/integration/logic",
    "tests/integration/gui",
    "tests/bdd",
]
```

### Phase 6: CI/CD段階的実行設定

**ファイル**: `.github/workflows/test.yml` (または相当)

```yaml
# Commit Hook: Logic Unit Tests
- name: Fast Tests
  run: uv run pytest tests/unit/logic/ -v

# PR Check: Logic Tests
- name: Standard Tests
  run: |
    uv run pytest tests/unit/logic/ -v
    uv run pytest tests/integration/logic/ -v

# Merge Check: All Tests
- name: Full Tests
  run: uv run pytest -v
```

### Phase 7: 実行スクリプト作成

**ファイル**: `scripts/test_stages.sh`

```bash
#!/bin/bash

case "$1" in
  fast)
    pytest tests/unit/logic/
    ;;
  standard)
    pytest tests/unit/logic/ tests/integration/logic/
    ;;
  gui)
    pytest tests/unit/gui/ tests/integration/gui/
    ;;
  full)
    pytest
    ;;
  *)
    echo "Usage: $0 {fast|standard|gui|full}"
    exit 1
    ;;
esac
```

---

## 期待効果

### 実行速度

**現在** (3段階):
- Unit Tests: ~2分 (Logic + GUI混在)
- Integration Tests: ~5分
- BDD Tests: ~2分
- **合計**: ~9分

**移行後** (5段階):
- Logic Unit: ~20秒
- GUI Unit: ~1分
- Logic Integration: ~2分
- GUI Integration: ~3分
- BDD: ~2分
- **合計**: ~8分20秒 (7%高速化)

**CI段階実行**:
- Commit Hook: `unit/logic/` (20秒)
- PR Check: `unit/logic/ + integration/logic/` (2分20秒)
- Merge Check: 全体 (8分20秒)

### その他効果

- テスト目的の明確化
- 責務分離の強化
- 高速フィードバックループ (20秒)
- GUIテスト遅延の影響排除

---

## 実装手順

### Step 1: 新規ブランチ作成

```bash
git checkout main
git pull
git checkout -b feature/test-refactoring-5tier
```

### Step 2: ディレクトリ構造作成

```bash
mkdir -p tests/unit/logic
mkdir -p tests/integration/logic
mkdir -p tests/integration/gui
```

### Step 3: Logic Unit Tests作成

各ファイルから純粋ロジックテストを抽出し、`tests/unit/logic/` に配置。

### Step 4: ファイル移動

`git mv` でファイルを移動（履歴維持）。

### Step 5: pytest設定更新

`pyproject.toml` の `testpaths` 更新。

### Step 6: 全テスト実行確認

```bash
uv run pytest -v
```

### Step 7: CI/CD設定更新

`.github/workflows/` または `.devcontainer/devcontainer.json` の設定更新。

### Step 8: ドキュメント更新

- `CLAUDE.md` のテストコマンド更新
- `README.md` のテスト説明更新

---

## 追加技術導入（オプション）

### Property-Based Testing (Hypothesis)

**対象**:
- `SearchCriteriaProcessor` 条件パース
- タグ正規化ロジック
- 解像度パースロジック
- 日付範囲フィルタ

**インストール**:
```bash
uv add --dev hypothesis
```

**実装例**:
```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=1, max_value=10000), 
       st.integers(min_value=1, max_value=10000))
def test_resolution_parser_properties(width, height):
    result = parse_resolution(f"{width}x{height}")
    assert result == (width, height)
```

### Snapshot Testing (pytest-insta)

**対象**:
- AI annotation結果
- データベースクエリ結果
- 設定ファイルパース結果

**インストール**:
```bash
uv add --dev pytest-insta
```

**実装例**:
```python
def test_annotation_result_structure(snapshot):
    result = annotator.annotate(test_image)
    assert result == snapshot
```

---

## リスク

### 1. 移動ファイル数が多い (~30件)
- **対策**: 段階的移行、各Phase毎にコミット・テスト実行

### 2. 既存テストの更新が必要
- **対策**: 各テストファイルの import パス更新

### 3. CI/CD設定変更の影響
- **対策**: ローカルで十分にテスト後、CI/CD設定変更

### 4. チーム学習コスト
- **対策**: ドキュメント整備、README更新

---

## 完了基準

- ✅ 全ファイルが5段階構成に配置
- ✅ pytest実行エラーなし
- ✅ カバレッジ75%以上維持
- ✅ CI/CD段階的実行動作
- ✅ 実行スクリプト動作確認
- ✅ ドキュメント更新完了

---

## 関連情報

### 現在のテスト構成
- Unit: 59ファイル
- Integration: 15ファイル
- BDD: 2 feature files
- 合計: ~76ファイル

### 参考資料
- Testing Diamond: https://martinfowler.com/articles/practical-test-pyramid.html
- Subcutaneous Testing: https://martinfowler.com/bliki/SubcutaneousTest.html
- Property-Based Testing: https://hypothesis.readthedocs.io/

---

**作成者**: Claude Code
**最終更新**: 2025-11-10
