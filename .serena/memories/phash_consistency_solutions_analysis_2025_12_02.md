# pHash不整合問題の解決策分析

**日時**: 2025-12-02  
**問題**: LoRAIroとimage-annotator-libのpHash計算アルゴリズム不一致によりDB照会失敗

---

## 問題の根本原因

### 現状の実装差異

**LoRAIro側** (`src/lorairo/utils/tools.py:16-30`):
```python
def calculate_phash(image_path: Path) -> str:
    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")  # 条件付きRGB変換
        hash_val = imagehash.phash(img)
        return str(hash_val)
```

**image-annotator-lib側** (`core/base/annotator.py:246-260`):
```python
def _calculate_phash(self, image: Image.Image) -> str | None:
    try:
        phash = imagehash.phash(image)  # 変換なし
        return str(phash)
    except Exception as e:
        logger.warning(f"知覚ハッシュの計算に失敗: {e}")
        return None
```

### 動作フロー

1. **DB登録時**: LoRAIroの`calculate_phash()` → RGBA/LA/Pの場合RGB変換 → pHashをDBに保存
2. **アノテーション時**: libの`_calculate_phash()` → 変換なし → pHash返却
3. **DB照会**: libが返したpHashでDB検索 → **LoRAIroが保存したpHashと不一致**

### 影響範囲

- **RGBモード画像**: 両方とも変換なし → ✅ 一致
- **RGBA/LA/Pモード画像**: LoRAIro側のみRGB変換 → ❌ 不一致

---

## 解決策の評価

### 選択肢1: image-annotator-lib側を修正（最も推奨）

**変更内容**:
```python
# core/base/annotator.py
def _calculate_phash(self, image: Image.Image) -> str | None:
    try:
        # LoRAIroと同じ前処理を適用
        rgb_image = image.convert("RGB")
        phash = imagehash.phash(rgb_image)
        return str(phash)
    except Exception as e:
        logger.warning(f"知覚ハッシュの計算に失敗: {e}")
        return None
```

**メリット**:
- ✅ 根本原因を解決（アルゴリズム統一）
- ✅ LoRAIro側の変更不要
- ✅ すべての画像モードで一貫性保証
- ✅ 将来的な問題も防止

**デメリット**:
- ⚠️ image-annotator-libの修正が必要
- ⚠️ 既存のpHashキャッシュが無効化される可能性
- ⚠️ libの他の利用者に影響（破壊的変更）

**技術的根拠**:
- imagehashライブラリは内部でYCbCr輝度変換を行う
- RGBとRGBAで輝度計算が異なる（アルファチャネルの扱い）
- 常にRGB変換することで輝度計算を統一

**実装工数**: 小（1メソッドのみ修正）

---

### 選択肢2: LoRAIro側でpHashリスト事前計算

**変更内容**:
```python
# AnnotationWorker.execute()
def execute(self) -> PHashAnnotationResults:
    # Phase 1: pHashリスト事前計算
    phash_list = []
    for image_path in self.image_paths:
        phash = calculate_phash(Path(image_path))  # LoRAIro版
        phash_list.append(phash)
    
    # Phase 2: アノテーション実行（pHashリストを渡す）
    model_results = self.annotation_logic.execute_annotation(
        image_paths=self.image_paths,
        model_names=self.models,
        phash_list=phash_list,  # LoRAIroのpHashを使用
    )
```

**メリット**:
- ✅ image-annotator-lib修正不要
- ✅ LoRAIro側のアルゴリズムを信頼
- ✅ 既存DBとの整合性維持

**デメリット**:
- ❌ pHash二重計算（パフォーマンス低下）
- ❌ 根本原因は未解決（lib側は不整合のまま）
- ❌ 他のlib利用箇所で同じ問題再発

**実装工数**: 小（既存のフローを微修正）

---

### 選択肢3: DB照会前にLoRAIro側でpHash再計算

**変更内容**:
```python
# AnnotationWorker._save_results_to_database()
def _save_results_to_database(self, results: PHashAnnotationResults) -> None:
    for lib_phash, annotations in results.items():
        # libのpHashを使わず、image_pathから再計算
        image_path = self._phash_to_path_mapping[lib_phash]
        lorairo_phash = calculate_phash(Path(image_path))  # 再計算
        
        image_id = self.db_manager.repository.find_duplicate_image_by_phash(lorairo_phash)
```

**メリット**:
- ✅ image-annotator-lib修正不要
- ✅ DBとの整合性確実

**デメリット**:
- ❌ pHash→image_path逆引きが必要（複雑化）
- ❌ pHash二重計算
- ❌ libのpHashを完全に無視（本質的解決ではない）
- ❌ 実装が複雑・保守困難

**実装工数**: 中（マッピング構築が必要）

---

### 選択肢4: DB側にpHash変換テーブル追加

**変更内容**:
```sql
CREATE TABLE phash_mappings (
    lorairo_phash TEXT,
    lib_phash TEXT,
    image_id INTEGER,
    PRIMARY KEY (lorairo_phash, lib_phash)
);
```

