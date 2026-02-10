# Tier 3 設定項目 詳細分析 (2026-02-09)

## 1. target_resolution

### 現状
- **TOML設定値**: `image_processing.target_resolution = 1024`
- **db_manager.py実装**: `target_resolution = 512` (ハードコード)
- **ImageProcessingService**: target_resolutionをパラメータで受け取る設計
- **ImageProcessor**: 512x512を基準として処理

### 問題点
- **設定値と実装にギャップあり**
  - TOML では 1024 で定義
  - 実装では 512 でハードコード
  - ConfigurationService の設定値が使われていない

### 使用箇所
- `ImageProcessingService.create_processing_manager(target_resolution)` - パラメータ形式
- `ImageProcessingManager.__init__` - インスタンス変数として保持
- `ImageProcessor.find_closest_resolution()` - アスペクト比計算に使用
- `db_manager.ensure_512px_image()` - 512にハードコード

### 判定
**UI化 or TOML削除が必要**
- 現在は実装が「512固定」になっているので、TOML 1024 の設定は無視されている
- 決定待ち: 512固定化するか、ユーザー選択肢にするか

---

## 2. upscaler

### 現状
- **TOML設定値**: `image_processing.upscaler = "RealESRGAN_x4plus"`
- **upscaler_models配列**: 2個のモデル定義あり

### 使用箇所
- `ImageProcessingService._process_single_image()` - 使用
- `ImageProcessingManager.__init__()` - Upscalerインスタンス生成時に参照
- `db_manager.py` - `upscaler` 変数で参照（実装確認: Line検索結果）

### 実装の詳細
```python
# ImageProcessingManager.__init__ での使用
upscaler = Upscaler(config_service)  # ConfigService経由で設定読み込み
# または
upscaler = image_processing_config.get("upscaler", "RealESRGAN_x4plus")
```

### 判定
**UI化の検討値**
- 複数モデルが定義されている
- ユーザーが選択する可能性がある
- ただし、現在のUIで選択肢がない
- 優先度：**低〜中**（後でUI化可能な候補）

---

## 3. realesrgan_upscale

### 現状
- **TOML設定値**: `image_processing.realesrgan_upscale = False`
- **実装での参照**: ゼロ（見つからない）

### 判定
**削除対象 - DEPRECATED設定**
- config.py に定義されているだけ
- 実装コードで全く参照されていない
- 古い設定項目の可能性

### 推奨アクション
削除 → config.py, lorairo.toml から削除

---

## 4. realesrgan_model

### 現状
- **TOML設定値**: `image_processing.realesrgan_model = "RealESRGAN_x4plus_anime_6B.pth"`
- **実装での参照**: ゼロ（見つからない）
- **代わりに使われているもの**: upscaler_models 配列 + upscaler 選択値

### 判定
**削除対象 - DEPRECATED設定**
- config.py に定義されているだけ
- 実装コードで全く参照されていない
- `upscaler_models` 配列が代替している

### 推奨アクション
削除 → config.py, lorairo.toml から削除

---

## 5. generation設定全般
- `batch_jsonl`
- `start_batch`
- `single_image`

### 現状
- **TOML設定値**: `generation = {"batch_jsonl": False, "start_batch": False, "single_image": True}`
- **実装での参照**: ゼロ（見つからない）
- **メソッド名に含まれるが設定値ではない**
  - `_start_batch_annotation()` - 関数名で、設定値ではない
  - `start_batch_registration()` - 関数名で、設定値ではない
  - `create_batch_jsonl()` - 関数名で、設定値ではない

### 判定
**削除対象 - DEPRECATED設定**
- 古い CLI/バッチ処理向けの設定か
- 現在の GUI 実装では不使用

### 推奨アクション
削除 → config.py, lorairo.toml から削除

---

## 6. options設定全般
- `generate_meta_clean`
- `cleanup_existing_tags`
- `join_existing_txt`

### 現状
- **TOML設定値**: `options = {"generate_meta_clean": False, "cleanup_existing_tags": False, "join_existing_txt": True}`
- **実装での参照**: ゼロ（見つからない）

### 判定
**削除対象 - DEPRECATED設定**
- 古い CLI/処理向けの設定か
- 現在の GUI 実装では不使用

### 推奨アクション
削除 → config.py, lorairo.toml から削除

---

## 7. prompts設定

### 現状
- **TOML設定値**: `prompts = {"main": "", "additional": ""}`
- **実装での参照**: 調査中（ConfigurationServiceで取得メソッドあり？）

### 判定
**保留中 - 要確認**
- "main" と "additional" の用途不明
- ConfigurationService に取得メソッドがあるか確認必要

---

## 最終判定サマリー

| 項目 | 現状 | 使用 | 判定 |
|------|------|------|------|
| target_resolution | 1024定義, 512実装 | ⚠️ あり（ギャップ） | 実装統一化必須 |
| upscaler | 定義あり | ✅ あり | UI化検討値 or 内部設定 |
| realesrgan_upscale | 定義のみ | ❌ なし | **削除対象** |
| realesrgan_model | 定義のみ | ❌ なし | **削除対象** |
| generation全般 | 定義のみ | ❌ なし | **削除対象** |
| options全般 | 定義のみ | ❌ なし | **削除対象** |
| prompts | 定義あり | ❓ 要確認 | 調査待ち |

## 推奨アクション（優先度順）

1. **即削除** (実装で参照なし)
   - realesrgan_upscale
   - realesrgan_model
   - generation全般 (batch_jsonl, start_batch, single_image)
   - options全般 (generate_meta_clean, cleanup_existing_tags, join_existing_txt)

2. **要調査後に実装統一**
   - target_resolution: TOML 1024 と実装 512 のギャップ解消
   - upscaler: 固定値化 or UI化の決定

3. **要確認**
   - prompts: main/additional の用途確認
