
# Phase C: Model Class & Edge Case Test Implementation Plan (2025-12-04)

**プロジェクト**: image-annotator-lib
**ブランチ**: feature/phase2-test-fixes
**目標**: カバレッジ 65% → 75%以上 (+30テスト)
**前提**: Phase A & B完了（Core unit tests + Integration tests実装済み）

---

## Phase C概要

### Phase B完了状態
- ✅ Phase B完了: 25/25統合テスト実装済み
- ✅ 現在カバレッジ: ~65% (Phase A 45% + Phase B 20%)
- ✅ 684 total tests passing
- ✅ Core modules高カバレッジ達成:
  - pydantic_ai_factory.py: 86%
  - provider_manager.py: 83%
  - model_config.py: 92%

### Phase Cカバレッジギャップ
**High Priority (カバレッジ低)**:
1. `model_class/` モジュール群: ~10-20% → **目標70%**
   - tagger_onnx.py
   - tagger_transformers.py
   - pipeline_scorers.py
   - scorer_clip.py
   - pydantic_ai_webapi_annotator.py

2. Error handling paths: ~0% → **目標80%**
   - 例外処理パス
   - 境界値・異常入力

3. Utility modules: 47% → **目標75%**
   - core/utils.py (device detection, pHash)
   - core/config.py (TOML parsing)

---

## 3つのテストカテゴリ（30テスト、~800行）

### Category 1: Model Class Unit Tests (15 tests)

**フォーカス**: Concrete model implementations

#### 1.1 ONNX Tagger Tests (5 tests) - NEW
**File**: `tests/unit/model_class/test_tagger_onnx.py`

**Tests**:
1. `test_onnx_tagger_initialization_success()`
   - ONNX model initialization
   - Session creation with providers
   - Input/output tensor shapes

2. `test_onnx_tagger_preprocessing()`
   - Image preprocessing pipeline
   - Tensor conversion (PIL → numpy → ONNX)
   - Batch processing

3. `test_onnx_tagger_inference()`
   - Mock ONNX session inference
   - Output postprocessing
   - Tag extraction from predictions

4. `test_onnx_tagger_batch_processing()`
   - Multiple images handling
   - Batch size optimization
   - Memory efficiency

5. `test_onnx_tagger_error_handling()`
   - Invalid model path
   - Corrupted model file
   - Inference failures

**Mock Strategy**:
- Mock: `onnxruntime.InferenceSession`
- Real: Preprocessing, postprocessing, config loading

---

#### 1.2 Transformers Tagger Tests (5 tests) - NEW
**File**: `tests/unit/model_class/test_tagger_transformers.py`

**Tests**:
1. `test_transformers_tagger_initialization()`
   - Model/processor loading
   - Device assignment (CPU/CUDA)
   - Config validation

2. `test_transformers_tagger_preprocessing()`
   - Image tensor preparation
   - Processor application
   - Normalization

3. `test_transformers_tagger_inference_mocked()`
   - Mock model forward pass
   - Logits extraction
   - Tag probability calculation

4. `test_transformers_tagger_device_handling()`
   - CPU → CUDA transfer
   - CUDA unavailable fallback
   - Device consistency checks

5. `test_transformers_tagger_memory_management()`
   - Model unloading
   - CUDA cache clearing
   - Memory leak prevention

**Mock Strategy**:
- Mock: `AutoModel.from_pretrained`, `AutoProcessor.from_pretrained`
- Real: Device handling, tensor operations

---

#### 1.3 Scorer Models Tests (5 tests) - NEW
**File**: `tests/unit/model_class/test_scorer_models.py`

**Tests**:
1. `test_pipeline_scorer_initialization()`
   - `AestheticShadow`, `CafeAesthetic` initialization
   - Pipeline creation
   - Config loading

2. `test_pipeline_scorer_prediction()`
   - Mock pipeline inference
   - Score extraction
   - Range validation (0.0-1.0)

3. `test_clip_scorer_initialization()`
   - CLIP model/processor loading
   - Device assignment
   - Embedding computation setup

4. `test_clip_scorer_aesthetic_scoring()`
   - Mock CLIP embeddings
   - Aesthetic score calculation
   - Normalization

5. `test_scorer_batch_processing()`
   - Multiple images scoring
   - Batch optimization
   - Consistent results

**Mock Strategy**:
- Mock: `pipeline()`, CLIP model forward
- Real: Score normalization, batch processing

---

### Category 2: Edge Case & Error Path Tests (10 tests)

**フォーカス**: 異常系・境界値・エラーハンドリング

