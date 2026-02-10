# Test Mapping Analysis - 2026-02-08

## 調査概要
変更ファイル2つの機能（バッチRating/Score更新 + スコアフィルター修正）について、既存テストとの対応関係と、テスト追加・修正が必要な箇所を調査。

---

## 機能1: バッチRating/Score更新

### 変更ファイル
- `src/lorairo/database/db_repository.py` - `update_rating_batch()`, `update_score_batch()` 追加
- `src/lorairo/gui/services/image_db_write_service.py` - バッチメソッド追加
- `src/lorairo/gui/widgets/rating_score_edit_widget.py` - `populate_from_selection()` 追加（バッチモード対応）
- `src/lorairo/gui/widgets/selected_image_details_widget.py` - バッチシグナル転送（`batch_rating_changed`, `batch_score_changed`）
- `src/lorairo/gui/window/main_window.py` - バッチハンドラー4つ追加

### 既存テスト状況

**既存テストファイル：**
- ✅ `tests/unit/gui/widgets/test_rating_score_edit_widget.py` (142行)
  - テスト対象: 単一選択モードのUI値/DB値変換、スライダー更新、保存シグナル
  - **問題**: バッチモード用テストなし（`populate_from_selection()` 未テスト）

- ✅ `tests/unit/gui/window/test_main_window.py` (136行)
  - テスト対象: `_setup_image_db_write_service()` のシグナル接続
  - **問題**: バッチハンドラー4つ（`_handle_batch_rating_changed`, `_handle_batch_score_changed`, `_execute_batch_rating_write`, `_execute_batch_score_write`）が未テスト

**新規テストファイル（作成済み）：**
- ✅ `tests/unit/database/test_db_repository_batch_rating_score.py` - リポジトリレイヤーのバッチメソッドテスト
- ✅ `tests/integration/services/test_image_db_write_service_batch.py` - サービスレイヤーのバッチメソッドテスト

### テスト追加が必要な箇所

1. **`test_rating_score_edit_widget.py` に追加必要**:
   - `test_populate_from_selection_common_rating()` - 全画像が同じRating時の表示
   - `test_populate_from_selection_different_ratings()` - 異なるRating時のプレースホルダー表示
   - `test_populate_from_selection_common_score()` - 全画像が同じScore時の表示
   - `test_populate_from_selection_different_scores()` - 異なるScore時の表示
   - `test_batch_mode_signals()` - `batch_rating_changed`, `batch_score_changed` シグナル発行の検証

2. **`test_main_window.py` に追加必要**:
   - `test_handle_batch_rating_changed()` - バッチRating変更ハンドラー
   - `test_handle_batch_score_changed()` - バッチScore変更ハンドラー
   - `test_execute_batch_rating_write()` - バッチRating書き込み実行
   - `test_execute_batch_score_write()` - バッチScore書き込み実行
   - `test_batch_update_refreshes_dataset_state()` - キャッシュ更新確認

---

## 機能2: スコアフィルター検索バグ修正

### 変更ファイル
- `src/lorairo/database/db_repository.py` - `_apply_score_filter()` の値変換バグ修正
  - **修正内容**: DB値（0.0-10.0）で直接比較するように修正（以前は不正な値変換）
  
- `src/lorairo/gui/widgets/filter_search_panel.py` - `_get_score_filter_values()` 追加
  - **新機能**: 全範囲（0-1000）時にNone返す（スコアレコードがない画像を除外しない）

### 既存テスト状況

**既存テストファイル：**
- ✅ `tests/unit/database/test_db_repository_score_filter.py` (188行)
  - テスト対象: `_apply_score_filter()` の min/max フィルタ適用検証
  - **状況**: 修正後のDB値直接比較に対応済み（テスト修正不要）
  - クエリ生成テストのみで、実際の値比較はモックで確認

- ✅ `tests/integration/gui/test_filter_search_integration.py` (249行+)
  - テスト対象: FilterSearchPanel全体の統合テスト
  - **問題**: `_get_score_filter_values()` の全範囲判定テストなし

### テスト追加が必要な箇所

1. **`test_filter_search_integration.py` に追加必要**:
   - `test_score_filter_full_range_returns_none()` - スコア全範囲時にNone返す確認
   - `test_score_filter_partial_range_returns_values()` - 範囲指定時に正しい値返す確認
   - `test_score_filter_min_only()` - 最小値のみ指定時の値変換
   - `test_score_filter_max_only()` - 最大値のみ指定時の値変換

2. **`test_db_repository_score_filter.py` に追加可能（オプション）**:
   - 実DB統合テストで値変換の正確性を検証
   - 現在のモックテストから一歩進んだテスト

---

## 影響範囲サマリー

### リポジトリレイヤー: ✅ テスト完備
- `update_rating_batch()`, `update_score_batch()` - 作成済みテストでカバー
- `_apply_score_filter()` - 既存テスト対応完了

### サービスレイヤー: ✅ テスト完備
- `ImageDBWriteService.update_rating_batch()`, `update_score_batch()` - 作成済みテストでカバー

### GUI層（ウィジェット）: ⚠️ テスト不完全
- `RatingScoreEditWidget.populate_from_selection()` - **テスト追加必要**
- `RatingScoreEditWidget` バッチシグナル発行 - **テスト追加必要**
- `FilterSearchPanel._get_score_filter_values()` - **テスト追加必要**

### GUI層（ウィンドウ）: ⚠️ テスト不完全
- `MainWindow` バッチハンドラー4つ - **テスト追加必要**

---

## テスト追加優先度

**高優先度**（バッチ処理の核心）:
1. `test_rating_score_edit_widget.py` - `populate_from_selection()` テスト 5個
2. `test_main_window.py` - バッチハンドラーテスト 5個

**中優先度**（検索機能の安定性）:
3. `test_filter_search_integration.py` - スコアフィルター値変換テスト 4個

---

## 全体カバレッジ予測

**現状**: テストファイルは存在するが、バッチ機能テストは大幅に不足
**追加後**: 上記テスト追加により、バッチRating/Score更新は75%+ カバレッジ達成見込み