**メリット**:
- ✅ 両方のpHashを記録
- ✅ 歴史的互換性維持

**デメリット**:
- ❌ DB設計の複雑化
- ❌ マイグレーション必要
- ❌ 二重管理のメンテナンスコスト
- ❌ 根本原因は未解決

**実装工数**: 大（スキーマ変更、マイグレーション、全体修正）

---

### 選択肢5: imagehashライブラリのバージョン固定

**調査結果**:

**imagehash公式ドキュメント**:
- [GitHub - JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash)
- [ImageHash · PyPI](https://pypi.org/project/ImageHash/)

**アルゴリズム動作**:
- pHashは画像を輝度（Y channel in YCbCr）に変換
- RGB → YCbCr変換は標準的
- **RGBA → RGB変換時のアルファチャネル処理が問題**

**変更内容**: なし（調査のみ）

**結論**:
- ❌ ライブラリ自体の問題ではない
- ❌ バージョン固定では解決しない
- アルファチャネルの扱いは呼び出し側が統一すべき

---

## 推奨解決策

### ✅ 最終推奨: 選択肢1（lib側修正）+ 選択肢2（短期対策）

**段階的実装**:

#### Phase 1: 短期対策（即座に実装可能）
選択肢2を実装し、現在の不具合を即座に解消:
```python
# AnnotationWorker.execute() - 既存コードに追加
phash_list = [calculate_phash(Path(p)) for p in self.image_paths]

model_results = self.annotation_logic.execute_annotation(
    image_paths=self.image_paths,
    model_names=self.models,
    phash_list=phash_list,  # LoRAIroのpHashを強制使用
)
```

**影響**:
- DB保存が即座に成功
- GUIに結果が表示される
- パフォーマンス影響は許容範囲（アノテーション処理自体が重い）

#### Phase 2: 長期対策（image-annotator-lib修正）
選択肢1を実装し、根本原因を解決:
```python
# image-annotator-lib/core/base/annotator.py
def _calculate_phash(self, image: Image.Image) -> str | None:
    try:
        # 常にRGB変換してpHash計算（LoRAIroと統一）
        rgb_image = image.convert("RGB")
        phash = imagehash.phash(rgb_image)
        return str(phash)
    except Exception as e:
        logger.warning(f"知覚ハッシュの計算に失敗: {e}")
        return None
```

**移行計画**:
1. lib修正完了後、LoRAIro側のphash_list事前計算を削除
2. 既存DBのpHashは変更不要（登録時からRGB変換済み）
3. lib側のテスト追加（RGB変換の検証）

---

## 技術的根拠

### imagehashライブラリの動作

**Web検索結果**:
- [ImageHash · PyPI](https://pypi.org/project/ImageHash/)
- [Image hashing with OpenCV and Python - PyImageSearch](https://pyimagesearch.com/2017/11/27/image-hashing-opencv-python/)

**アルゴリズム詳細**:
1. 画像 → YCbCr色空間変換
2. Y（輝度）チャネルのみ使用
3. DCT（離散コサイン変換）適用
4. 低周波成分からハッシュ生成

**RGBA→RGB変換の重要性**:
- YCbCr変換前にアルファチャネル除去が必須
- アルファチャネルがあると輝度計算が変わる
- PIL/Pillowの`convert("RGB")`はアルファを白背景に合成

---

## 実装優先度

| 解決策 | 優先度 | 工数 | 効果 | リスク |
|--------|--------|------|------|--------|
| 選択肢1（lib修正） | ⭐⭐⭐⭐⭐ | 小 | 根本解決 | 低（破壊的変更） |
| 選択肢2（phash事前計算） | ⭐⭐⭐⭐ | 小 | 即座に解決 | 低（パフォーマンス） |
| 選択肢3（再計算） | ⭐⭐ | 中 | 動作はする | 中（複雑化） |
| 選択肢4（DBテーブル） | ⭐ | 大 | 互換性維持 | 高（設計複雑化） |
| 選択肢5（バージョン固定） | ❌ | - | 効果なし | - |

---

## 次のアクション

1. **即座実施**: 選択肢2（phash_list事前計算）を実装
2. **後日実施**: 選択肢1（lib側修正）をimage-annotator-lib Issue/PRで提案
3. **検証**: 実際の画像セットで両解決策をテスト
4. **ドキュメント**: 今回の知見をlorairo-test-generatorスキルに反映

---

## Sources:

- [GitHub - JohannesBuchner/imagehash](https://github.com/JohannesBuchner/imagehash)
- [ImageHash · PyPI](https://pypi.org/project/ImageHash/)
- [pHash.org: Home of pHash](https://www.phash.org/)
- [Image hashing with OpenCV and Python - PyImageSearch](https://pyimagesearch.com/2017/11/27/image-hashing-opencv-python/)
- [Duplicate image detection with perceptual hashing in Python](https://benhoyt.com/writings/duplicate-image-detection/)
