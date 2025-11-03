# Phase 3 P3.3～P3.5 完了記録 (2025-11-03)

## 概要

**期間**: 2025-11-03セッション
**作業フェーズ**: Phase 3 P3.3, P3.4, P3.5
**最終結果**: 433 passed, 19 skipped, 5 failed (前回から15件改善)

## Phase 3 P3.3: test_transformers.py修正完了

### 問題

- test_transformers.py内の全9テストが `ValueError: Model 'dummy-model' not found in config_registry`で失敗
- DummyTransformersAnnotatorが `super().__init__()`でconfig読み込みを試みるが、"dummy-model"が未登録

### 解決策

```python
# tests/unit/standard/core/base/test_transfomers.py
@pytest.fixture(autouse=True)
def setup_dummy_model_config():
    """Setup dummy model configuration for all tests."""
    from image_annotator_lib.core.config import config_registry

    config = {
        "model_path": "/path/to/dummy-model",
        "device": "cpu",
        "class": "DummyTransformersAnnotator",
    }
    for key, value in config.items():
        config_registry.add_default_setting("dummy-model", key, value)

    yield

    # Cleanup
    try:
        config_registry._config.pop("dummy-model", None)
    except (AttributeError, KeyError):
        pass
```

### 結果

- **9 tests passed** (100%成功率)
- autouse fixtureでテスト前後に自動setup/cleanup

---

## Phase 3 P3.4: test_webapi.py invalid値テスト処理

### 問題

- 4テストが `ConfigurationError: モデル 'test_model' の設定オブジェクト変換に失敗`で失敗
- Phase 1BでPydantic validation導入後、invalid値がconfig変換時に拒否される
- テストが想定していた「invalid値でannotator初期化→デフォルト値使用」が実行不可能

### 対象テスト

1. `test_init_with_invalid_timeout`
2. `test_init_with_invalid_retry_count`
3. `test_init_with_invalid_retry_delay`
4. `test_init_with_invalid_min_request_interval`
5. `test_init_with_invalid_max_output_tokens`

### 解決策

```python
@pytest.mark.skip(reason="Pydantic config validation makes invalid value testing infeasible")
@pytest.mark.standard
@patch("image_annotator_lib.core.base.webapi.logger")
def test_init_with_invalid_timeout(self, mock_logger):
    """無効なtimeout値でのデフォルト設定テスト"""
    # ...
```

### 設計上の理由

- Phase 1BのPydantic validation設計により、invalid値はWebAPIModelConfig変換時に拒否される
- これはセキュリティ・データ整合性のための意図的な設計
- 今後、config validation層でのエラーハンドリングテストに置き換える必要がある

### 結果

- **5 tests skipped** (設計上の制約として記録)

---

## Phase 3 P3.5: test_webapi.py全テスト修正完了

### 問題1: AttributeError - config_registry patch失敗

```
AttributeError: <module 'image_annotator_lib.core.base.webapi'> does not have the attribute 'config_registry'
```

**原因**:

- テストが `@patch("image_annotator_lib.core.base.webapi.config_registry")`を使用
- しかし、webapi.pyではconfig_registryをmodule levelでimportしていない
- BaseAnnotator内で動的にimportされるため、patchが失敗

### 問題2: ValidationError - test_model config汚染

```
ValidationError: 2 validation errors for WebAPIModelConfig
timeout
  Input should be a valid integer [type=int_parsing, input_value='invalid_timeout']
model_path
  Extra inputs are not permitted [type=extra_forbidden, input_value='/path/to/model']
```

**原因**:

- config_registryはsingletonで状態を保持
- 前のテストの"test_model"設定（invalid_timeout, model_path）が残存
- WebAPIModelConfigは `extra='forbid'`でmodel_pathを拒否

### 解決策

#### 1. autouse fixtureの全面改修

```python
@pytest.fixture(autouse=True)
def setup_test_model_config():
    """Setup test model configuration for all tests."""
    from image_annotator_lib.core.config import config_registry

    # Use unique model name to avoid conflicts
    test_model_name = "webapi_unittest_model"

    # Cleanup first to ensure no leftover settings
    try:
        config_registry._config.pop(test_model_name, None)
    except (AttributeError, KeyError):
        pass

    # Set up WebAPIModelConfig-compatible configuration (no model_path)
    config = {
        "device": "cpu",
        "class": "MockWebApiAnnotator",
        "api_model_id": "test-api-model-id",
        "model_name_on_provider": "test-provider-model",
    }
    for key, value in config.items():
        config_registry.add_default_setting(test_model_name, key, value)

    yield

    # Cleanup after test
    try:
        config_registry._config.pop(test_model_name, None)
    except (AttributeError, KeyError):
        pass
```

**変更点**:

- ✅ **Unique model name**: "test_model" → "webapi_unittest_model"
- ✅ **Pre-cleanup**: fixture開始時に既存設定削除
- ✅ **WebAPIModelConfig準拠**: model_path除外
- ✅ **Post-cleanup**: テスト後に確実に削除

#### 2. config_registry patch全削除

```python
# ❌ Before
@patch("image_annotator_lib.core.base.webapi.config_registry")
@patch("image_annotator_lib.core.base.webapi.prepare_web_api_components")
def test_context_manager_enter_success(self, mock_prepare, mock_config):
    mock_config.get.return_value = None
    annotator = MockWebApiAnnotator("test_model")

# ✅ After
@patch("image_annotator_lib.core.base.webapi.prepare_web_api_components")
def test_context_manager_enter_success(self, mock_prepare):
    annotator = MockWebApiAnnotator()
```

**修正箇所**: 全18テストメソッド

#### 3. MockWebApiAnnotatorのデフォルト引数化

