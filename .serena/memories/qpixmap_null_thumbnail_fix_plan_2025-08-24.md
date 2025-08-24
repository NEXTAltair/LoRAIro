# QPixmap Null Pixmap Error 修正計画 2025-08-24

## 問題の概要
- **エラー**: `QPixmap::scaled: Pixmap is a null pixmap` (53回発生)
- **原因**: ThumbnailSelectorWidget の二つのサムネイル読み込みパスで null pixmap バリデーション不足
- **影響**: Qt警告、視覚的な破損、パフォーマンス低下

## 根本原因分析

### 1. Modern Worker-Based Path (推奨パス)
- **場所**: `src/lorairo/gui/widgets/thumbnail.py:279-280`
- **問題**: `QPixmap.fromImage(qimage)` 後の null チェック不足
- **コード**: 
```python
qpixmap = QPixmap.fromImage(qimage)
thumbnail_map[image_id] = qpixmap  # ❌ null チェックなし
```

### 2. Legacy Direct Loading Path (問題のあるパス)
- **場所**: `src/lorairo/gui/widgets/thumbnail.py:447-451`
- **問題**: `QPixmap(image_path).scaled()` 前の null チェック不足
- **コード**:
```python
pixmap = QPixmap(str(image_path)).scaled(  # ❌ null チェックなし
    self.thumbnail_size, ...
)
```

### 3. Best Practice 確認
- **ImagePreviewWidget**: 既に `pixmap.isNull()` チェック実装済み (line 72)
- **パターン**: 同じ validate → log → skip パターンを適用可能

## 実装計画

### Phase 1: Critical Fixes (即座対応)
**目標**: Qt警告の即座停止、基本的な安定性確保

#### 1.1 Modern Path Null Check
```python
# load_thumbnails_from_result() in line 279-280
for image_id, qimage in thumbnail_result.loaded_thumbnails:
    qpixmap = QPixmap.fromImage(qimage)
    if not qpixmap.isNull():  # ✅ ADD
        thumbnail_map[image_id] = qpixmap
    else:
        logger.warning(f"Failed to create pixmap from QImage for image_id: {image_id}")
```

#### 1.2 Legacy Path Null Check  
```python
# add_thumbnail_item() in line 447-451
raw_pixmap = QPixmap(str(image_path))
if raw_pixmap.isNull():  # ✅ ADD
    logger.warning(f"Failed to load image: {image_path}")
    return
    
pixmap = raw_pixmap.scaled(...)
```

### Phase 2: Architecture Cleanup (短期対応)
**目標**: 重複パス統合、競合状態解消

#### 2.1 State Management
- Worker pipeline 実行中の legacy path 無効化
- `update_thumbnail_layout()` の呼び出し制御
- Pipeline 状態の追跡とロック機能

#### 2.2 Path Unification
- Modern worker-based path を主要パスとして確立
- Legacy path を fallback or maintenance モードに限定

### Phase 3: Enhanced Error Handling (中期対応)
**目標**: 詳細なエラー情報とデバッグ支援

#### 3.1 Enhanced Logging
```python
logger.error(f"Null pixmap: {image_path}, Exists: {image_path.exists()}, "
            f"Size: {image_path.stat().st_size if image_path.exists() else 'N/A'}")
```

#### 3.2 Fallback Mechanisms
- Placeholder 画像の表示
- 破損した画像のスキップとマーキング
- ユーザーへの情報表示

### Phase 4: Testing & Validation (検証)
**目標**: 修正の確認と回帰テスト

#### 4.1 Test Cases
- 正常な画像での動作確認
- 破損/不正な画像でのエラーハンドリング確認
- 大量画像での性能確認
- 競合状態の確認

#### 4.2 Performance Testing
- メモリ使用量の測定
- Qt警告の完全除去確認
- UI応答性の確認

## リスク評価

### 低リスク
- Phase 1 の null check 追加は既存動作に影響なし
- ImagePreviewWidget で実証済みパターン

### 中リスク  
- Phase 2 の architecture cleanup は既存動作変更の可能性
- 十分なテストが必要

### 高リスク
- なし（安全な段階的アプローチ）

## 成功基準
1. Qt警告 "QPixmap::scaled: Pixmap is a null pixmap" の完全除去
2. サムネイル表示の視覚的改善
3. エラー時の適切な fallback 動作
4. 既存機能の regression なし

## 次のステップ
1. Phase 1 の実装と検証
2. 段階的な Phase 2-4 の実行
3. 包括的なテストの実施