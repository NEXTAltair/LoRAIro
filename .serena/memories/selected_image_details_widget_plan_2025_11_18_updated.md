# SelectedImageDetailsWidget メタデータ表示問題の修正計画（検証完了版）

**作成日**: 2025-11-18
**最終更新**: 2025-11-18 検証完了
**ステータス**: 問題確定、修正準備完了
**優先度**: 高

---

## 📌 問題の確定（検証完了）

### ✅ 検証結果: データ構造の不一致

**Repository層の実装** (`db_repository.py:1246`):
```python
metadata.update(self._format_annotations_for_metadata(img))
# 戻り値を metadata に直接追加
```

**Repository層が返すデータ構造**:
```python
metadata = {
    "id": 123,
    "stored_image_path": "...",
    "tags": [...],          # ← 直接キー（ネストなし）
    "tags_text": "...",
    "captions": [...],
    "caption_text": "...",
    "scores": [...],
    "score_value": ...,
    "ratings": [...],
    "rating_value": ...
}
```

**Widget層の期待** (`selected_image_details_widget.py:374`):
```python
annotations = metadata.get("annotations", {})  # ← "annotations" キーを期待
tags_list = annotations.get("tags", [])        # ← ネストを期待
```

### 🎯 問題の本質

**不一致**:
- Widget層: `metadata["annotations"]["tags"]` にアクセス
- Repository層: `metadata["tags"]` を提供（ネストなし）

**結果**:
- `metadata.get("annotations", {})` は空の辞書 `{}` を返す
- `annotations.get("tags", [])` は空のリスト `[]` を返す
- Widget には何も表示されない

---

## 📋 修正計画

### Phase 1: Widget層の修正（1ファイル、1箇所のみ）

**対象ファイル**: `src/lorairo/gui/widgets/selected_image_details_widget.py`
**修正箇所**: L374-390
**作業時間**: 5分

**修正内容**:

```python
# ========== 修正前（L374-390） ==========
# アノテーション情報（Repository層で変換済み）
annotations = metadata.get("annotations", {})

# Repository層で変換済みのlist[dict]をそのまま使用
tags_list = annotations.get("tags", [])

# caption: Repository層で提供される caption_text を使用
caption_text = annotations.get("caption_text", "")

# tags_text: Repository層で提供される tags_text を使用
tags_text = annotations.get("tags_text", "")

annotation_data = AnnotationData(
    tags=tags_list,  # ← list[dict] をそのまま渡す
    caption=caption_text,
    aesthetic_score=annotations.get("score_value"),
    overall_score=int(annotations.get("rating_value", 0)),
)

# ========== 修正後 ==========
# Repository層のデータ構造に合わせて直接アクセス
tags_list = metadata.get("tags", [])
caption_text = metadata.get("caption_text", "")
tags_text = metadata.get("tags_text", "")

annotation_data = AnnotationData(
    tags=tags_list,
    caption=caption_text,
    aesthetic_score=metadata.get("score_value"),
    overall_score=int(metadata.get("rating_value", 0)),
)
```

**変更点**:
1. `annotations = metadata.get("annotations", {})` の行を削除
2. 全ての `annotations.get()` を `metadata.get()` に変更

**影響範囲**: 1ファイル、10行程度の修正

---

### Phase 2: テスト検証

#### 単体テスト
```bash
uv run pytest tests/unit/gui/widgets/test_selected_image_details_widget.py -xvs
```

#### 統合テスト
```bash
uv run pytest tests/integration/gui/test_mainwindow_signal_connection.py -xvs
```

#### 手動確認
1. GUI起動: `uv run lorairo`
2. 検索実行: tags=['box']
3. 画像選択
4. SelectedImageDetailsWidget でメタデータ表示確認
   - タグテーブルにデータが表示される
   - キャプションが表示される
   - スコア/レーティングが表示される

---

## ✅ 完了基準

- [ ] **Phase 1完了**: selected_image_details_widget.py 修正完了
- [ ] **単体テスト**: 全合格
- [ ] **統合テスト**: 全合格
- [ ] **手動確認**: GUI でメタデータが正しく表示される

---

## 📝 関連情報

### 関連ファイル
- `src/lorairo/database/db_repository.py:1100-1200` - `_format_annotations_for_metadata()`
- `src/lorairo/database/db_repository.py:1246` - metadata.update()
- `src/lorairo/gui/widgets/selected_image_details_widget.py:374-390` - 修正対象箇所

### 関連メモリー
- `selected_image_details_widget_plan_2025_11_17.md` - Phase 1-3 実装完了記録
- `ui_metadata_display_issue_2025_11_17.md` - 初期問題診断

---

**作成日**: 2025-11-18
**最終更新**: 2025-11-18 検証完了
**ステータス**: 修正準備完了
