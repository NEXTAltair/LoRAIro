# Integration Test Plan: image-annotator-lib Coverage 75% Achievement

**作成日**: 2025-12-03
**ブランチ**: `feature/annotator-library-integration`
**目標**: テストカバレッジ 20.36% → 75%以上達成
**方針**: 統合テスト（モックのみ）+ ユニットテスト拡充

---

## Current Status

### Achieved (Phase 1 & 3)
- ✅ 開発環境整備完了
- ✅ LoRAIro統合実装完了（AnnotatorLibraryAdapter, AnnotationLogic, AnnotationWorker）
- ✅ Context manager robustness fix完了（2025-12-03）

### Outstanding (Phase 2)
- ❌ テストカバレッジ 20.36% / 75%目標
- ✅ 642 tests collected
- ✅ Context manager robustness tests追加済み（4 tests）

---

## Test Coverage Gap Analysis

### Current Test Structure

**image-annotator-lib tests/** (45 files):
```
tests/
├── integration/          # 14 files（モックテスト）
│   ├── test_context_manager_robustness.py (NEW)
│   ├── test_anthropic_api_annotator_integration.py
│   ├── test_google_api_annotator_integration.py
│   ├── test_provider_manager_integration.py
│   ├── test_pydantic_ai_factory_integration.py
│   └── ...
├── unit/                 # ユニットテスト
│   ├── core/
│   │   ├── test_model_factory.py
│   │   ├── test_provider_manager.py
│   │   ├── test_pydantic_ai_factory.py
│   │   └── base/
│   ├── fast/
│   └── fixtures/
├── features/             # BDD tests
└── conftest.py
```

### Coverage Gaps (推定)

**High Priority (Core Components):**
1. `core/model_factory.py` - LRU cache, memory management
2. `core/base/annotator.py` - Base class device validation
3. `core/base/webapi.py` - WebAPI base class
4. `core/pydantic_ai_factory.py` - Agent caching logic
5. `core/provider_manager.py` - Provider routing

**Medium Priority:**
6. Model classes (`model_class/`) - Concrete annotators
7. `core/config.py` - Configuration management
8. `core/registry.py` - Model registry
9. Error handling paths - `exceptions/errors.py`

**Low Priority:**
10. Utility functions (`core/utils.py`)

---

## Test Strategy

### Test Policy (2025-11-06準拠 + 修正)

**ユニットテスト** (`@pytest.mark.unit`):
- 単一クラス/関数テスト
- 外部依存のみモック

**統合テスト** (`@pytest.mark.integration + @pytest.mark.fast_integration`):
- **API呼び出しのみモック** (実API禁止)
- **内部リソース（キャッシュ、メモリ、デバイス切替）は実物使用**
- CI/CD常時実行可能
- 実行時間: 数秒〜数十秒

**LoRAIro統合テスト** (`tests/integration/` - LoRAIro側):
- LoRAIro本体→image-annotator-lib の結合パステスト
- AnnotationService/Worker経由の呼び出し検証
- 実コンポーネント使用（API呼び出しのみモック）

**E2Eテスト** (`@pytest.mark.bdd` in `tests/features/`):
- 実API使用
- BDDシナリオ
- APIキー必須環境のみ

### Coverage Target Distribution

| カテゴリ | 現在 | 目標 | 追加テスト数（推定） |
|---------|------|------|---------------------|
| Core Components | ~15% | 80% | +30 tests |
| Base Classes | ~25% | 80% | +20 tests |
| Model Classes | ~10% | 70% | +25 tests |
| Utilities | ~30% | 75% | +10 tests |
| **Total** | **20.36%** | **75%+** | **+85 tests** |

---

## Implementation Plan: 3 Phases

### Phase A: Fixture Setup + Core Component Unit Tests (Priority 1)

**Target:** テストインフラ整備 + Core機能カバー（カバレッジ20% → 45%）

**Tasks (前提条件):**
0. **Fixture実装** (`conftest.py`)
   - `managed_config_registry()` - テスト用設定レジストリ
   - `mock_model_components()` - モックモデルコンポーネント
   - `mock_cuda_available()` / `mock_cuda_unavailable()` - CUDA環境モック
   - API: 設定登録、クリーンアップ、モック提供
   - **Estimated**: 1-2 hours

**Tasks (Unit Tests):**
1. `test_model_factory.py` 拡充
   - LRU cache eviction logic
   - Memory estimation accuracy
   - CUDA/CPU device switching
   - Cache state transitions

2. `test_pydantic_ai_factory.py` 拡充
   - Agent caching LRU strategy
   - Configuration change detection
   - Provider instance reuse

3. `test_provider_manager.py` 拡充
   - Model ID routing logic
   - Provider detection (OpenAI, Anthropic, Google, OpenRouter)
   - Error propagation

4. `test_base_annotator_di.py` 拡充
   - Device validation paths
   - Config loading edge cases
   - Error handling

**Estimated:** 30 new unit tests

---

### Phase B: Integration Tests Expansion (Priority 2)

**Target:** コンポーネント間連携をカバー（カバレッジ45% → 65%）

**Tasks (image-annotator-lib internal):**
1. `test_context_manager_lifecycle_integration.py` (NEW)
   - Full lifecycle: __init__ → __enter__ → annotate → __exit__
   - **実コンポーネント**: Memory state transitions (CPU/CUDA)
   - **実コンポーネント**: Device fallback scenarios
   - Error recovery paths

2. `test_model_factory_integration.py` (拡充)
   - Multi-model concurrent loading (**実キャッシュ使用**)
   - Cache eviction under memory pressure (**実LRU動作検証**)
   - Device fallback scenarios (**実CUDA/CPU切替**)

3. `test_cross_provider_integration.py` (拡充)
   - Sequential provider switching (**実Provider instances**)
   - Configuration consistency
   - Error isolation between providers

4. `test_pydantic_ai_integration.py` (NEW)
   - Agent creation → caching → reuse flow (**実Agent cache**)
   - Configuration change detection → cache invalidation
   - Provider instance sharing verification

**Tasks (LoRAIro integration - NEW):**
5. `tests/integration/test_lorairo_annotation_integration.py` (NEW - LoRAIro側)
   - AnnotationService → AnnotatorLibraryAdapter 呼び出し
   - AnnotationWorker → AnnotationLogic 実行フロー
   - DB保存 + キャッシュ更新パス検証
   - pHash整合性検証（LoRAIro計算 vs Library計算）

**Estimated:** 30 new integration tests (library 25 + LoRAIro 5)

---

### Phase C: Model Class & Edge Case Tests (Priority 3)

**Target:** Concrete models + edge casesをカバー（カバレッジ65% → 75%+）

**Tasks:**
1. Model class unit tests
   - `model_class/tagger_*` concrete implementations
   - `model_class/scorer_*` concrete implementations
   - `model_class/annotator_webapi/*` PydanticAI models

2. Edge case & error path tests
   - Invalid configuration handling
   - Missing model files
   - API authentication failures (mocked)
   - Memory allocation failures

3. Utility & helper tests
   - `core/utils.py` - device detection, pHash calculation
   - `core/config.py` - TOML parsing, validation

**Estimated:** 30 new tests

---

## Test Implementation Guidelines

### Fixture Strategy

**既存fixtures** (`conftest.py`):
```python
@pytest.fixture(autouse=True)
def reset_global_state(request):
    # グローバル状態リセット（既存）
    ...
```

**新規fixtures実装必須** (`conftest.py` - Phase A Task 0):
```python
@pytest.fixture
def managed_config_registry():
    """テスト用設定レジストリ
    
    API:
    - registry.set(model_name, config_dict) - 設定登録
    - registry.get(model_name, key, default) - 設定取得
    - Teardown: テスト終了時に自動クリーンアップ
    
    Usage:
        def test_foo(managed_config_registry):
            managed_config_registry.set("test_model", {
                "model_path": "test/path",
                "device": "cpu",
            })
            # Test with registered config
    """
    from image_annotator_lib.core.config import config_registry
    # Implementation details in Phase A
    ...

@pytest.fixture
def mock_model_components():
    """モックモデルコンポーネント（Pipeline/Transformers）"""
    return {
        "model": MagicMock(),
        "processor": MagicMock(),
        "pipeline": MagicMock(),
    }

@pytest.fixture
def mock_cuda_available(monkeypatch):
    """CUDA利用可能環境のモック"""
    monkeypatch.setattr("torch.cuda.is_available", lambda: True)

@pytest.fixture
def mock_cuda_unavailable(monkeypatch):
    """CUDA利用不可環境のモック"""
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
```

### Test Pattern Templates

**ユニットテスト（単一クラス）:**
```python
@pytest.mark.unit
def test_model_factory_lru_eviction():
    # Setup: Fill cache to capacity
    # Act: Add one more model (trigger eviction)
    # Assert: Least recently used model evicted
    ...
```

**統合テスト（コンポーネント連携）:**
```python
@pytest.mark.integration
@pytest.mark.fast_integration
def test_annotator_full_lifecycle_with_mocks():
    with patch("...load_transformers_components") as mock_load:
        mock_load.return_value = mock_components

        # Full lifecycle test
        annotator = ConcreteAnnotator("model_name")
        with annotator:
            results = annotator.annotate(images)

        # Verify interactions
        assert mock_load.called
        ...
```

---

## Success Criteria

### Phase A (Core Unit Tests)
- ✅ +30 unit tests added
- ✅ Coverage: 45%+ achieved
- ✅ All new tests pass
- ✅ No regression in existing tests

### Phase B (Integration Tests)
- ✅ +30 integration tests added (library 25 + LoRAIro 5)
- ✅ Coverage: 65%+ achieved
- ✅ API calls mocked, internal resources use real components
- ✅ LoRAIro統合パス検証完了
- ✅ CI/CD compatible (no API keys required)

### Phase C (Model & Edge Cases)
- ✅ +30 tests added (model classes + edge cases)
- ✅ Coverage: 75%+ achieved
- ✅ All error paths tested
- ✅ All existing 642 tests still pass

### Final Validation
- ✅ `uv run pytest local_packages/image-annotator-lib/tests/ --cov` → Coverage ≥75%
- ✅ `uv run pytest -m unit` → All pass
- ✅ `uv run pytest -m fast_integration` → All pass
- ✅ `uv run ruff check` → No issues
- ✅ `uv run mypy src/` → No errors

---

## Files to Modify/Create

### Existing Files to Expand

**image-annotator-lib:**
1. `local_packages/image-annotator-lib/tests/conftest.py` - Fixture実装
2. `local_packages/image-annotator-lib/tests/unit/core/test_model_factory.py` - LRU cache tests
3. `local_packages/image-annotator-lib/tests/unit/core/test_pydantic_ai_factory.py` - Agent caching tests
4. `local_packages/image-annotator-lib/tests/unit/core/test_provider_manager.py` - Routing tests
5. `local_packages/image-annotator-lib/tests/unit/core/test_base_annotator_di.py` - Device validation tests
6. `local_packages/image-annotator-lib/tests/integration/test_cross_provider_integration.py` - Provider switching tests
7. `local_packages/image-annotator-lib/tests/integration/test_model_factory_integration.py` - Memory management tests

### New Files to Create

**image-annotator-lib:**
8. `local_packages/image-annotator-lib/tests/integration/test_context_manager_lifecycle_integration.py` - Full lifecycle tests
9. `local_packages/image-annotator-lib/tests/integration/test_pydantic_ai_integration.py` - Agent caching integration
10. `local_packages/image-annotator-lib/tests/unit/model_class/test_tagger_models.py` - Tagger concrete tests
11. `local_packages/image-annotator-lib/tests/unit/model_class/test_scorer_models.py` - Scorer concrete tests
12. `local_packages/image-annotator-lib/tests/unit/model_class/test_webapi_models.py` - PydanticAI model tests
13. `local_packages/image-annotator-lib/tests/unit/core/test_error_paths.py` - Edge case & error tests

**LoRAIro:**
14. `tests/integration/test_lorairo_annotation_integration.py` - LoRAIro→library統合テスト

---

## Risk Mitigation

### Risk 1: Time Constraint (85 tests estimation)
**Mitigation:**
- Prioritize Phase A (core components)
- Use test templates for repetitive patterns
- Leverage existing mock fixtures

### Risk 2: Test Fragility
**Mitigation:**
- Follow LoRAIro test guidelines (75%+ coverage)
- Use `@pytest.mark.fast_integration` for CI
- Avoid real API dependencies

### Risk 3: Regression
**Mitigation:**
- Run full test suite after each phase
- Monitor coverage report changes
- Use `reset_global_state` fixture

---

## Timeline Estimate (修正版)

- **Phase A**: 
  - Fixture実装: 1-2 hours
  - Unit tests: 3-4 hours
  - **Subtotal**: 4-6 hours

- **Phase B**: 
  - image-annotator-lib integration: 4-5 hours
  - LoRAIro integration: 2-3 hours
  - **Subtotal**: 6-8 hours

- **Phase C**: 
  - Model class tests: 2-3 hours
  - Edge case tests: 2-3 hours
  - **Subtotal**: 4-6 hours

**Total**: 14-20 hours (full coverage achievement)

---

## Next Steps After Plan Approval

1. Implement Phase A (Core unit tests)
2. Verify coverage increase (20% → 45%)
3. Implement Phase B (Integration tests)
4. Verify coverage increase (45% → 65%)
5. Implement Phase C (Model & edge tests)
6. Final verification: Coverage ≥75%
7. Update `.serena/memories/` with completion record

---

**計画策定日**: 2025-12-03
**優先度**: High (Phase 2 completion blocker)
**方針**: 段階的実装、各Phase後に検証
**実装予定**: 承認後即時実施（3フェーズ）
