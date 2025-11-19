# SelectedImageDetailsWidget メタデータ表示問題の修正計画

**作成日**: 2025-11-18
**ステータス**: プランニング完了
**優先度**: 高

---

## 📌 問題の本質（ユーザー提供の設計情報）

### 現行設計のデータフロー

```
SearchWorker/ThumbnailWorker (DB検索)
  ↓ image_metadata取得
DatasetStateManager.update_from_search_results()
  ↓ _all_images/_filtered_images にキャッシュ
DatasetStateManager.set_current_image()
  ↓ get_image_by_id() でキャッシュから取得
  ↓ current_image_data_changed.emit(image_data)
SelectedImageDetailsWidget._on_image_data_received()
  ❌ annotations データがない
```

### 問題箇所の特定

**ユーザー指摘**:
> "今回問題になっているのは、そのキャッシュに `annotations` 付きのメタデータが載っていない経路が存在することです。"

**調査結果**:
1. ✅ Repository層: `_format_annotations_for_metadata()` は実装済み（前タスクで修正）
2. ✅ SearchWorker: `db_manager.get_images_by_filter()` を呼び出し
3. ✅ Repository: annotations を含む metadata を返す（L1243, L1272）
4. ✅ ThumbnailWorker: `search_result.image_metadata` をそのまま渡す（L406）
5. ❌ **問題**: キャッシュに annotations が含まれていない

---

## 🔍 根本原因の検証結果

### ✅ 検証完了: Repository層の実装確認

**実装箇所**: `src/lorairo/database/db_repository.py:1246`
```python
metadata.update(self._format_annotations_for_metadata(img))
```

**`_format_annotations_for_metadata()` の戻り値構造（L1115-1200）**:
```python
{
    "tags": [...],        # ← 直接キー（ネストなし）
    "tags_text": "...",
    "captions": [...],
    "caption_text": "...",
    "scores": [...],
    "score_value": ...,
    "ratings": [...],
    "rating_value": ...
}
```

**metadata の最終構造**:
```python
{
    "id": 123,
    "stored_image_path": "...",
    "tags": [...],  # ← metadata.update() で直接追加
    "tags_text": "...",
    "captions": [...],
    ...
}
```

### 📌 重要な発見

1. **`annotations` キーは存在しない**: Repository層は `annotations` というネストされたキーを返していません
2. **直接追加設計**: `tags`, `captions` などのキーが metadata に直接追加されます
3. **Widget層の期待**: `selected_image_details_widget.py` が `metadata.get("annotations", {})` でアクセスしている可能性

### 🎯 修正方針の確定

**問題**: Widget層が `metadata["annotations"]` にアクセスしているが、Repository層は直接キーを追加している

**解決策**: Widget層を修正して、直接キー（`metadata["tags"]`, `metadata["captions"]`）にアクセスする

---

## 🎯 解決策の設計

### アプローチ1: Repository層でannotationsを明示的に含める（選択）

**方針**:
- `_fetch_filtered_metadata()` でannotationsキーが確実に含まれるよう修正
- ログで検証可能にする

**実装内容**:

```python
# src/lorairo/database/db_repository.py:1217-1289
def _fetch_filtered_metadata(
    self, session: Session, image_ids: list[int], resolution: int
) -> list[dict[str, Any]]:
    """フィルタリングされたIDリストに基づき、指定解像度のメタデータを取得します。"""
    from sqlalchemy.orm import joinedload

    final_metadata_list = []
    if not image_ids:
        return []

    if resolution == 0:
        # Original Images - アノテーション情報を含めて取得
        orig_stmt = (
            select(Image)
            .where(Image.id.in_(image_ids))
            .options(
                joinedload(Image.tags).joinedload(Tag.model),
                joinedload(Image.captions).joinedload(Caption.model),
                joinedload(Image.scores).joinedload(Score.model),
                joinedload(Image.ratings),
            )
        )
        orig_results: list[Image] = list(session.execute(orig_stmt).unique().scalars().all())

        # メタデータ構築 - 基本カラム + アノテーション情報
        for img in orig_results:
            metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
            # アノテーション情報を追加
            annotations = self._format_annotations_for_metadata(img)
            
            # 🔍 デバッグログ追加
            logger.debug(
                f"画像ID {img.id}: annotations keys={list(annotations.keys())}, "
                f"tags={len(annotations.get('tags', []))}, "
                f"captions={len(annotations.get('captions', []))}"
            )
            
            metadata.update(annotations)
            
            # ✅ annotationsキーの存在を確認
            if "annotations" not in metadata:
                logger.error(f"画像ID {img.id}: annotationsキーが metadata に含まれていません")
            
            final_metadata_list.append(metadata)
    else:
        # ProcessedImage の場合も同様に annotations を確実に含める
        # （既存コードと同様、省略）
        pass

    return final_metadata_list
```

