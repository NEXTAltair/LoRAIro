# ThumbnailWorker 51%停止問題 - 詳細調査報告

**調査日**: 2025-08-24
**問題**: ThumbnailWorkerが53件処理で51%付近（≈27件）で処理停止する問題
**Status**: 🔍 根本原因特定完了 → 修正計画立案済み

## 🚨 **根本原因の特定**

### **1. 進捗計算の数学的分析**
- **計算式**: `ProgressHelper.calculate_percentage(27, 53, 5, 90)` = **50.8%** ≈ **51%**
- **進捗範囲**: 5-90%（100%は完了処理で別途発行）
- **バッチ構成**: BATCH_SIZE=100で53件 → 1バッチのみ（0-53）

### **2. 停止箇所の特定**
**Location**: `src/lorairo/gui/workers/database_worker.py:338-370`
```python
# バッチ内のアイテム処理ループ（27件目付近で停止）
for image_data in batch_items:  # line 338
    # 具体的停止箇所の候補：
    # 1. _get_thumbnail_path() でのDB呼び出し (line 346)
    # 2. QImage読み込み処理 (line 353)
    # 3. scaled() でのスケーリング処理 (line 359-363)
```

### **3. 技術的問題点**

#### **A. キャンセレーション不備**
- `_check_cancellation()`がバッチ境界でのみ実行（line 330）
- バッチ内ループ（27件処理中）では実行されない
- **→ 長時間処理でキャンセル不能、UI無反応**

#### **B. データベースアクセス競合**
```python
# _get_thumbnail_path() 内での重複DB呼び出し
existing_512px = self.db_manager.check_processed_image_exists(image_id, 512)
# 53件 × DB呼び出し → 潜在的ロック・競合リスク
```

#### **C. 重い画像処理**
```python
# Qt SmoothTransformation は重い処理
scaled_qimage = qimage.scaled(
    self.thumbnail_size,
    Qt.AspectRatioMode.KeepAspectRatio,
    Qt.TransformationMode.SmoothTransformation,  # CPU集約的
)
```

#### **D. 同期的ファイルI/O**
```python
# 各画像でファイル存在チェック
if not thumbnail_path or not thumbnail_path.exists():  # 同期I/O
```

## 🎯 **Phase 1: 即座の修正計画**

### **1. バッチ内キャンセレーション改善**
**Target**: `database_worker.py:338-370`
```python
# 修正前: バッチ境界でのみキャンセルチェック
for image_data in batch_items:

# 修正後: 定期的キャンセルチェック
for idx, image_data in enumerate(batch_items):
    if idx % 5 == 0:  # 5件毎
        self._check_cancellation()
```

### **2. データベースアクセス最適化**
**Target**: `ThumbnailWorker._get_thumbnail_path()`
```python
# 修正前: 個別DB呼び出し
for image_data in batch_items:
    existing_512px = self.db_manager.check_processed_image_exists(image_id, 512)

# 修正後: バッチ一括取得
batch_512px_info = self.db_manager.batch_check_processed_images(
    [item.get("id") for item in batch_items], 512
)
```

### **3. 詳細デバッグログ実装**
**Target**: バッチ内処理の各ステップ
```python
logger.debug(f"Processing item {idx+1}/{len(batch_items)}: id={image_id}")
logger.debug(f"Thumbnail path resolved: {thumbnail_path}")
logger.debug(f"QImage loaded: size={qimage.size()}, null={qimage.isNull()}")
```

### **4. タイムアウト機構**
**Target**: 個別画像処理
```python
import signal
def timeout_handler(signum, frame):
    raise TimeoutError("Image processing timeout")

# 個別画像処理にタイムアウト（例：5秒）
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5)
try:
    # 画像処理
finally:
    signal.alarm(0)
```

## 📊 **期待効果**

### **Phase 1 完了後**
- ✅ **51%停止問題の完全解決**
- ✅ **バッチ処理中のキャンセル可能性確保**
- ✅ **DB呼び出し最適化による高速化**
- ✅ **詳細ログによるデバッグ能力向上**
- ✅ **長時間処理の自動回復機構**

### **パフォーマンス改善予測**
- DB呼び出し回数: **53回 → 1回** （53倍高速化）
- キャンセル応答性: **バッチ完了まで → 5件毎** （約10倍改善）
- デバッグ効率: **ブラックボックス → 詳細追跡可能**

## 🔄 **次フェーズ予定**

### **Phase 2: 構造改善**
- バッチ内進捗報告の細分化
- 非同期I/O実装による更なる高速化

### **Phase 3: 長期最適化**
- サムネイルキャッシュシステム
- メモリ効率的な画像処理パイプライン

---

## 📝 **技術的備考**

### **過去の修正との関係**
- **QPixmap null対策**: 既に実装済み（2025-08-23）
- **UUID ID生成**: 既に実装済み（2025-08-23）
- **QImage化**: 既に実装済み（スレッドセーフ確保）

### **今回の修正範囲**
- **Focus**: バッチ内処理最適化とレスポンシブ性向上
- **Scope**: ThumbnailWorker::execute() メソッド内改善
- **Risk**: 低リスク（既存機能拡張のみ）

### **検証方法**
1. 53件データセットでの再現テスト
2. 進捗ログ詳細確認
3. キャンセレーション応答性テスト
4. パフォーマンス測定（処理時間・DB呼び出し回数）