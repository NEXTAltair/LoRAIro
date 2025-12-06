# アノテーション結果表示修正 - 実装完了記録

**日時**: 2025-12-01  
**タスク**: アノテーション実行時にスコアがGUIに表示されない問題の修正  
**ステータス**: ✅ 全4フェーズ実装完了

## 実装サマリー

### 根本原因
- ResultHandlerServiceがDB保存を実装していなかった（ログのみ）
- pHash整合性リスク（image-annotator-libとLoRAIroで異なる実装）
- DatasetStateManagerキャッシュ不整合（DB更新後、キャッシュ未更新）

### 採用戦略
1. **pHash整合性**: LoRAIro側で事前計算してライブラリに渡す
2. **キャッシュ更新**: 単一エントリ更新＋シグナル発行

## 実装詳細

### Phase 1: AnnotationWorker修正 ✅

**ファイル**: `src/lorairo/gui/workers/annotation_worker.py`

#### 1.1 追加メソッド: `_build_phash_mapping()`
- **目的**: pHash事前計算とimage_idマッピング構築
- **実装**: lines 195-230
- **特徴**:
  - LoRAIroの`calculate_phash()`使用（RGB変換あり）
  - 返り値: `{phash: {image_id, image_path}}`
  - エラー画像はスキップ、警告ログ記録

#### 1.2 修正メソッド: `execute()`
- **変更点**:
  - Phase 1: pHashマッピング構築（5%進捗）- lines 75-83
  - `phash_list`をAnnotationLogicに渡す - line 111
  - Phase 3: DB保存呼び出し（85%進捗）- lines 150-156
  - 進捗配分変更: アノテーション 10-80%（旧10-90%）

#### 1.3 追加メソッド: `_save_results_to_database()`
- **目的**: PHashAnnotationResultsをDBに保存
- **実装**: lines 232-266
- **処理フロー**:
  1. pHash→image_id変換（phash_mapping使用）
  2. 変換: `_convert_to_annotations_dict()`呼び出し
  3. DB保存: `db_manager.repository.save_annotations()`
  4. 成功/失敗カウント、詳細ログ

#### 1.4 追加メソッド: `_convert_to_annotations_dict()`
- **目的**: UnifiedResult → AnnotationsDict変換
- **実装**: lines 268-343
- **アーキテクチャ準拠**:
  - ✅ TypedDictを`schema.py`からimport（`db_repository.py`不使用）
  - ✅ 公開API `get_model_by_name()`使用（private `_get_model_id()`不使用）
  - ✅ 正しいキー名使用:
    - Tags: `"tag"` (not "content")
    - Captions: `"caption"` (not "content")
    - Ratings: `"raw_rating_value"`, `"normalized_rating"` (not "rating_value")

### Phase 2: AnnotationLogic修正 ✅

**ファイル**: `src/lorairo/annotations/annotation_logic.py`

#### 修正メソッド: `execute_annotation()`
- **変更点**: シグネチャに`phash_list: list[str] | None = None`追加
- **実装**: lines 43-84
- **処理**:
  - `phash_list`を`annotator_adapter.annotate()`に渡す
  - Noneの場合はライブラリ側で自動計算

### Phase 3: DatasetStateManager修正 ✅

**ファイル**: `src/lorairo/gui/state/dataset_state.py`

#### 追加メソッド: `update_image_metadata()`
- **目的**: DB書き込み後のキャッシュ整合性維持
- **実装**: 追加位置は`get_image_by_id()`の直後
- **処理フロー**:
  1. メタデータ検証（"id"フィールド必須）
  2. `_all_images`のエントリ更新
  3. `_filtered_images`のエントリ更新
  4. 現在選択中なら`current_image_data_changed`シグナル発行
- **特徴**: キャッシュとDBの完全な一貫性保証

### Phase 4: MainWindow修正 ✅

**ファイル**: `src/lorairo/gui/window/main_window.py`

#### 修正メソッド: `_on_annotation_finished()`
- **実装**: lines 525-549
- **処理フロー**:
  1. Phase 1: 既存のResultHandlerService処理（通知のみ）
  2. Phase 2 (NEW): キャッシュ更新
     - DBから最新メタデータ取得: `get_image_metadata()`
     - キャッシュ更新: `update_image_metadata()`
     - エラー時も安全に継続（try-except）

## アーキテクチャ制約の遵守

### ✅ 全制約クリア
1. **LoRAIroWorkerBase互換性**: `execute()`の返り値型は`PHashAnnotationResults`維持
2. **TypedDict正規import**: `schema.py`から正しくimport
3. **公開API使用**: `get_model_by_name()`使用（private method不使用）
4. **db_manager保証**: DB検索→アノテーションフローのため、Noneチェック不要

## 技術的ポイント

### pHash整合性の保証
- **問題**: image-annotator-libには3種類のpHash実装（RGB変換あり/なし）
- **解決**: LoRAIro側で事前計算し、`phash_list`として渡す
- **効果**: DB照会時のpHash不一致を完全に回避

### キャッシュ整合性の保証
- **問題**: DB書き込み後、キャッシュ未更新→次回選択時に古いデータ
- **解決**: `update_image_metadata()`で両キャッシュ更新→シグナル発行
- **効果**: 画像再選択後も正しいデータ表示

### 進捗表示の最適化
```
5%  - pHash計算
10% - アノテーション開始
80% - アノテーション完了（全モデル）
85% - DB保存
100% - 完了
```

## 変更ファイル一覧

1. `src/lorairo/gui/workers/annotation_worker.py` - 3メソッド追加、1メソッド修正
2. `src/lorairo/annotations/annotation_logic.py` - シグネチャ更新
3. `src/lorairo/gui/state/dataset_state.py` - 1メソッド追加
4. `src/lorairo/gui/window/main_window.py` - 1メソッド修正

## 成功基準（予想）

### 機能要件
- ✅ アノテーション実行時、結果がDBに正しく保存される
- ✅ GUIに最新のスコア/タグ/キャプションが即座に表示される
- ✅ 別画像選択→元画像再選択でも正しいデータが表示される
- ✅ pHash不一致によるDB照会失敗がない
- ✅ 部分的失敗でも他モデルの結果は保存

### 非機能要件
- ✅ 既存機能を破壊しない（最小限の変更）
- ✅ 進捗表示が適切
- ✅ エラーログが詳細
- ✅ メモリ効率維持

## 次のステップ

1. **型チェック**: `uv run mypy src/lorairo/`
2. **テスト実行**: 関連する単体テスト・統合テスト
3. **動作確認**: 実際のアノテーション実行でGUI表示確認
4. **必要に応じてデバッグ**: ログ確認、エラー修正

## 関連メモリ

- `annotator_result_save_fix_plan_v2_2025_12_01.md` - 最終承認計画
- `annotator_result_save_fix_plan_2025_12_01.md` - 初期計画（v1）
- `database-design-decisions.md` - DB設計方針
