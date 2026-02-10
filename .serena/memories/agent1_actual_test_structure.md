# LoRAIro 実テスト構造詳細分析（pytest collect-only）

**更新日**: 2026-02-10
**実行方法**: `uv run pytest --collect-only -q`
**データソース**: analyze_tests.py スクリプト実行結果

---

## 📊 実テスト統計（修正版）

| 項目 | 値 |
|------|-----|
| **総テストファイル数** | **91個** |
| **総テスト数** | **1,255個** ★ 重要発見 |
| **総テスト行数** | 28,063行 |
| **conftest.py 数** | 1個（ルートのみ） |

**注**: 先ほどの「300+ 見積り」が大幅に過小評価だった。実際は **1,255個**。

---

## 📂 ディレクトリ別テスト数（詳細）

### unit/ ディレクトリ（充実）

**総テスト数**: 223+（サブディレクトリ含む）

#### unit/gui/widgets/ ★ 最大カテゴリ
- ファイル数: 14個
- **テスト数: 240個** ← 全体の 19%
- 対象ウィジェット:
  - test_thumbnail_selector_widget.py: 39件
  - test_custom_range_slider.py: 35件
  - test_model_checkbox_widget.py: 23件
  - test_batch_tag_add_widget.py: 21件
  - test_image_preview_widget.py: 21件
  - test_annotation_filter_widget.py: 19件
  - test_rating_score_edit_widget.py: 18件
  - test_error_log_viewer_widget.py: 17件
  - ... 等 14ファイル

#### unit/services/
- ファイル数: 9個
- テスト数: 167個 ← 全体の 13%
- 対象サービス:
  - test_model_filter_service.py: 34件
  - test_search_criteria_processor.py: 32件
  - test_favorite_filters_service.py: 26件
  - test_signal_manager_service.py: 20件
  - test_model_selection_service.py: 16件
  - test_tag_management_service.py: 14件
  - test_selection_state_service.py: 10件
  - test_annotator_library_adapter.py: 10件
  - test_date_formatter.py: 5件

#### unit/gui/services/
- ファイル数: 6個
- テスト数: 98個 ← 全体の 8%
- 対象GUI サービス:
  - test_worker_service.py: 23件
  - test_search_filter_service.py: 20件
  - test_result_handler_service.py: 17件
  - test_image_db_write_service.py: 19件
  - test_pipeline_control_service.py: 9件
  - test_tab_reorganization_service.py: 10件

#### unit/gui/workers/
- ファイル数: 4個
- テスト数: 42個
- 対象ワーカー:
  - test_base_worker.py: 17件
  - test_annotation_worker.py: 12件
  - test_progress_helper.py: 10件
  - test_thumbnail_worker.py: 3件

#### unit/gui/state/
- ファイル数: 2個
- テスト数: 41個
- 対象:
  - test_pagination_state.py: 28件
  - test_dataset_state.py: 13件

#### unit/gui/controllers/
- ファイル数: 3個
- テスト数: 31個
- 対象:
  - test_annotation_workflow_controller.py: 14件
  - test_dataset_controller.py: 11件
  - test_settings_controller.py: 6件

#### unit/storage/
- ファイル数: 2個
- テスト数: 58個
- 対象:
  - test_file_system_manager.py: 37件
  - test_temp_directory_helper.py: 21件

#### unit/gui/window/
- ファイル数: 2個
- テスト数: 30個
- 対象:
  - test_main_window.py: 20件
  - test_configuration_window.py: 10件

#### unit/gui/cache/
- ファイル数: 1個
- テスト数: 21個
- 対象:
  - test_thumbnail_page_cache.py: 21件

#### unit/ トップレベル
- ファイル数: 14個
- テスト数: 223個
- 対象:
  - test_autocrop.py: 38件
  - test_batch_processor.py: 14件
  - test_batch_utils.py: 19件
  - test_configuration_service.py: 21件
  - test_dataset_export_service.py: 15件
  - test_existing_file_reader.py: 12件
  - test_image_processor.py: 19件
  - test_import_lorairo.py: 0件（スキップ等）
  - test_model_info_manager.py: 14件
  - ... 等

---

### integration/ ディレクトリ

**総テスト数**: 92+（トップレベル）+ 105（GUI）+ 8（DB）+ 9（Services）= **214+**

#### integration/ トップレベル
- ファイル数: 11個
- テスト数: 92個
- 対象:
  - test_main_window_tab_integration.py: 17件（最大）
  - test_batch_processing_integration.py: 10件
  - test_gui_configuration_integration.py: 8件
  - test_project_directory_integration.py: 8件
  - test_upscaler_database_integration.py: 8件
  - test_tag_db_integration.py: 7件
  - test_tag_management_integration.py: 7件
  - test_configuration_integration.py: 7件
  - test_database_path_integration.py: 7件
  - test_dataset_export_integration.py: 7件
  - test_ai_rating_filter_integration.py: 6件

