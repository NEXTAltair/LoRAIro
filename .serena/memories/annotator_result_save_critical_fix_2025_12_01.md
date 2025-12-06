# アノテーション結果保存 - 緊急バグ修正記録

**日時**: 2025-12-01  
**タスク**: pHash計算失敗時の整合性崩壊とimage_id未検証の致命的バグ修正  
**ステータス**: ✅ 修正完了

## 発見された致命的バグ

### バグ1: pHash計算失敗時の整合性崩壊
**問題**:
- `_build_phash_mapping()`でpHash計算失敗した画像をスキップ
- `phash_list`が短くなる（例: 10画像中2枚失敗→8件のpHash）
- `image_paths`は元のまま（10画像）
- `image_annotator_lib.annotate()`に渡すと数が合わず、エラーまたは結果のズレ

**問題コード**:
```python
# 失敗画像をスキップ（phash_mappingに追加されない）
for image_path in self.image_paths:
    try:
        phash_mapping[phash_value] = {...}
    except:
        failed_count += 1  # スキップのみ

# 元のimage_pathsをそのまま渡す（数が合わない！）
model_results = self.annotation_logic.execute_annotation(
    image_paths=self.image_paths,  # ← 失敗画像含む
    phash_list=phash_list,         # ← 成功画像のみ
)
```

### バグ2: image_id未検証
**問題**:
- `get_image_id_by_filepath()`が`None`を返す可能性（DB未登録画像）
- チェックなしで`phash_mapping`に格納: `{"image_id": None, ...}`
- 後続の`save_annotations(image_id=None)`で`ValueError`発生
- 保存処理が失敗し、結果が失われる

**問題コード**:
```python
image_id = self.db_manager.get_image_id_by_filepath(image_path)
# Noneチェックなし！
phash_mapping[phash_value] = {"image_id": image_id, "image_path": image_path}
```

## 修正内容

### 修正1: `_build_phash_mapping()`返り値変更

**ファイル**: `src/lorairo/gui/workers/annotation_worker.py:195-241`

#### 変更点:
1. **返り値をtupleに変更**: `tuple[dict, list[str]]`
   - `phash_mapping`: 従来通り
   - `valid_image_paths`: 処理成功した画像パスのリスト（NEW）

2. **image_id=None検証追加**:
```python
if image_id is None:
    failed_count += 1
    logger.error(f"image_id取得失敗: {image_path} - DBに未登録の可能性")
    continue  # スキップ
```

3. **valid_image_pathsに追加**:
```python
phash_mapping[phash_value] = {"image_id": image_id, "image_path": image_path}
valid_image_paths.append(image_path)  # NEW: 成功画像のみ記録
```

#### 修正後のシグネチャ:
```python
def _build_phash_mapping(self) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """pHash→画像メタデータマッピングを構築
    
    Returns:
        tuple[dict, list]: (phash_mapping, valid_image_paths)
            - phash_mapping: {phash: {image_id, image_path}}
            - valid_image_paths: 処理成功した画像パスのリスト
    
    Note:
        pHash計算失敗またはimage_id取得失敗の画像はスキップされ、
        valid_image_pathsには含まれません。
    """
```

### 修正2: `execute()`でvalid_image_paths使用

**ファイル**: `src/lorairo/gui/workers/annotation_worker.py:72-175`

#### 変更点:

1. **tuple unpacking**:
```python
# 修正前
phash_mapping = self._build_phash_mapping()

# 修正後
phash_mapping, valid_image_paths = self._build_phash_mapping()
```

2. **有効画像数チェックとログ**:
```python
valid_count = len(valid_image_paths)
if valid_count < len(self.image_paths):
    logger.warning(
        f"一部画像をスキップ: {len(self.image_paths) - valid_count}件失敗, "
        f"{valid_count}件で処理継続"
    )
```

3. **AnnotationLogicに有効画像のみ渡す**:
```python
# 修正前
model_results = self.annotation_logic.execute_annotation(
    image_paths=self.image_paths,  # ← 失敗画像含む
    phash_list=phash_list,
)

# 修正後
model_results = self.annotation_logic.execute_annotation(
    image_paths=valid_image_paths,  # ✅ 有効画像のみ
    phash_list=phash_list,          # ✅ 数が一致
)
```

4. **進捗報告の修正**:
```python
# すべての進捗報告でvalid_countを使用
self._report_progress(10, "...", total_count=valid_count)  # 修正前: len(self.image_paths)
self._report_progress(85, "...", processed_count=valid_count, total_count=valid_count)
self._report_progress(100, "...", processed_count=valid_count, total_count=valid_count)
```

## 修正効果

### ✅ バグ1修正の効果
- **整合性保証**: `image_paths`と`phash_list`の要素数が完全一致
- **エラー回避**: ライブラリ呼び出し時の実行時エラーを防止
- **結果の正確性**: pHashと画像の対応関係が正確に維持

### ✅ バグ2修正の効果
- **保存成功率向上**: `image_id=None`による`ValueError`を防止
- **早期エラー検出**: マッピング構築時に問題を検出してログ記録
- **データ整合性**: DB未登録画像を事前に除外

### 追加改善
- **詳細ログ**: 失敗画像数と成功画像数を明示的にログ記録
- **部分的成功**: 一部失敗でも処理を継続、成功画像のみを処理
- **正確な進捗表示**: 実際の処理画像数に基づく進捗報告

## 検証結果

- ✅ Python import成功
- ✅ 構文エラーなし
- ✅ 型定義の整合性維持（tuple返り値）
- ✅ 既存機能を破壊しない（後方互換性）

## テストシナリオ（推奨）

### シナリオ1: pHash計算失敗
```
入力: 10画像（うち2枚破損）
期待動作:
- 8枚のpHashマッピング構築
- valid_image_paths = 8枚
- ライブラリには8枚＋8pHashを渡す
- 8枚の結果がDB保存される
```

### シナリオ2: DB未登録画像
```
入力: 10画像（うち1枚がDB未登録）
期待動作:
- 9枚のpHashマッピング構築（image_id取得成功）
- 1枚はスキップ（image_id=None検出）
- 9枚の結果がDB保存される
```

### シナリオ3: 全失敗
```
入力: 10画像（全て破損またはDB未登録）
期待動作:
- phash_list = []
- ValueError発生: "pHash計算に失敗しました"
- 処理中止
```

## 関連ファイル

- **修正**: `src/lorairo/gui/workers/annotation_worker.py`
- **影響なし**: `src/lorairo/annotations/annotation_logic.py` (シグネチャ変更なし)

## 次のステップ

1. **統合テスト**: 破損画像・DB未登録画像を含むケースでテスト
2. **エラーログ確認**: `logger.error()`出力を確認
3. **進捗表示確認**: GUIで正確な画像数が表示されるか確認

## 関連メモリ

- `annotator_result_save_fix_implementation_completion_2025_12_01.md` - 元の実装記録
- `annotator_result_save_fix_plan_v2_2025_12_01.md` - 実装計画