**メリット**:
- Single Source of Truth（Repository層）で修正完結
- 全ての検索経路で annotations が保証される
- テスト可能

**デメリット**:
- Repository層のロジックが増える

---

### アプローチ2: set_current_image() でon-demandフェッチ（不採用）

**方針**:
- キャッシュに annotations がない場合、その場でDBから取得

**実装内容**:

```python
# src/lorairo/gui/state/dataset_state.py:276-306
def set_current_image(self, image_id: int) -> None:
    """現在の画像IDを設定"""
    if self._current_image_id != image_id:
        self._current_image_id = image_id
        self.current_image_changed.emit(image_id)

        image_data = self.get_image_by_id(image_id)
        if image_data:
            # ✅ annotations がない場合は DB から再取得
            if "annotations" not in image_data or not image_data["annotations"]:
                logger.warning(
                    f"画像ID {image_id}: annotations がキャッシュに含まれていないため、DBから再取得"
                )
                # DBから完全なメタデータを取得
                full_metadata = self._fetch_full_metadata_from_db(image_id)
                if full_metadata:
                    image_data = full_metadata
            
            self.current_image_data_changed.emit(image_data)
            logger.info(f"✅ 画像選択成功: ID {image_id}")
        else:
            self.current_image_data_changed.emit({})
```

**メリット**:
- キャッシュが不完全でも動作する
- 柔軟性が高い

**デメリット**:
- パフォーマンス低下（DB再アクセス）
- キャッシュの意味が薄れる
- 根本解決ではない

---

## 📋 実装計画（アプローチ1を選択）

### Phase 1: 調査・検証（診断強化）

#### Step 1.1: Repository層の戻り値検証
**目的**: `_fetch_filtered_metadata()` が実際にannotationsを返しているか確認

**実施内容**:
```python
# src/lorairo/database/db_repository.py:1243付近
for img in orig_results:
    metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
    annotations = self._format_annotations_for_metadata(img)
    
    # 🔍 デバッグログ
    logger.debug(
        f"📊 Repository: 画像ID {img.id} - "
        f"annotations keys: {list(annotations.keys())}, "
        f"tags: {len(annotations.get('tags', []))}, "
        f"tags_text: {annotations.get('tags_text', 'N/A')}"
    )
    
    metadata.update(annotations)
    final_metadata_list.append(metadata)

# 最終結果確認
logger.info(
    f"📦 Repository戻り値: {len(final_metadata_list)}件 - "
    f"サンプル keys: {list(final_metadata_list[0].keys()) if final_metadata_list else []}"
)
```

#### Step 1.2: DatasetStateManager キャッシュ検証
**目的**: `update_from_search_results()` がannotationsを保持しているか確認

**実施内容**:
```python
# src/lorairo/gui/state/dataset_state.py:188-231
def update_from_search_results(self, search_results: list[dict[str, Any]]) -> None:
    logger.info(f"検索結果によるデータ完全更新: {len(search_results)}件")
    
    # 🔍 入力データ検証
    if search_results:
        sample = search_results[0]
        logger.debug(
            f"📥 入力データサンプル keys: {list(sample.keys())}, "
            f"annotations存在: {'annotations' in sample}"
        )
    
    self._all_images = search_results.copy()
    self._filtered_images = search_results.copy()
    
    # 🔍 キャッシュ後検証
    if self._all_images:
        cached_sample = self._all_images[0]
        logger.debug(
            f"💾 キャッシュ後サンプル keys: {list(cached_sample.keys())}, "
            f"annotations存在: {'annotations' in cached_sample}"
        )
```

#### Step 1.3: set_current_image() 発行データ検証
**目的**: シグナル発行時のデータにannotationsが含まれているか確認

**実施内容**:
```python
# src/lorairo/gui/state/dataset_state.py:276-306
def set_current_image(self, image_id: int) -> None:
    if self._current_image_id != image_id:
        self._current_image_id = image_id
        self.current_image_changed.emit(image_id)

        image_data = self.get_image_by_id(image_id)
        if image_data:
            # 🔍 発行データ検証
            logger.info(
                f"📤 シグナル発行データ: ID {image_id}, "
                f"keys: {list(image_data.keys())}, "
                f"annotations存在: {'annotations' in image_data}, "
                f"annotations内容: {image_data.get('annotations', {}).keys() if 'annotations' in image_data else 'N/A'}"
            )
            
            self.current_image_data_changed.emit(image_data)
```

**期待される結果**:
- Repository: annotations キーが存在
- DatasetStateManager: キャッシュ後も annotations 保持
- set_current_image: 発行データに annotations 含まれる

**失敗時の対応**:
- どの段階で annotations が消失しているかを特定
- その箇所を修正

---

