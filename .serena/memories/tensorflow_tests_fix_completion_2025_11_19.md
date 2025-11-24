# TensorFlowテスト修正完了（2025-11-19）

## 実施内容

### 修正対象
- `local_packages/image-annotator-lib/tests/unit/model_class/test_tagger_tensorflow.py`
- `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/tagger_tensorflow.py`
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/tensorflow.py`

### 問題原因
1. `DeepDanbooruTagger.__init__()`が`config`引数を受け付けていなかった
2. `TensorflowBaseAnnotator.__init__()`も`config`引数が未対応
3. テスト関数の引数に`mock_config`が不足
4. `_format_predictions()`がエラー時に例外を投げていた（テストはエラー辞書を期待）
5. `_preprocess_images()`が空リストを処理できなかった

### 修正内容

#### 1. DeepDanbooruTagger.__init__修正
```python
# 修正前
def __init__(self, model_name: str):

# 修正後
def __init__(self, model_name: str, config: BaseModelConfig | None = None):
    super().__init__(model_name=model_name, config=config)
```

**追加import**:
```python
from ..core.model_config import BaseModelConfig
```

**tag_threshold修正**:
```python
# Noneの場合もデフォルト値0.35を使用
threshold = config_registry.get(self.model_name, "tag_threshold", 0.35)
self.tag_threshold = threshold if threshold is not None else 0.35
```

#### 2. TensorflowBaseAnnotator.__init__修正
```python
# 修正前
def __init__(self, model_name: str):
    super().__init__(model_name=model_name)

# 修正後
def __init__(self, model_name: str, config: BaseModelConfig | None = None):
    super().__init__(model_name=model_name, config=config)
```

**追加import**:
```python
from ..model_config import BaseModelConfig
```

#### 3. _format_predictions修正
```python
# 修正前（エラー時に例外を投げる）
if not all_tags:
    raise ValueError("タグ候補リストが見つかりません。")

# 修正後（エラー辞書を返す）
if not all_tags:
    return [{"error": "タグ候補リストが見つかりません。"}]
```

**対象箇所**:
- NumPy変換エラー
- タグリスト不足
- 次元ミスマッチ

#### 4. _preprocess_images修正
```python
# 空リスト処理を追加
if not images:
    logger.debug("Empty image list, returning empty batch.")
    return np.empty((0, target_size[0], target_size[1], 3), dtype=np.float32)
```

#### 5. テスト修正
**修正箇所**: 19テスト関数

**パターン1**: 関数引数に`mock_config`追加
```python
# 修正前
def test_load_tags_missing_model_dir():

# 修正後
def test_load_tags_missing_model_dir(mock_config):
```

**パターン2**: DeepDanbooruTagger初期化に`config`追加
```python
# 修正前
tagger = DeepDanbooruTagger("deepdanbooru-v3")

# 修正後
tagger = DeepDanbooruTagger("deepdanbooru-v3", config=mock_config)
```

## テスト結果

### TensorFlowテスト
- **成功**: 19/19 ✅
- **失敗**: 0件

### 全体テスト（--no-cov）
- **成功**: 1,254件（+19件改善）
- **失敗**: 45件（-19件削減）
- **エラー**: 156件（カバレッジ問題、修正対象外）

## 修正前後の比較

| 項目 | 修正前 | 修正後 | 変化 |
|------|--------|--------|------|
| TensorFlowテスト成功 | 0/19 | 19/19 | +19 ✅ |
| 全体テスト成功 | 1,235 | 1,254 | +19 ✅ |
| 全体テスト失敗 | 64 | 45 | -19 ✅ |

## 残課題

### ONNXテスト（推定）
`test_onnx.py`も同様の問題がある可能性があります（未確認）。

### GUIテスト失敗（45件）
- Worker関連: 5件
- Upscaler関連: 4件
- Filter/Search統合: 7件
- MainWindow統合: 11件
- その他: 18件

### カバレッジエラー（156件）
`pyproject.toml`の`fail_under = 75`設定により、個別ファイルカバレッジ不足がERRORとして報告されています。

## 関連ファイル

**修正済み**:
- `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/tagger_tensorflow.py`
- `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/tensorflow.py`
- `local_packages/image-annotator-lib/tests/unit/model_class/test_tagger_tensorflow.py`

## 次のステップ

1. ONNXテストの確認・修正
2. GUIテスト45件の個別調査・修正
3. カバレッジ設定の調整（fail_underの削除または緩和）
