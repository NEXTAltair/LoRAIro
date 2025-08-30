# ThumbnailSelectorWidget サイズ変更時クリア問題の解決分析

## 問題概要（2025-08-29）
ThumbnailSelectorWidget._on_thumbnail_size_slider_changed()でグリッドサイズ変更時に古いサムネイルが残存する問題が発生。

## 根本原因
- `_display_cached_thumbnails()`が直接呼び出される
- 他のメソッド(`load_thumbnails_from_result`)では`scene.clear()`と`thumbnail_items.clear()`が実行される
- キャッシュ最適化実装により高速化したが、UI要素クリアが不完全

## 解決策分析結果

### 推奨解決策: シンプル修正（アプローチ1）
**実装**: `_on_thumbnail_size_slider_changed()`に2行追加
```python
# 【追加】UI要素クリア
self.scene.clear()
self.thumbnail_items.clear()
```

**選定理由**:
- 確実性: 根本原因に直接対処
- 最小リスク: 2行追加の最小限変更
- アーキテクチャ準拠: 既存`load_thumbnails_from_result()`パターンと一致
- テスト効率: 影響範囲限定的
- 実装速度: 即座適用可能

### 代替案評価

#### アプローチ2: パフォーマンス最適化
- メリット: 最高のパフォーマンス、視覚的継続性
- デメリット: 実装複雑度高、ThumbnailItem.update_pixmap()実装必要
- 判定: オーバーエンジニアリング（現状で十分高速）

#### アプローチ3: アーキテクチャ改善
- メリット: 保守性向上、コード重複排除
- デメリット: 修正範囲拡大、リファクタリングリスク
- 判定: 将来のリファクタリング時に検討

#### アプローチ4: 防御的プログラミング
- メリット: 最高安定性、例外処理保護
- デメリット: コード量増加、過度な防御処理
- 判定: 現在の問題には過剰

## 実装計画
1. `_on_thumbnail_size_slider_changed()`修正
2. ログ出力でクリア処理記録
3. ユニットテスト追加（サイズ変更前後のアイテム数検証）

## 技術的教訓
- キャッシュ最適化実装時のUI要素管理の重要性
- `_display_cached_thumbnails()`の設計前提（事前クリア必須）の理解
- 既存パターンとの一貫性確保の重要性