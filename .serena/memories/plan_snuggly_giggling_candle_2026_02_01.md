# Plan: snuggly-giggling-candle

**Created**: 2026-02-01 00:22:46
**Source**: plan_mode
**Original File**: snuggly-giggling-candle.md
**Status**: planning

---

# テスト計画: Tech-Debt Cleanup実装変更のテスト検証・修正

## 背景
Tech-debt cleanupプラン（Phase 1-5）で以下の実装変更を行った:
- Worker 3分割 (database_worker.py → registration/search/thumbnail_worker.py + re-export)
- db_repository.py/db_manager.py のメソッド抽出
- image-annotator-lib api.py/onnx.py のメソッド抽出
- genai-tag-db-tools repository.py のメソッド抽出
- batch_processor.py の未使用変数修正

## 現状のテスト結果

### 変更関連テスト（全通過済み）
- `tests/unit/workers/test_database_worker.py` - 11 passed ✅
- `tests/unit/gui/services/test_worker_service.py` - 全通過 ✅
- `tests/integration/gui/workers/test_worker_error_recording.py` - 全通過 ✅
- `tests/unit/database/` - 118 passed ✅
- `local_packages/image-annotator-lib/tests/` - 793 passed ✅
- `local_packages/genai-tag-db-tools/tests/` - 245 passed ✅

### 発見済みの問題
1. **test_dataset_controller.py** - `test_select_and_register_images_no_filesystem_manager`
   - テストが `QMessageBox.critical` を期待するが、実装は `QMessageBox.warning` を呼ぶ
   - **既存バグ**（今回の変更とは無関係だが、発見したので修正する）

2. **test_error_detail_dialog.py** - PySide6 Segfault
   - Qt ウィジェットテストでセグメンテーションフォルト発生
   - **既存問題**（PySide6環境依存、修正対象外）

3. **その他の既存失敗** - tag_management, configuration_service, upscaler等
   - 今回の変更とは完全に無関係の既存バグ

## 実行計画

### Step 1: Ruff Lint検証
```bash
uv run ruff check src/ tests/ --output-format=grouped
```

### Step 2: Ruff Format検証
```bash
uv run ruff format --check src/ tests/
```

### Step 3: 変更関連テストの最終確認
```bash
uv run pytest tests/unit/workers/ tests/unit/gui/services/test_worker_service.py tests/integration/gui/workers/ tests/unit/database/ -q --timeout=30
```

### Step 4: 既存バグ修正 - test_dataset_controller.py
- ファイル: `tests/unit/gui/controllers/test_dataset_controller.py:159`
- 修正: `mock_msgbox.critical.assert_called_once()` → `mock_msgbox.warning.assert_called_once()`
- 理由: 実装（dataset_controller.py:88-94）は `QMessageBox.warning()` を呼ぶ

### Step 5: ローカルパッケージテスト最終確認
```bash
uv run pytest local_packages/image-annotator-lib/tests/ -q --timeout=30
uv run pytest local_packages/genai-tag-db-tools/tests/ -q --timeout=30
```

### Step 6: 検証レポート出力

## 修正対象ファイル
- `tests/unit/gui/controllers/test_dataset_controller.py` - 既存バグ修正（1行）

## 検証方法
- 全変更関連テスト通過
- ruff check/format クリーン
- 新規テスト追加不要（内部メソッド抽出のみで公開API変更なし）
