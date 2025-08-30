# ImagePreviewWidget "Image data not found" 問題修正プラン

## 実装日: 2025-08-29
## ブランチ: fix/image-preview-data-not-found  
## Status: 計画策定完了 ✅

## 🎯 問題分析

### 根本原因: UI状態とDatasetStateManager選択状態の不整合
先ほどのグリッドサイズ変更問題修正で追加したUIクリア処理が原因：

```python
# _on_thumbnail_size_slider_changed() に追加された処理
self.scene.clear()           # Qt UI要素クリア  
self.thumbnail_items.clear() # サムネイルアイテムクリア
self._display_cached_thumbnails()  # UI再構築
```

**問題の発生メカニズム:**
1. ユーザーが画像選択 → `DatasetStateManager._current_image_id = 3489` 保存
2. グリッドサイズ変更 → **UI要素のみクリア、選択状態は保持**
3. UI再構築中または完了後、古い選択状態に基づく `current_image_changed` シグナル発火
4. `ImagePreviewWidget._on_current_image_changed(3489)` 実行
5. `DatasetStateManager.get_image_by_id(3489)` → `None` → "Image data not found for ID: 3489" 警告

### エラーログ詳細
```
2025-08-29 21:46:29.629 | WARNING  | lorairo.gui.widgets.image_preview:_on_current_image_changed - Image data not found for ID: 3489
```

### データフロー確認済み
```
ThumbnailSelectorWidget.handle_item_selection() 
  → DatasetStateManager.set_current_image() 
  → current_image_changed signal
  → ImagePreviewWidget._on_current_image_changed()
  → DatasetStateManager.get_image_by_id() → None
```

## 🏆 推奨解決策: 選択状態同期アプローチ

### Solutions Agent代替分析結果
**検討したアプローチ:**
1. **選択状態同期** (推奨): UIクリア時にDatasetStateManagerの選択状態もクリア
2. **防御的プログラミング**: エラー処理強化による症状隠蔽  
3. **タイミング制御**: シグナルブロック制御
4. **アーキテクチャ改善**: 整合性保証メカニズム追加

**推奨理由:**
- ✅ 根本原因の直接解決
- ✅ UI状態とデータ状態の完全同期
- ✅ 既存DatasetStateManager + Signal/Slotアーキテクチャに準拠
- ✅ 実装がシンプル (3-4行追加)
- ✅ 理解しやすい直感的な解決策

## 🚀 実装内容

### 修正対象ファイル
`src/lorairo/gui/widgets/thumbnail.py`

### 修正箇所
`ThumbnailSelectorWidget._on_thumbnail_size_slider_changed()` メソッド

### 具体的実装
```python
def _on_thumbnail_size_slider_changed(self, value: int):
    """
    サムネイルサイズスライダーの値変更を処理する（高速キャッシュ版）。

    キャッシュされた元画像から新サイズにスケールし、ファイルI/Oを
    完全回避した高速なサイズ変更を実現する。

    Args:
        value (int): 新しいサムネイルサイズ値
    """
    old_size = self.thumbnail_size
    self.thumbnail_size = QSize(value, value)

    # 画像件数表示を更新
    self._update_image_count_display()

    # キャッシュから高速再表示（ファイルI/O完全回避）
    if self.image_cache:
        logger.debug(f"サムネイルサイズ変更: {old_size.width()}x{old_size.height()} → {value}x{value}")
        
        # UI要素クリア（古い画像残存問題の修正）
        self.scene.clear()
        self.thumbnail_items.clear()
        
        # 【追加】選択状態クリア（データ不整合問題の修正）
        if self.dataset_state:
            self.dataset_state.clear_current_image()
            self.dataset_state.clear_selection()
        
        self._display_cached_thumbnails()
    else:
        # キャッシュが空の場合は従来方式（フォールバック）
        if len(self.image_data) <= 50:
            self.update_thumbnail_layout()
```

