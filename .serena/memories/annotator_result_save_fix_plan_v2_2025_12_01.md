# LoRAIro アノテーション結果表示修正計画 v2（アーキテクチャ指摘反映版）

## 前回計画からの修正点

### 修正1: pHashマッピング戦略（再計算 → DB照会）

**問題**: `_build_phash_mapping()`で`calculate_phash(image_path)`を毎回再計算していたが、DBには登録時のpHashが既に保存されている。再計算するとアルゴリズム差異や前処理の違いでライブラリが返すpHashとズレるリスクがある。

**解決策**: `_build_phash_mapping()`メソッドを削除し、`find_duplicate_image_by_phash(phash)`を直接使用してライブラリが返したpHashからimage_idを取得する。

```python
# ❌ 旧計画（再計算）
def _build_phash_mapping(self) -> dict[str, dict[str, Any]]:
    from lorairo.utils.tools import calculate_phash
    for image_path in self.image_paths:
        phash = calculate_phash(image_path)  # 再計算リスク
        image_id = self.db_manager.get_image_id_by_filepath(image_path)
        mapping[phash] = {"image_id": image_id, "image_path": image_path}

# ✅ 新計画（DB照会）
def _save_results_to_database(self, results: PHashAnnotationResults) -> None:
    for phash, model_results in results.items():
        # ライブラリが返したpHashを信頼してDB照会
        image_id = self.db_manager.repository.find_duplicate_image_by_phash(phash)
        if image_id is None:
            logger.warning(f"pHash {phash[:8]}... に対応する画像がDBに見つかりません")
            continue
        # 変換と保存...
```

### 修正2: TypedDict import先（db_repository → schema）

**問題**: `from lorairo.database.db_repository import ScoreAnnotationData, ...`としていたが、これらのTypeDefは`schema.py`に定義されている。repositoryからimportしようとすると循環参照やImportErrorになる。

**解決策**: `schema.py`から正しくimportする。

```python
# ❌ 旧計画（誤ったimport）
from lorairo.database.db_repository import (
    ScoreAnnotationData,
    TagAnnotationData,
    CaptionAnnotationData,
    RatingAnnotationData,
)

# ✅ 新計画（正しいimport）
from lorairo.database.schema import (
    ScoreAnnotationData,
    TagAnnotationData,
    CaptionAnnotationData,
    RatingAnnotationData,
    AnnotationsDict,
)
```

### 修正3: GUI更新メカニズム（キャッシュ再送 → DB再取得）

**問題**: `DatasetStateManager.set_current_image(current_image_id)`を再度呼ぶだけでは、内部キャッシュ`_all_images`から既存メタデータを取り出して`current_image_data_changed`をemitするだけで、DBから再取得しない。DB書き込み後も古いキャッシュが送信され、UIに反映されない。

**解決策**: `db_manager.repository.get_image_metadata(image_id)`でDBから最新データを取得し、直接`current_image_data_changed.emit()`する。

```python
# ❌ 旧計画（キャッシュ再送）
def _on_annotation_finished(self, result: PHashAnnotationResults) -> None:
    self._delegate_to_result_handler(...)
    current_image_id = self.dataset_state_manager.current_image_id
    if current_image_id:
        # set_current_image()は_all_imagesから取得するだけ（DBアクセスなし）
        self.dataset_state_manager.set_current_image(current_image_id)

# ✅ 新計画（DB再取得）
def _on_annotation_finished(self, result: PHashAnnotationResults) -> None:
    self._delegate_to_result_handler(...)
    current_image_id = self.dataset_state_manager.current_image_id
    if current_image_id:
        # DBから最新メタデータを取得
        latest_metadata = self.db_manager.repository.get_image_metadata(current_image_id)
        if latest_metadata:
            # 直接シグナル発行してUI更新
            self.dataset_state_manager.current_image_data_changed.emit(latest_metadata)
            logger.info(f"画像ID {current_image_id} の最新メタデータでGUI更新完了")
```

---

## 修正後の完全な実装計画

### Phase 1: AnnotationWorkerでDB保存実装

**ファイル**: `src/lorairo/gui/workers/annotation_worker.py`

**変更内容**:

1. **execute()メソッドの修正** - DB保存処理を追加（返り値型は`PHashAnnotationResults`のまま）
2. **_save_results_to_database()メソッドの追加** - pHash→image_id変換とDB保存
3. **_convert_to_annotations_dict()メソッドの追加** - PHashAnnotationResults → AnnotationsDict変換
4. **_build_phash_mapping()メソッドは追加しない** - DB照会で直接解決