### Phase 2: 修正実装

#### Case A: Repository層で annotations が含まれていない場合

**修正箇所**: `src/lorairo/database/db_repository.py:1100-1167`

**修正内容**:
```python
def _format_annotations_for_metadata(self, image: Image) -> dict[str, Any]:
    """アノテーション情報をUI用に変換
    
    Returns:
        dict: {
            "tags": list[dict],
            "tags_text": str,
            "captions": list[dict],
            "caption_text": str,
            "scores": list[dict],
            "score_value": float,
            "ratings": list[dict],
            "rating_value": int
        }
    """
    annotations: dict[str, Any] = {}

    # Tags
    if image.tags:
        annotations["tags"] = [
            {
                "id": tag.id,
                "tag": tag.tag,
                "model_id": tag.model_id,
                "model_name": tag.model.name if tag.model else "Unknown",
                "source": "Manual" if tag.is_edited_manually else "AI",
                "confidence_score": tag.confidence_score,
                "is_edited_manually": tag.is_edited_manually,
            }
            for tag in image.tags
        ]
        annotations["tags_text"] = ", ".join([tag.tag for tag in image.tags])
    else:
        annotations["tags"] = []
        annotations["tags_text"] = ""

    # Captions, Scores, Ratings も同様
    # （既存実装通り）
    
    # ✅ annotations が空でないことを保証
    if not annotations:
        logger.warning(f"画像ID {image.id}: annotations が空です")
    
    return annotations
```

**重要**: 戻り値が `annotations` キーでネストされていないことを確認
- ❌ `{"annotations": {"tags": [...]}}`
- ✅ `{"tags": [...], "tags_text": "...", ...}`

#### Case B: update_from_search_results() で annotations が消失する場合

**修正箇所**: `src/lorairo/gui/state/dataset_state.py:188-231`

**修正内容**:
```python
def update_from_search_results(self, search_results: list[dict[str, Any]]) -> None:
    logger.info(f"検索結果によるデータ完全更新: {len(search_results)}件")

    # ✅ annotations 保持を確認しながらコピー
    self._all_images = []
    for item in search_results:
        # deep copy で annotations も確実に保持
        import copy
        self._all_images.append(copy.deepcopy(item))
    
    self._filtered_images = copy.deepcopy(self._all_images)
    
    # 検証ログ
    if self._all_images:
        sample = self._all_images[0]
        logger.debug(f"キャッシュ後サンプル: annotations={('annotations' in sample or any(k in sample for k in ['tags', 'captions', 'scores', 'ratings']))}")
```

---

### Phase 3: テスト作成

#### 統合テスト: Repository → DatasetStateManager → Widget

**ファイル**: `tests/integration/gui/test_metadata_with_annotations.py`

**内容**:
```python
def test_search_results_include_annotations(db_manager, qtbot):
    """検索結果にannotationsが含まれることを検証"""
    # 検索実行
    image_metadata, total_count = db_manager.get_images_by_filter(
        tags=["1girl"],
        resolution=0
    )
    
    # 検証
    assert total_count > 0
    assert len(image_metadata) > 0
    
    sample = image_metadata[0]
    assert "tags" in sample or "annotations" in sample
    
    # tags の詳細検証
    if "tags" in sample:
        assert isinstance(sample["tags"], list)
        if sample["tags"]:
            tag_dict = sample["tags"][0]
            assert "tag" in tag_dict
            assert "source" in tag_dict
            assert "model_name" in tag_dict

def test_dataset_state_manager_caches_annotations(db_manager, qtbot):
    """DatasetStateManagerがannotationsをキャッシュすることを検証"""
    state_manager = DatasetStateManager()
    
    # 検索結果取得
    image_metadata, _ = db_manager.get_images_by_filter(tags=["1girl"], resolution=0)
    
    # キャッシュ
    state_manager.update_from_search_results(image_metadata)
    
    # 取得
    cached_data = state_manager.get_image_by_id(image_metadata[0]["id"])
    
    # 検証
    assert cached_data is not None
    assert "tags" in cached_data or "annotations" in cached_data
```

---

## ✅ 完了基準

- [ ] **Phase 1完了**: 診断ログでannotationsの有無を確認
- [ ] **根本原因特定**: どの段階でannotationsが消失しているか判明
- [ ] **Phase 2完了**: 修正実装完了
- [ ] **Phase 3完了**: 統合テスト全合格
- [ ] **実機確認**: 画像選択時にメタデータが正しく表示される

---

## 📝 次アクション

1. `/implement` 実行でPhase 1診断開始
2. ログ出力結果から根本原因を特定
3. Phase 2修正実装
4. Phase 3テスト作成・検証

---

**作成日**: 2025-11-18
**最終更新**: 2025-11-18
**ステータス**: プランニング完了
