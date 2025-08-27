# LoRAIro アーキテクチャ改善計画 - 2025-08-27

## 概要
SearchConditions互換性、プライベートAPI直接呼び出し、Signal型不整合の3つの技術課題に対する包括的改善計画。

## 特定された技術課題

### 1. SearchConditions後方互換性問題
**現状**: テストコードがdictを使用、WorkerServiceはSearchConditionsを期待
**影響**: テスト実行時の型不整合、将来的な破壊的変更リスク
**位置**: `src/lorairo/gui/services/worker_service.py:start_search()`

### 2. プライベートAPI直接呼び出し
**現状**: `AnnotationCoordinator._on_annotation_display_filter_changed()` が `ThumbnailSelectorWidget._on_images_filtered()` を直接呼び出し
**影響**: カプセル化違反、テスタビリティ低下、保守性問題
**位置**: `src/lorairo/gui/widgets/annotation_coordinator.py:332`

### 3. Signal型不整合
**現状**: `CustomGraphicsView.itemClicked = Signal(QGraphicsPixmapItem)` だが `ThumbnailItem` をemit
**影響**: 型安全性欠如、IDE補完問題、潜在的ランタイムエラー
**位置**: `src/lorairo/gui/widgets/thumbnail.py:CustomGraphicsView`

## 選定実装アプローチ

### Phase 1: WorkerService互換性層実装
```python
# src/lorairo/gui/services/worker_service.py
def _ensure_search_conditions(self, conditions: Union[dict, SearchConditions]) -> SearchConditions:
    """dict/SearchConditions両方を受け入れる変換層"""
    if isinstance(conditions, dict):
        return SearchConditions(**conditions)
    return conditions

def start_search(self, search_conditions: Union[dict, SearchConditions]) -> str:
    """後方互換性を保持したsearch開始"""
    search_conditions = self._ensure_search_conditions(search_conditions)
    # 既存実装...
```

**利点**: 
- 既存API破壊なし
- テスト修正不要
- 段階的移行可能
- 型安全性確保

### Phase 2: ThumbnailSelectorWidget公開API追加
```python
# src/lorairo/gui/widgets/thumbnail.py
def apply_filtered_metadata(self, filtered_data: list[dict[str, Any]]) -> None:
    """公開API: フィルター結果の適用
    
    Args:
        filtered_data: フィルター済みメタデータリスト
    """
    self._on_images_filtered(filtered_data)
```

**移行**: `AnnotationCoordinator` 修正
```python
# Before
self.thumbnail_selector_widget._on_images_filtered(filtered_images)

# After  
self.thumbnail_selector_widget.apply_filtered_metadata(filtered_images)
```

**利点**:
- 適切なAPI境界
- テスタビリティ向上
- カプセル化強化

### Phase 3: Signal型整合性修正
```python
# src/lorairo/gui/widgets/thumbnail.py:CustomGraphicsView
from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

class CustomGraphicsView(QGraphicsView):
    # Before: itemClicked = Signal(QGraphicsPixmapItem, Qt.KeyboardModifier)
    # After:
    itemClicked = Signal(ThumbnailItem, Qt.KeyboardModifier)
```

**利点**:
- 型安全性確保
- IDE補完改善
- ランタイムエラー防止

## 実装戦略

### 優先順位
1. **高**: WorkerService互換性層（テスト実行への直接影響）
2. **中**: ThumbnailSelectorWidget API改善（アーキテクチャ整合性）
3. **低**: Signal型修正（開発体験改善）

### テスト戦略
- 既存テスト実行確認
- 新規互換性テスト追加
- 段階的移行による影響範囲限定

### 移行計画
1. 新機能実装・テスト
2. 既存呼び出し箇所移行
3. レガシー実装段階的削除
4. 完全移行確認

## 期待効果

### 短期効果
- テスト実行安定化
- 型安全性向上
- API一貫性改善

### 長期効果  
- 保守性大幅向上
- 新機能開発効率化
- バグ発生率削減

## 関連実装パターン
この改善は2025-01-22のSearchConditions統合パターンを踏襲し、段階的互換性確保アプローチを採用。

## 次段階
ユーザー承認後、Phase 1から順次実装開始。各Phaseでテスト実行・動作確認を実施。