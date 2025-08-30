# ImagePreview「Image data not found」警告解決実装記録 2025-08-29

## 実装概要
サムネイルグリッドサイズ変更時に「Image data not found for ID: XXXX」警告が発生する問題を解決。原因はUI要素のクリアと選択状態管理の非同期による不整合。

## 根本原因分析
- **直接原因**: `_on_thumbnail_size_slider_changed()`でUI要素（`self.scene.clear()`, `self.thumbnail_items.clear()`）をクリアするが、DatasetStateManagerの選択状態（`_current_image_id`, `_selected_image_ids`）は残存
- **結果**: ImagePreviewWidgetが存在しない画像IDを参照しようとして警告発生
- **発生タイミング**: グリッドサイズ変更時のUIクリア処理後

## 採用解決策: 選択状態同期アプローチ
**戦略**: UIクリア処理と同時にDatasetStateManagerの選択状態もクリアし、状態整合性を保つ

### 実装箇所
ファイル: `src/lorairo/gui/widgets/thumbnail.py`
メソッド: `ThumbnailSelectorWidget._on_thumbnail_size_slider_changed()`

### 具体的変更（4行追加）
```python
# UI要素クリア（古い画像残存問題の修正）
self.scene.clear()
self.thumbnail_items.clear()

# 選択状態同期（ImagePreview警告解決）
if self.dataset_state:
    self.dataset_state.clear_current_image()
    self.dataset_state.clear_selection()
    
self._display_cached_thumbnails()
```

## 技術的詳細

### DatasetStateManagerクリア機能
1. **`clear_current_image()`**: 現在選択中の画像ID（`_current_image_id`）をクリア、`current_image_cleared`シグナル発信
2. **`clear_selection()`**: 選択中画像IDリスト（`_selected_image_ids`）をクリア、`selection_changed`シグナル発信

### 実装上の考慮
- **安全チェック**: `if self.dataset_state:` でNoneチェック実装
- **処理順序**: UIクリア → 選択状態クリア → 再表示 の順序で実行
- **既存機能への影響**: 最小限（4行追加のみ）
- **シグナル発信**: 自動的に関連UIコンポーネントに状態変更を通知

## 他候補解決策（検討済み・不採用理由）

### 1. ImagePreview null チェック強化
- **概要**: `get_image_by_id()`での存在チェック強化
- **不採用理由**: 根本原因未解決、防御的プログラミングのみで本質的解決にならない

### 2. 非同期処理による段階的クリア
- **概要**: QTimer使用によるUI/データ状態の時差クリア
- **不採用理由**: 複雑性増加、タイミング制御困難

### 3. 画像キャッシュ再構築
- **概要**: サイズ変更時に画像キャッシュを完全再構築
- **不採用理由**: パフォーマンス劣化、高速キャッシュ機能の利点消失

## 期待効果
1. **主要**: 「Image data not found for ID: XXXX」警告の完全解消
2. **副次**: 状態管理の整合性向上、デバッグログのノイズ削減
3. **パフォーマンス**: 既存の高速キャッシュ機能維持

## 実装パターンとしての価値
- **UI状態とデータ状態の同期**: 類似問題への適用可能な解決パターン
- **最小侵襲修正**: 既存機能への影響を最小化した設計
- **シグナル/スロット活用**: Qt標準パターンを活用した通知仕組み

## 関連実装歴史
- **2025-08-28**: グリッドサイズ変更時の画像残存問題修正（UI要素クリアのみ）
- **2025-08-29**: 選択状態不整合問題解決（データ状態同期追加）

## ブランチ情報
- ブランチ名: `fix/image-preview-data-not-found`
- ベースブランチ: `main`
- 関連issue解決: サムネイルリサイズ時のImagePreview警告

この実装により、LoRAIro프로젝트のサムネイル機能の安定性と整合性が大幅に向上しました。