**ファイル分割方針（メンテナンス性考慮）**:
- **カテゴリごとに独立ファイル**: 1ファイル3-4テストに制限
- **命名規約**: `test_{error_category}_errors.py`
- **共通fixture**: `tests/unit/core/conftest.py` に集約
- **理由**: 10テスト×平均30行 = 300行を1ファイルにすると保守困難

**共通Error Fixtures**:
```python
# tests/unit/core/conftest.py
@pytest.fixture
def mock_filesystem_error():
    """Mock filesystem errors (FileNotFoundError, PermissionError)."""
    def _mock(error_type: type, path: str):
        return error_type(f"Mock error for {path}")
    return _mock

@pytest.fixture
def mock_api_error():
    """Mock API errors (401, 429, timeout)."""
    def _mock(status_code: int | None = None, exception: Exception | None = None):
        # Implementation
        pass
    return _mock
```

#### 2.1 Configuration Error Tests (NEW)
**File**: `tests/unit/core/test_config_errors.py` (3テスト)

**Tests**:
1. `test_invalid_config_missing_required_fields()`
   - Missing `model_path` or `model_name_on_provider`
   - ConfigurationError raised
   - Clear error message

2. `test_invalid_config_wrong_types()`
   - String for numeric field
   - Pydantic validation error
   - Type coercion behavior

3. `test_invalid_config_out_of_range_values()`
   - Negative batch_size
   - timeout > max_allowed
   - ValidationError with details

---

#### 2.2 File System Error Tests (NEW)
**File**: `tests/unit/core/test_filesystem_errors.py` (3テスト)

**Tests**:
4. `test_missing_model_file_error()`
   - Model path doesn't exist
   - FileNotFoundError propagation
   - Helpful error message

5. `test_corrupted_model_file_error()`
   - Invalid ONNX/pickle file
   - RuntimeError on load
   - Graceful failure

6. `test_insufficient_disk_space_error()`
   - Mock disk full scenario
   - OSError handling
   - Cache cleanup attempt

---

#### 2.3 API & Authentication Error Tests (NEW)
**File**: `tests/unit/core/test_api_errors.py`

**Mock Strategy**:
- Mock: `pydantic_ai.Agent.run()` at module level
- Mock: HTTP client responses (status codes, exceptions)
- Real: Error handling logic, retry mechanisms
- Fixture: `mock_api_response` - Configurable HTTP response simulator

**Implementation Pattern**:
```python
@pytest.fixture
def mock_api_response():
    """Fixture to simulate API responses."""
    def _mock(status_code: int, raise_exception: Exception | None = None):
        mock_response = AsyncMock()
        mock_response.status_code = status_code
        if raise_exception:
            mock_response.side_effect = raise_exception
        return mock_response
    return _mock

@pytest.mark.unit
def test_api_authentication_failure_401(managed_config_registry, mock_api_response):
    with patch("pydantic_ai.Agent.run", side_effect=HTTPError(401)):
        # Test implementation
```

**Tests**:
7. `test_api_authentication_failure_401()`
   - Mock 401 Unauthorized via HTTPError
   - APIAuthenticationError raised
   - Retry logic NOT triggered
   - Clear error message with API provider

8. `test_api_rate_limit_429()`
   - Mock 429 Too Many Requests
   - Exponential backoff retry (1s, 2s, 4s)
   - Max retry limit (3 attempts)
   - Final RateLimitError after exhaustion

9. `test_api_timeout_error()`
   - Mock asyncio.TimeoutError
   - TimeoutError propagated
   - Configurable timeout from config
   - No retry on timeout

---

#### 2.4 Memory & Device Error Tests (NEW)
**File**: `tests/unit/core/test_memory_device_errors.py` (1テスト)

**Tests**:
10. `test_cuda_oom_fallback_to_cpu()`
    - Mock CUDA out of memory
    - Automatic CPU fallback
    - Warning logged

---

### Category 3: Utility & Helper Tests (5 tests)

**フォーカス**: core/utils.py, core/config.py 未カバー部分

#### 3.1 Utils Module Tests (EXPAND)
**File**: `tests/unit/core/test_utils.py`

**Tests** (3 new):
1. `test_calculate_phash_consistency()`
   - Same image → same pHash
   - Different images → different pHash
   - Hamming distance properties

2. `test_determine_effective_device_logic()`
   - CUDA available + config="cuda" → "cuda"
   - CUDA unavailable + config="cuda" → "cpu" (fallback)
   - Config="cpu" → always "cpu"

3. `test_download_file_caching()`
   - File cached → skip download
   - Cache miss → perform download
   - Cache validation (hash check)