### 変更内容要約
- **追加**: `if self.dataset_state:` チェック
- **追加**: `self.dataset_state.clear_current_image()`
- **追加**: `self.dataset_state.clear_selection()`
- **目的**: UI状態とデータ状態の完全同期による不整合問題解決

## 📊 実装計画

### Phase 1: コア修正実装
1. **ファイル修正**: `src/lorairo/gui/widgets/thumbnail.py`
2. **修正内容**: 3-4行追加による選択状態クリア
3. **動作確認**: グリッドサイズ変更時の警告メッセージ消失確認

### Phase 2: 品質確保
1. **コード品質**: Ruff formatting, mypy型チェック
2. **機能テスト**: グリッドサイズ変更 → 画像選択の動作確認
3. **UI/UX確認**: 選択状態リセットが自然な動作であることの確認

### Phase 3: 完了処理
1. **コミット**: 原子的修正のコミット
2. **検証**: エラーログ出力の完全停止確認
3. **知識蓄積**: 実装結果と教訓の記録

## 🧪 テスト戦略

### 基本動作テスト
1. **画像選択 → グリッドサイズ変更**:
   - 選択状態がクリアされることを確認
   - プレビュー領域がクリアされることを確認
   - エラーログが出力されないことを確認

2. **グリッドサイズ変更 → 新しい画像選択**:
   - 新しい選択が正常に機能することを確認
   - プレビュー表示が正常に更新されることを確認

### エラーログ監視
```bash
# 実行前: エラーログ確認
grep "Image data not found for ID" logs/lorairo.log

# グリッドサイズ変更操作実行

# 実行後: エラーログが出力されないことを確認
grep "Image data not found for ID" logs/lorairo.log
```

## 📈 期待される効果

### 直接効果
- ✅ "Image data not found for ID: XXXX" エラーログの完全解消
- ✅ UI状態とデータ状態の完全同期
- ✅ グリッドサイズ変更時の一貫した動作

### 技術的利点
- ✅ DatasetStateManager設計思想との整合性確保
- ✅ Signal/Slotアーキテクチャの適切な活用
- ✅ 既存キャッシュ最適化機能との共存
- ✅ 将来的な保守性確保

### ユーザビリティ影響
- **仕様変更**: グリッドサイズ変更時に選択状態がリセット
- **自然な動作**: サイズ変更 = 新しい表示状態という直感的な仕様

## 🔮 長期的視点

### 設計パターンの確立
今回の解決策は以下の設計パターンを確立：
```
UI状態変更時 = データ状態も同期更新
```

### 類似問題の予防
- フィルタ適用時の選択状態管理
- ソート変更時の選択状態管理
- データセット切り替え時の状態管理

### アーキテクチャ改善可能性
- UI/データ状態同期の自動化メカニズム
- 状態不整合検出・警告システム
- より堅牢な状態管理パターンの導入

## 関連実装記録
- `thumbnail_grid_size_persistence_fix_implementation_complete_2025-08-29`: 直前の修正（今回の問題の原因）
- `thumbnail_preview_connection_fix_2025`: 類似のプレビュー表示問題
- `thumbnail_cache_optimization_implementation_2025`: キャッシュ最適化基盤

## 設計判断と根拠

### なぜ選択状態同期アプローチなのか
1. **根本解決**: 症状ではなく原因に対処
2. **設計整合性**: DatasetStateManagerの責務に適合
3. **実装コスト**: 最小限の変更で最大効果
4. **ユーザビリティ**: グリッドサイズ変更時の選択リセットは自然な動作

### 他のアプローチを採用しなかった理由
- **防御的プログラミング**: 対症療法で根本解決にならない
- **タイミング制御**: 複雑すぎて保守性が低下
- **アーキテクチャ改善**: オーバーエンジニアリング

この実装により、UI状態とデータ状態の不整合による警告が解消され、一貫した動作が保証されます。