#### 実装コード

```python
# ファイル: src/lorairo/gui/workers/annotation_worker.py

# import追加
from lorairo.database.schema import (
    ScoreAnnotationData,
    TagAnnotationData,
    CaptionAnnotationData,
    RatingAnnotationData,
    AnnotationsDict,
)


def execute(self) -> PHashAnnotationResults:
    """アノテーション処理実行

    Returns:
        PHashAnnotationResults: アノテーション結果（phash → model_name → UnifiedResult）
    """
    logger.info(f"アノテーション処理開始 - {len(self.image_paths)}画像, {len(self.models)}モデル")

    try:
        # 前処理進捗
        self._report_progress(10, "アノテーション処理を開始...", total_count=len(self.image_paths))
        self._check_cancellation()

        # モデル単位で処理
        merged_results: PHashAnnotationResults = {}
        total_models = len(self.models)

        for model_idx, model_name in enumerate(self.models):
            self._check_cancellation()

            # 進捗報告
            progress = 10 + int((model_idx / total_models) * 70)  # 10-80%
            self._report_progress(
                progress,
                f"AIモデル実行中: {model_name} ({model_idx + 1}/{total_models})",
                processed_count=model_idx,
                total_count=total_models,
            )

            # AnnotationLogic経由でアノテーション実行
            try:
                model_results = self.annotation_logic.execute_annotation(
                    image_paths=self.image_paths,
                    model_names=[model_name],
                )

                # 結果をマージ
                for phash, annotations in model_results.items():
                    if phash not in merged_results:
                        merged_results[phash] = {}
                    merged_results[phash].update(annotations)

                logger.debug(f"モデル {model_name} 完了: {len(model_results)}件の結果")

            except Exception as e:
                logger.error(f"モデル {model_name} でエラー: {e}", exc_info=True)
                # エラーレコード保存（既存コード維持）
                for image_path in self.image_paths:
                    try:
                        image_id = self.db_manager.get_image_id_by_filepath(image_path)
                        self.db_manager.save_error_record(
                            operation_type="annotation",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            image_id=image_id,
                            stack_trace=traceback.format_exc(),
                            file_path=image_path,
                            model_name=model_name,
                        )
                    except Exception as save_error:
                        logger.error(f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}")

        # DB保存進捗
        self._report_progress(85, "結果をデータベースに保存中...", total_count=len(self.image_paths))

        # 結果をDBに保存（新規追加）
        self._save_results_to_database(merged_results)

        # 完了進捗
        self._report_progress(
            100,
            "アノテーション処理が完了しました",
            processed_count=len(self.image_paths),
            total_count=len(self.image_paths),
        )

        logger.info(f"アノテーション処理完了: {len(merged_results)}件の結果")
        return merged_results  # 返り値の型は変更しない

    except Exception as e:
        logger.error(f"アノテーション処理エラー: {e}", exc_info=True)
        # エラーレコード保存（既存コード維持）
        for image_path in self.image_paths:
            try:
                image_id = self.db_manager.get_image_id_by_filepath(image_path)
                self.db_manager.save_error_record(
                    operation_type="annotation",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    image_id=image_id,
                    stack_trace=traceback.format_exc(),
                    file_path=image_path,
                    model_name=None,
                )
            except Exception as save_error:
                logger.error(f"エラーレコード保存失敗（二次エラー）: {image_path}, {save_error}")
        raise


def _save_results_to_database(
    self,
    results: PHashAnnotationResults,
) -> None:
    """アノテーション結果をDBに保存

    Args:
        results: PHashAnnotationResults（phash → model_name → UnifiedResult）

    Note:
        find_duplicate_image_by_phash()を使用してpHash→image_id変換を行う。
        ライブラリが返したpHashを信頼し、DB側の保存済みpHashと照合する。
    """
    saved_count = 0

    for phash, model_results in results.items():
        try:
            # pHash → image_id変換（DB照会）
            image_id = self.db_manager.repository.find_duplicate_image_by_phash(phash)

            if image_id is None:
                logger.warning(f"pHash {phash[:8]}... に対応する画像がDBに見つかりません。スキップします。")
                continue

            # PHashAnnotationResults → AnnotationsDict 変換
            annotations = self._convert_to_annotations_dict(model_results)

            if not annotations or not any(annotations.values()):
                logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
                continue

            # DB保存（ImageDBWriteServiceと同じパターン）
            self.db_manager.repository.save_annotations(
                image_id=image_id,
                annotations=annotations,
            )

            saved_count += 1
            logger.info(f"画像ID {image_id} のアノテーション保存成功")

        except Exception as e:
            logger.error(f"pHash {phash[:8]}... の保存失敗: {e}", exc_info=True)
            # 保存失敗しても次の画像に進む（部分的成功を許容）

    logger.info(f"アノテーション保存完了: {saved_count}/{len(results)}件成功")


def _convert_to_annotations_dict(
    self,
    model_results: dict[str, Any],  # model_name → UnifiedResult
) -> AnnotationsDict:
    """PHashAnnotationResultsの1画像分をAnnotationsDictに変換

    Args:
        model_results: {
            "aesthetic_scorer_v2": UnifiedResult(
                model_name="aesthetic_scorer_v2",
                capabilities={"SCORES"},
                scores={"aesthetic": 0.85, "quality": 0.92},
                tags=None,
                captions=None,
                ratings=None,
                error=None
            ),
            ...
        }

    Returns:
        AnnotationsDict: {
            "scores": [ScoreAnnotationData, ...],
            "tags": [TagAnnotationData, ...],
            "captions": [CaptionAnnotationData, ...],
            "ratings": [RatingAnnotationData, ...],
        }
    """
    annotations: AnnotationsDict = {
        "scores": [],
        "tags": [],
        "captions": [],
        "ratings": [],
    }

    for model_name, unified_result in model_results.items():
        try:
            # エラーがある場合はスキップ
            if unified_result.error:
                logger.warning(f"モデル {model_name} のエラーをスキップ: {unified_result.error}")
                continue

            # model_name → model_id変換（公開API使用）
            model = self.db_manager.repository.get_model_by_name(model_name)
            if model is None:
                logger.warning(f"モデル '{model_name}' がデータベースに存在しません。スキップします。")
                continue
            model_id = model.id

            # Scores処理
            if unified_result.scores:
                for score_name, score_value in unified_result.scores.items():
                    score_data: ScoreAnnotationData = {
                        "model_id": model_id,
                        "score": float(score_value),
                        "is_edited_manually": False,
                    }
                    annotations["scores"].append(score_data)

            # Tags処理
            if unified_result.tags:
                for tag_content in unified_result.tags:
                    tag_data: TagAnnotationData = {
                        "model_id": model_id,
                        "tag": tag_content,  # ← 正しいキー名（schema.py準拠）
                        "existing": False,
                        "is_edited_manually": False,
                        "confidence_score": None,
                        "tag_id": None,
                    }
                    annotations["tags"].append(tag_data)

            # Captions処理
            if unified_result.captions:
                for caption_content in unified_result.captions:
                    caption_data: CaptionAnnotationData = {
                        "model_id": model_id,
                        "caption": caption_content,  # ← 正しいキー名（schema.py準拠）
                        "existing": False,
                        "is_edited_manually": False,
                    }
                    annotations["captions"].append(caption_data)

            # Ratings処理
            if unified_result.ratings:
                rating_value = str(unified_result.ratings)
                rating_data: RatingAnnotationData = {
                    "model_id": model_id,
                    "raw_rating_value": rating_value,  # ← 正しいキー名（schema.py準拠）
                    "normalized_rating": rating_value,  # ← 正しいキー名（schema.py準拠）
                    "confidence_score": None,
                }
                annotations["ratings"].append(rating_data)

        except Exception as e:
            logger.error(f"モデル {model_name} の変換エラー: {e}", exc_info=True)
            # 変換エラーでも次のモデルに進む

    return annotations
```