---

#### 3.2 Config Module Tests (EXPAND)
**File**: `tests/unit/core/test_config.py`

**Tests** (2 new):
4. `test_load_config_from_toml_file()`
   - Valid TOML → correct parsing
   - Invalid TOML → TOMLDecodeError
   - Missing file → FileNotFoundError

5. `test_config_registry_isolation()`
   - Test-specific registry
   - No cross-test contamination
   - Proper cleanup

---

## 実装順序と工数見積もり

### Day 1 (3-4時間): ONNX & Transformers Taggers
- Task 1.1: test_tagger_onnx.py (5テスト) - 1.5時間
- Task 1.2: test_tagger_transformers.py (5テスト) - 1.5-2時間
- **小計**: 3-3.5時間、検証30分

### Day 2 (3-4時間): Scorers & Configuration Errors
- Task 1.3: test_scorer_models.py (5テスト) - 1.5時間
- Task 2.1: test_config_errors.py (3テスト) - 1-1.5時間
- **小計**: 2.5-3時間、検証30分

### Day 3 (3-4時間): File System & API Errors
- Task 2.2: test_filesystem_errors.py (3テスト) - 1-1.5時間
- Task 2.3: test_api_errors.py (3テスト) - 1.5-2時間
- **小計**: 2.5-3.5時間、検証30分

### Day 4 (2-3時間): Memory/Device Errors & Utilities
- Task 2.4: test_memory_device_errors.py (1テスト) - 0.5時間
- Task 3.1-3.2: Utils & Config tests (5テスト) - 1.5-2時間
- **小計**: 2-2.5時間、検証30分

### 総工数見積もり
- **実装**: 11-14時間（4日間、1日3-3.5時間）
- **検証・修正**: 2-3時間
- **Total**: 13-17時間

**実装可能スケジュール**: 4-5営業日（1日3時間ペース）

---

## 成功基準

### テスト品質
- ✅ 各テストに明確なdocstring (目的・Mock戦略・検証項目)
- ✅ `@pytest.mark.unit` マーカー
- ✅ 既存fixturesの活用 (`managed_config_registry`, `mock_cuda_*`)
- ✅ Mock最小限（外部依存のみ）

### カバレッジ目標
- ✅ プロジェクト全体: 65% → **75%以上**
- ✅ `model_class/` modules: 10-20% → **70%**
- ✅ Error handling paths: 0% → **80%**
- ✅ `core/utils.py`: 47% → **75%**
- ✅ `core/config.py`: 47% → **75%**

### 実行検証コマンド

#### Phase Cテスト実行
```bash
# Model class tests
uv run pytest local_packages/image-annotator-lib/tests/unit/model_class -v

# Error path tests (all categories)
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_config_errors.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_filesystem_errors.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_api_errors.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_memory_device_errors.py -v

# Utility tests
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_utils.py -v
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_config.py -v
```

#### カバレッジ検証（ファイル・ディレクトリ単位）

**1. model_class/ ディレクトリ（目標70%）**
```bash
uv run pytest local_packages/image-annotator-lib/tests \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/model_class \
  --cov-report=term-missing \
  --no-cov-on-fail

# Expected output:
# tagger_onnx.py         120  36  70%
# tagger_transformers.py 150  45  70%
# scorer_clip.py         100  30  70%
```

**2. Error handling paths（目標80%）**
```bash
# Config errors coverage
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_config_errors.py \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/core/model_config.py \
  --cov-report=term-missing

# API errors coverage
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_api_errors.py \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/core/base/pydantic_ai_annotator.py \
  --cov-report=term-missing
```

**3. Utils & Config（目標75%）**
```bash
uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_utils.py \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/core/utils.py \
  --cov-report=term-missing

uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_config.py \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib/core/config.py \
  --cov-report=term-missing
```

**4. 全体カバレッジ（目標75%以上）**
```bash
uv run pytest local_packages/image-annotator-lib/tests \
  --cov=local_packages/image-annotator-lib/src/image_annotator_lib \
  --cov-report=term \
  --no-cov-on-fail | grep -E "(TOTAL|model_class|utils\.py|config\.py)"
```

---

## テスト実装ガイドライン

### Mock戦略（統一方針）

**Phase C統一Mock Policy**:
1. **外部ライブラリのみMock**: ONNX/Transformers/CLIP/PydanticAI
2. **内部ロジックは実物使用**: 前処理、後処理、設定読込、デバイス判定
3. **Mock対象の明確化**: 各テストのdocstringに記載必須

