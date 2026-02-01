# Session: N+1クエリ問題の解消とSQLiteバインド変数チャンク化

**Date**: 2026-01-30
**Branch**: feature/annotator-library-integration
**Commit**: 68e2387
**Status**: completed

---

## 実装結果

### Repository層（db_repository.py）: 4メソッド追加 + チャンク化
- `get_images_metadata_batch()`: image_ids一括取得、既存`_fetch_filtered_metadata()`をラップ
- `get_annotated_image_ids()`: EXISTS+OR(Tag,Caption)サブクエリで一括チェック
- `find_image_ids_by_phashes()`: pHash→image_id マッピング一括取得
- `get_models_by_names()`: モデル名→Modelオブジェクト一括取得（selectinload付き）
- `BATCH_CHUNK_SIZE = 15000`: SQLiteバインド変数上限（32,766）への安全マージン
- 3メソッド（get_images_metadata_batch, get_annotated_image_ids, find_image_ids_by_phashes）にチャンク分割実装

### db_manager.py: 委譲メソッド追加
- `get_annotated_image_ids()` → SearchCriteriaProcessorからアクセス用

### 呼び出し元書き換え
- `dataset_state.py`: `refresh_images()` N個SELECT → 1回バッチ取得
- `search_criteria_processor.py`: `filter_images_by_annotation_status()` N回個別チェック → 1回set取得
- `annotation_worker.py`: `_save_results_to_database()` pHash/モデルのN+M回 → 2回バッチ取得

### Quick Tag選択制限（thumbnail.py）
- `quick_tag_requested` emit前に `thumbnail_items`（表示中サムネイル）のIDのみにフィルタリング

## テスト結果

- test_db_repository_batch_queries.py: 15テスト PASSED（チャンク化テスト3件含む）
- test_dataset_state.py: 13テスト PASSED（バッチクエリ検証3件追加）
- test_search_criteria_processor.py: 30テスト PASSED（モック変更）
- test_annotation_worker.py: 環境問題で実行不可（image_annotator_libインポートハング、既存問題）
- 合計: 58/58テスト PASSED

## 設計意図

### バッチクエリ設計
- 既存の`_fetch_filtered_metadata()`を再利用し、joinedloadによるN+1防止済みの基盤を活用
- Repository Patternに従い、全バッチメソッドをdb_repository.pyに集約
- 後方互換性維持: 既存の単体メソッド（refresh_image, check_image_has_annotation等）は削除せず存続

### チャンク化設計
- SQLite 3.32.0以降のデフォルト上限32,766に対し、BATCH_CHUNK_SIZE=15,000で約46%マージン確保
- 旧SQLite（3.31以前）のデフォルト999には非対応（必要時にBATCH_CHUNK_SIZEを900に変更で対応可能）
- チャンク化対象: IN句でバインド変数数=要素数となる3メソッド
- get_models_by_namesは対象外（モデル数は数十程度で上限到達の可能性なし）

### Quick Tag選択制限
- UIレベルでCtrl+A選択を表示中サムネイルに制限（チャンク化との多層防御）

## 問題と解決

### SQLiteバインド変数上限の発見
- 初回分析では「チャンク化不要」と判断 → ユーザー指摘で再調査
- Quick TagのCtrl+A、検索結果のLIMIT無し、アノテーションワークフローのバッチ無制限を発見
- 教訓: UIの上限制約を過信せず、DB層で安全策を講じる

### make test の全体実行問題
- `make test`がプロジェクト全体を対象にし、既存のtest collection errorで停止
- 直接venv python経由でpytest実行することで回避

## 未完了・次のステップ
- annotation_worker テストの実行確認（image_annotator_lib環境問題の解消後）
- mypy型チェック確認（同上の環境問題）