### Phase 2: MainWindowでGUI更新

**ファイル**: `src/lorairo/gui/window/main_window.py`

**変更内容**: `_on_annotation_finished()`メソッドでDBから最新メタデータを取得してGUI更新

#### 実装コード

```python
def _on_annotation_finished(self, result: PHashAnnotationResults) -> None:
    """アノテーション完了ハンドラ

    Args:
        result: PHashAnnotationResults（phash → model_name → UnifiedResult）
    """
    # 既存の通知処理（ResultHandlerService経由）
    self._delegate_to_result_handler(
        "handle_annotation_finished",
        result,
        status_bar=self.statusBar()
    )

    # GUI更新: DBから最新メタデータを取得して直接シグナル発行
    current_image_id = self.dataset_state_manager.current_image_id

    if current_image_id:
        try:
            # DBから最新メタデータを取得
            latest_metadata = self.db_manager.repository.get_image_metadata(current_image_id)

            if latest_metadata:
                # 直接シグナル発行してUI更新（キャッシュバイパス）
                self.dataset_state_manager.current_image_data_changed.emit(latest_metadata)
                logger.info(f"画像ID {current_image_id} の最新メタデータでGUI更新完了")
            else:
                logger.warning(f"画像ID {current_image_id} のメタデータがDBに見つかりません")

        except Exception as e:
            logger.error(f"GUI更新時のメタデータ取得エラー: {e}", exc_info=True)
```