#### integration/gui/
- ファイル数: 9個
- テスト数: 105個 ← 全体の 8%（GUI統合の中核）
- 対象:
  - test_filter_search_integration.py: 24件（最大）
  - test_ui_layout_integration.py: 15件
  - test_gui_component_interactions.py: 12件
  - test_worker_coordination.py: 12件
  - test_batch_tag_add_integration.py: 11件
  - test_mainwindow_signal_connection.py: 8件
  - test_thumbnail_details_annotation_integration.py: 7件
  - test_mainwindow_critical_initialization.py: 7件
  - test_widget_integration.py: 9件

#### integration/gui/widgets/
- ファイル数: 1個
- テスト数: 3件
- 対象:
  - test_model_selection_table_widget_critical_initialization.py

#### integration/gui/window/
- ファイル数: 1個
- テスト数: 5件
- 対象:
  - test_main_window_integration.py

#### integration/gui/workers/
- ファイル数: 1個
- テスト数: 8件
- 対象:
  - test_worker_error_recording.py

#### integration/database/
- ファイル数: 1個
- テスト数: 8件
- 対象:
  - test_tag_registration_integration.py

#### integration/services/
- ファイル数: 1個
- テスト数: 9件
- 対象:
  - test_image_db_write_service_batch.py

---

### features/ ディレクトリ（BDD）

**総テスト数**: 0件（.feature ファイルのみ、Python テストではない）
**ファイル数**: 2個（.feature ファイル）

---

### step_defs/ ディレクトリ（BDD ステップ定義）

**総テスト数**: 0件（Python テスト関数なし）
**ファイル数**: 1個
- test_database_management.py: 0件（ステップ定義のみ）

---

## 🎯 テスト分布分析

### カテゴリ別テスト数

| カテゴリ | テスト数 | 比率 | 特徴 |
|---------|---------|------|------|
| **unit/gui/widgets/** | 240 | 19% | 最大（ウィジェット単体） |
| **unit/services/** | 167 | 13% | サービスユニット |
| **integration/** | 92 | 7% | 統合テスト（トップレベル） |
| **integration/gui/** | 105 | 8% | GUI統合 |
| **unit/gui/services/** | 98 | 8% | GUI サービス |
| **unit/storage/** | 58 | 5% | ストレージ関連 |
| **unit/ トップレベル** | 223 | 18% | その他ユニット |
| **その他 (state, controllers, workers, window, cache)** | ~163 | 13% | 残り |
| **BDD (features + step_defs)** | 0 | 0% | .feature ファイルのみ |

---

## 🔍 重要な観察

### 1. ユニットテストが充実
- unit/ ディレクトリが既に多くのテストを含む
- **計画ドキュメント**での「unit/ディレクトリなし」という分析は誤りだった
- GUI ウィジェット、サービス、ワーカーのユニットテストが豊富

### 2. GUI テストが多い
- unit/gui/ 全体: 240 + 98 + 42 + 41 + 31 + 58 + 30 + 21 = **500+ テスト** ← 全体の 40%
- これは PySide6 GUI プロジェクトとして合理的

### 3. 統合テストは補助的
- integration/: 214個 ← 全体の 17%
- unit/ の約 1/3 規模
- **現状は Unit-heavy 戦略**を採用

### 4. BDD テストは未実装
- features/ と step_defs/ は存在するが、実 Python テスト関数なし
- .feature ファイルのみの状態

---

## ✅ 修正事項（Agent 1 分析からの更正）

| 項目 | Agent 1 判定 | 実測 | 修正 |
|------|------|------|------|
| unit/ ディレクトリ | なし | あり | **誤分析** |
| 総テスト数 | 300+ 見積り | 1,255 | 大幅に過小 |
| テストカテゴリの充実度 | integration 中核 | unit が 主力 | パラダイム逆 |
| GUI テスト | integration/gui に統合 | unit/gui が大多数 | 見逃し |

---

## 🎯 Agent 2 への重要情報

**推奨**: Agent 2 の設計を以下に修正
1. **Unit-first 戦略を尊重**（既に実装されている）
2. **conftest.py の肥大化が避けられない理由を理解**
   - GUI テスト（240+98+...）が多いため、フィクスチャが必要
3. **Integration テストは補助的**であることを前提
4. **Multi-layer conftest の優先順位**:
   1. tests/unit/conftest.py（ユニット用）← 最大
   2. tests/gui/conftest.py（GUI用）← 次大
   3. tests/integration/conftest.py（統合用）← 小
   4. tests/bdd/conftest.py（BDD用）← 将来用

---

## 📈 カバレッジ推定（改訂版）

- **ユニットテスト**: ~850 テスト（68%）
- **統合テスト**: ~214 テスト（17%）
- **BDD テスト**: 0 テスト（0%）
- **総計**: ~1,255 テスト

推定カバレッジ: **75-80%** （ユニット+統合で十分か）

---

## 🚀 Next Steps

Agent 2・3・4 の設計・実装では、この**実テスト構造を前提に**計画を修正してください。

特に conftest.py の責務分割は、既存のテスト配置を尊重した設計が必要です。