**Mock Level定義**:
```python
# Level 1: Model Loading (常にMock)
@patch("onnxruntime.InferenceSession")
@patch("transformers.AutoModel.from_pretrained")
@patch("transformers.pipeline")

# Level 2: Inference (常にMock)
mock_model.return_value = mock_output  # 推論結果のみ差し替え

# Level 3: Internal Logic (実物使用)
# - Image preprocessing (PIL → Tensor)
# - Output postprocessing (Logits → Tags)
# - Config loading (config_registry)
# - Device determination (torch.cuda.is_available)
```

**Mock最小限の原則**:
- ファイルI/O・ネットワーク・重い計算のみMock
- ビジネスロジック・条件分岐は実物でテスト
- Mockしたらdocstringに理由を明記

### Model Class Tests Pattern

```python
@pytest.mark.unit
def test_onnx_tagger_initialization_success(managed_config_registry):
    """Test ONNX tagger successful initialization.

    Mock Strategy:
    - Mock: onnxruntime.InferenceSession
    - Real: Config loading, path validation

    Scenario:
    1. Configure ONNX model
    2. Mock session creation
    3. Initialize tagger
    4. Verify session created with correct providers
    """
    # Setup
    config = {
        "class": "OnnxTaggerAnnotator",
        "model_path": "test/path/model.onnx",
        "device": "cpu",
    }
    managed_config_registry.set("test_onnx", config)

    # Mock
    with patch("onnxruntime.InferenceSession") as mock_session:
        mock_session.return_value = MagicMock()

        # Act
        tagger = OnnxTaggerAnnotator("test_onnx")

        # Assert
        assert tagger.model_path == "test/path/model.onnx"
        mock_session.assert_called_once()
```

### Error Path Tests Pattern

```python
@pytest.mark.unit
def test_missing_model_file_error(managed_config_registry):
    """Test FileNotFoundError when model file missing.

    Scenario:
    1. Configure with non-existent path
    2. Attempt initialization
    3. Verify FileNotFoundError raised
    4. Check error message includes path
    """
    config = {
        "class": "TransformersTaggerAnnotator",
        "model_path": "/nonexistent/path",
        "device": "cpu",
    }
    managed_config_registry.set("missing_model", config)

    # Act & Assert
    with pytest.raises(FileNotFoundError) as exc_info:
        tagger = TransformersTaggerAnnotator("missing_model")
        tagger.__enter__()  # Trigger loading

    assert "/nonexistent/path" in str(exc_info.value)
```

---

## 重要なファイル参照

### Phase A & B成果物（再利用）
- `tests/conftest.py` - `managed_config_registry`, `mock_cuda_*`, `mock_model_components`
- `tests/integration/conftest.py` - Integration-specific fixtures

### 既存ユニットテスト参考
- `tests/unit/model_class/test_tagger_tensorflow.py` - TensorFlow tagger tests
- `tests/unit/core/test_base_annotator_di.py` - DI pattern tests

### 実装ファイル
- `src/image_annotator_lib/model_class/*.py` - Concrete model implementations
- `src/image_annotator_lib/core/utils.py` - Utility functions
- `src/image_annotator_lib/core/config.py` - Configuration management

---

## リスク軽減策

### Phase C固有リスク

**Risk 1: Model Dependencies (TensorFlow, ONNX, Transformers)**
- **Mitigation**: Mock all model loading/inference
- Use `unittest.mock.patch` at import level
- Test only our wrapper code, not libraries

**Risk 2: CUDA/GPU Testing**
- **Mitigation**: Use `mock_cuda_available/unavailable` fixtures
- Test device logic without real GPU
- Verify fallback behavior

**Risk 3: Test Data Requirements**
- **Mitigation**: Use `lightweight_test_images` fixture
- Generate minimal synthetic images
- Focus on logic, not actual inference quality

---

## 見積もり（修正版）

- **テスト数**: 30個
- **コード量**: ~800行
- **実装工数**: 11-14時間（4-5営業日、1日3時間ペース）
- **検証・修正**: 2-3時間
- **総工数**: 13-17時間
- **カバレッジ向上**: +10 percentage points (65% → 75%+)

---

## 次ステップ

1. Week 1: Model class tests (15テスト)
2. Week 2: Error path tests (10テスト)
3. Week 3: Utility tests (5テスト)
4. Final verification: Coverage ≥75%
5. Update completion記録

---

**計画策定日**: 2025-12-04
**次のステップ**: `/implement` コマンドで実装開始
**完了条件**: 全30テスト合格 + カバレッジ75%以上達成