---

## データフロー詳細

### 1. pHash → image_id 変換フロー

```
image-annotator-lib
    ↓ 返却: PHashAnnotationResults (phash → model_name → UnifiedResult)
AnnotationWorker._save_results_to_database()
    ↓ phash を抽出
find_duplicate_image_by_phash(phash)
    ↓ DB照会: SELECT id FROM images WHERE phash = ?
image_id取得
    ↓
save_annotations(image_id, annotations)
```

**メリット**:
- ライブラリが返したpHashを信頼（再計算リスクなし）
- DB側の保存済みpHashと照合（アルゴリズム一貫性保証）
- シンプルで効率的（N+1なし）

### 2. GUI更新フロー

```
AnnotationWorker.execute() 完了
    ↓ finished シグナル発行
MainWindow._on_annotation_finished()
    ↓ current_image_id取得
db_manager.repository.get_image_metadata(current_image_id)
    ↓ DB照会: SELECT * FROM images WHERE id = ?
latest_metadata取得
    ↓
dataset_state_manager.current_image_data_changed.emit(latest_metadata)
    ↓
SelectedImageDetailsWidget._on_current_image_data_changed()
    ↓
スコア表示更新
```

**メリット**:
- DBから最新データを直接取得（キャッシュ問題回避）
- 既存のシグナル/スロット仕組みを活用
- DatasetStateManagerの内部状態を変更しない（副作用なし）

---

## 成功基準

1. ✅ アノテーション実行時、結果がDBに保存される
2. ✅ 保存された結果がGUIに正しく表示される（最新データ）
3. ✅ エラー発生時も部分的成功を許容（他のモデルの結果は保存）
4. ✅ LoRAIroWorkerBaseとの互換性を維持（返り値の型は不変）
5. ✅ TypedDict定義に準拠（schema.pyから正しくimport、正しいキー名使用）
6. ✅ 層分離ポリシー準拠（公開API使用、private method非依存）
7. ✅ pHash再計算リスク回避（DB照会で解決）
8. ✅ GUIキャッシュ問題回避（DBから直接取得）
9. ✅ 既存アーキテクチャを壊さない

---

## テスト戦略

### Unit Tests

1. **`AnnotationWorker._convert_to_annotations_dict()`**:
   - 正常系: scores, tags, captions, ratingsの変換
   - 異常系: model不一致、エラー結果含む
   - TypedDict構造の検証（schema.py準拠）

2. **`AnnotationWorker._save_results_to_database()`**:
   - モック使用: `find_duplicate_image_by_phash()`, `save_annotations()`
   - pHash不一致時の挙動（スキップ）
   - 保存成功/失敗のシナリオ
   - 部分的成功の確認

3. **`MainWindow._on_annotation_finished()`**:
   - モック使用: `get_image_metadata()`, `current_image_data_changed.emit()`
   - DBから最新データ取得の確認
   - シグナル発行の確認

### Integration Tests

1. アノテーション実行 → DB保存 → GUI表示の完全フロー
2. 部分的失敗時の動作確認（一部モデルのみ成功）
3. pHash不一致時の挙動（該当画像スキップ）
4. 複数画像同時アノテーション時のDB整合性

---

## 制約事項

- image-annotator-lib の修正は行わない（別タスク）
- ResultHandlerServiceにDB依存を追加しない（通知のみ維持）
- ImageDBWriteServiceは手動編集専用のまま維持
- DatasetStateManagerの内部状態を変更しない（キャッシュ更新なし）
- 最小限の変更で対処