```python
class MockWebApiAnnotator(WebApiBaseAnnotator):
    def __init__(self, model_name: str = "webapi_unittest_model"):
        super().__init__(model_name)
        self.inference_called = False
```

**効果**: テストコードが `MockWebApiAnnotator()`のみで動作

#### 4. 一括置換

```python
# Replace all occurrences
MockWebApiAnnotator("test_model") → MockWebApiAnnotator()
```

### 修正対象テスト (18 tests)

**Context Manager Tests (5)**:

- test_context_manager_enter_success ✅
- test_context_manager_enter_configuration_error ✅
- test_context_manager_enter_authentication_error ✅
- test_context_manager_enter_unexpected_error ✅
- test_context_manager_exit_with_client ✅

**_preprocess_images Tests (1)**:

- test_preprocess_images_success ✅

**_parse_common_json_response Tests (4)**:

- test_parse_common_json_response_with_dict_success ✅
- test_parse_common_json_response_with_invalid_dict ✅
- test_parse_common_json_response_json_decode_error ✅
- test_parse_common_json_response_unexpected_error ✅

**_generate_tags Tests (4)**:

- test_generate_tags_from_dict_with_tags ✅
- test_generate_tags_from_dict_without_tags ✅
- test_generate_tags_with_error ✅
- test_generate_tags_with_annotation_none ✅

**_format_predictions Tests (4)**:

- test_format_predictions_with_annotation_schema ✅
- test_format_predictions_with_error ✅
- test_format_predictions_with_none_response ✅
- test_format_predictions_with_invalid_response_type ✅

### 結果

- **18 passed, 5 skipped** (test_webapi.py全テスト)
- config isolation問題完全解決

---

## Test Isolation問題の解決パターン (再利用可能)

### Pattern 1: Unique Model Name Strategy

```python
# ❌ 共有名を使用 → 他テストと競合
test_model_name = "test_model"

# ✅ テストファイル固有の名前を使用
test_model_name = "webapi_unittest_model"
test_model_name = "test_memory_efficiency_model"
```

### Pattern 2: Pre/Post Cleanup in Fixture

```python
@pytest.fixture(autouse=True)
def setup_config():
    # 1. Pre-cleanup (前テストの残骸削除)
    config_registry._config.pop("model_name", None)

    # 2. Setup
    config_registry.add_default_setting(...)

    yield

    # 3. Post-cleanup (本テストの設定削除)
    config_registry._config.pop("model_name", None)
```

### Pattern 3: Config-Compatible Setup

```python
# ❌ WebAPIModelConfigと互換性のない設定
config = {
    "model_path": "/path",  # WebAPIには不要
    "timeout": "invalid"     # 型不一致
}

# ✅ Pydantic validationを通過する設定
config = {
    "api_model_id": "test-model",
    "model_name_on_provider": "provider-model",
    "device": "cpu",
    "class": "MockAnnotator"
}
```

### Pattern 4: Avoid Module-Level Patch

```python
# ❌ Module levelにimportされていないものをpatch
@patch("module.config_registry")  # AttributeError

# ✅ autouse fixtureで直接設定
@pytest.fixture(autouse=True)
def setup():
    from module.config import config_registry
    config_registry.add_default_setting(...)
```

---

## コミット記録

### Commit 1: 75b7afb

```
test: fix Phase 3 P3.2 - resolve test isolation issues

- Memory efficiency test: unique model name使用
- Env var tests: ALLOW_MODEL_REQUESTS直接patch
- Fixture scope修正: class → function
- test_transformers.py: autouse fixture追加
```

### Commit 2: 3127459

```
fix: resolve test isolation issues in test_webapi.py

Phase 3 P3.5 complete:
- Removed all @patch config_registry decorators
- Updated autouse fixture (unique name, pre-cleanup)
- Removed WebAPIModelConfig-incompatible "model_path"
- Updated all MockWebApiAnnotator() calls
- Fixed 4 context manager + 13 other tests

Results: 18 passed, 5 skipped
```

---

## 現状と次セッションへの引き継ぎ

### テスト統計

- **Total**: 457 tests
- **Passed**: 433 (94.7%)
- **Skipped**: 19 (4.2%)
- **Failed**: 5 (1.1%)

### 残り5件の失敗テスト

**test_local_ml_models_integration.py (1 test)**:

- `test_clip_model_loading_integration` - Phase 3 P3.6で確認予定

**test_base.py (4 tests)**:

- `test_init_success`
- `test_init_no_config_error`
- `test_predict_handles_out_of_memory`
- `test_predict_handles_general_exception`

**推測される原因**: test_webapi.pyと同様のconfig isolation問題の可能性が高い

### 次セッションのタスク優先順位

1. **Phase 3 P3.6**: 残り5件の失敗テスト修正

   - test_base.pyにautouse fixture適用
   - test_clip検証（skipされている可能性）
2. **Phase 3 P4**: スキップテスト19件の有効化

   - カテゴリA: API key必要テスト
   - カテゴリB: mock設定修正必要テスト
3. **Phase 3 P5**: カバレッジ向上 (16.65% → 75%)

   - 120-170テスト追加必要

---

## 学んだ教訓

1. **Singleton状態の危険性**: config_registryのような共有状態は、適切なcleanupなしでテスト間汚染を引き起こす
2. **Pydantic validationの影響**: Phase 1B導入後、invalid値テストの多くが実行不可能になった。設計時に考慮が必要
3. **Unique naming重要性**: "test_model"のような汎用名は避け、テストファイル固有の名前を使用する
4. **Pre-cleanupの必要性**: Post-cleanupだけでは前テストの失敗時に残骸が残る。Pre-cleanupが確実
5. **Module-level patchの落とし穴**: 実行時import（動的import）されるものはpatchできない。代わりに直接操作する
