# 📋 実装計画: サムネイルウィジェットの責任分離修正（簡素化版）

**タスク**: ThumbnailSelectorWidgetの責任分離違反とアーキテクチャ問題の修正
**日付**: 2025-08-01
**ブランチ**: `fix/thumbnail-widget-responsibility-separation`
**ステータス**: 簡素化されたアプローチで実装準備完了

---

## 🎯 問題の定義

### 核心的な問題

`AnnotationCoordinator`が `AnnotationStatusFilterWidget.filter_changed`シグナルを `ThumbnailSelectorWidget.apply_annotation_filters()`メソッドに接続しようとしているが：

1. **メソッドが存在しない** → `AttributeError`が発生
2. **責任分離に違反** → UIウィジェットがデータフィルタリングロジックを持つべきではない

### エラーの詳細

```
AttributeError: 'ThumbnailSelectorWidget' object has no attribute 'apply_annotation_filters'
ファイル: src/lorairo/gui/widgets/annotation_coordinator.py:147行目
```

### 📌 重要な設計理解の修正

**データベースフィルタリング vs 表示フィルタリング**:

- 🔍 **FilterSearchPanel** (`filter.py`) → データベース画像の包括的フィルタリング（タグ、解像度、日付等）
- 📊 **AnnotationStatusFilterWidget** → 既に表示されている結果の**表示レベルフィルタリング**
- 🖼️ **ThumbnailSelectorWidget** → 表示のみ

**つまり**: データベースクエリは不要！メモリ内の表示データをフィルタリングするだけ。

---

## ✅ 成功基準

1. **アーキテクチャ**: 責任分離の徹底（表示 ≠ データ処理）
2. **機能性**: 統合テストが `AttributeError`なしで通る
3. **パフォーマンス**: サムネイル表示性能の劣化なし
4. **互換性**: 既存のサムネイル選択機能が変更なしで動作

---

## 🔍 現状分析

### 壊れているデータフロー

```python
# ❌ 現在（壊れている）
AnnotationStatusFilterWidget.filter_changed
    → ThumbnailSelectorWidget.apply_annotation_filters()  # 存在しない
```

### 利用可能なコンポーネント

- **AnnotationStatusFilterWidget**: ✅ `filter_changed(dict)`シグナルを発行
- **ThumbnailSelectorWidget**: ✅ `_on_images_filtered()`スロットあり
- **AnnotationCoordinator**: ✅ 両ウィジェットにアクセス可能

### 必要な実装

- **ThumbnailSelectorWidget**: ❌ `get_current_image_data()`メソッドなし（現在表示中の画像データ取得用）
- **AnnotationCoordinator**: ❌ 表示レベルフィルタリングロジックなし

---

## 🏗️ 解決策設計

### 簡素化されたアーキテクチャ ⭐

```python
# ✅ 正しい: フィルター → Coordinator → 表示フィルタリング
AnnotationStatusFilterWidget.filter_changed
    → AnnotationCoordinator._on_annotation_display_filter_changed()
    → [メモリ内表示データフィルタリング]
    → ThumbnailSelectorWidget._on_images_filtered()
```

### このアプローチを選ぶ理由

- ✅ **シンプル**: データベースクエリ不要
- ✅ **高速**: メモリ内フィルタリングで即座に応答
- ✅ **責任分離**: Coordinatorが調整役、ThumbnailWidgetは表示専用
- ✅ **最小変更**: 既存コードへの影響を最小限に抑制

---

## 📋 実装タスク

### フェーズ1: ThumbnailSelectorWidget拡張 (15分)

1. **現在表示中の画像データ取得メソッド追加**:
   ```python
   def get_current_image_data(self) -> list[dict]:
       """現在表示中の画像データを返す（フィルタリング用）"""
       return self.current_displayed_images  # 内部状態として保持
   ```

### フェーズ2: AnnotationCoordinator修正 (20分)

1. **表示レベルフィルタリングの実装**:

   ```python
   @Slot(dict)
   def _on_annotation_display_filter_changed(self, filter_conditions: dict):
       """表示中のサムネイルをアノテーション状態でフィルタリング"""
       # 現在表示中の画像データを取得
       current_images = self.thumbnail_selector_widget.get_current_image_data()

       # アノテーション状態でフィルタリング
       filtered_images = self._filter_by_annotation_status(
           current_images, filter_conditions
       )

       # サムネイル表示を更新
       self.thumbnail_selector_widget._on_images_filtered(filtered_images)
   ```
2. **フィルタリングロジックの実装**:

   ```python
   def _filter_by_annotation_status(self, images: list[dict], filters: dict) -> list[dict]:
       """アノテーション状態で画像リストをフィルタリング"""
       # 完了/エラー状態による絞り込み
   ```
3. **シグナル接続の修正**:

   ```python
   # 壊れた接続を置き換え
   self.status_filter_widget.filter_changed.connect(
       self._on_annotation_display_filter_changed  # ✅ 新しいスロット
   )
   ```

### フェーズ3: 不存在メソッド接続の削除 (10分)

1. **存在しないメソッドへの接続を削除**:
   ```python
   # ❌ 削除対象
   - update_image_rating
   - update_image_score
   - refresh_thumbnails
   ```

### フェーズ4: テスト・動作確認 (5分)

1. **統合テスト実行**: `AttributeError`が解消されることを確認
2. **手動テスト**: アノテーション状態フィルタリングの動作確認

---

## ⚠️ リスク軽減

| リスク                         | 確率 | 影響 | 軽減策                     |
| ------------------------------ | ---- | ---- | -------------------------- |
| 既存機能の破綻                 | 低   | 高   | 段階的実装、回帰テスト     |
| フィルタリングロジックの複雑さ | 低   | 中   | シンプルな状態チェックのみ |
| UI応答性の低下                 | 低   | 低   | メモリ内処理で高速         |

---

## 🧪 テスト戦略

### 単体テスト

- `AnnotationCoordinator._filter_by_annotation_status()`
- `ThumbnailSelectorWidget.get_current_image_data()`
- シグナル接続の検証

### 統合テスト

- 完全なシグナルフロー: フィルター → Coordinator → ThumbnailWidget
- `AttributeError`の解消確認
- フィルタリング結果の正確性

### 手動テスト

- GUIアノテーション状態フィルタリングワークフロー
- サムネイル選択の回帰テスト

---

## 📅 タイムライン（大幅短縮）

| フェーズ            | 時間           | 主要成果物                      |
| ------------------- | -------------- | ------------------------------- |
| **フェーズ1** | 15分           | ThumbnailSelectorWidget拡張     |
| **フェーズ2** | 20分           | AnnotationCoordinator修正       |
| **フェーズ3** | 10分           | 不存在メソッド接続削除          |
| **フェーズ4** | 5分            | テスト・動作確認                |
| **合計**      | **50分** | 完全な修正 ⚡**25分短縮** |

---

## 🎯 次のステップ

1. **実装開始**: ThumbnailSelectorWidget拡張から始める
2. **段階的テスト**: 各フェーズ後にテストしてから進む
3. **統合検証**: マージ前にテストが通ることを確認

---

**計画ステータス**: ✅ **簡素化アプローチで実装準備完了**
**推定完了時間**: 50分（25分短縮）
**アーキテクチャ**: 表示レベルフィルタリングで責任分離維持
