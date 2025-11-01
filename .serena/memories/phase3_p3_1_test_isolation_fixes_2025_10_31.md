# Phase 3 P3.1: Test Isolation Fixes (2025-10-31)

## Context
After Phase 3 P3 fixes that added `model_name_on_provider` requirement, 10 new test failures emerged. This was because the validation logic in `ModelConfigFactory.from_registry()` now requires either `model_path` OR `model_name_on_provider`.

## Root Cause Analysis
Tests were using `@patch("image_annotator_lib.core.base.annotator.config_registry")` and only mocking `.get()` method. However, after ModelConfigFactory integration, the code path changed to use `config_registry.get_all_config()` which returns the entire config dict.

## Solution Implemented

### 1. Created Helper Function
```python
def setup_mock_config_registry(mock_config, model_config: dict[str, Any]):
    """Helper to setup mock config_registry with get_all_config."""
    mock_config.get_all_config.return_value = {"test_model": model_config}
```

### 2. Updated test_annotator.py
- Fixed all 18 BaseAnnotator tests
- Changed mock setup from `.get.side_effect` to `.get_all_config.return_value`
- All tests now pass individually: **18/18 ✓**
- Commit: `4b0ad76`

### 3. Updated test_api.py
- Added `setup_test_model_configs` autouse fixture
- Configured 5 test models with proper structure
- Commit: `5a20f7a` (previous)

## Current Status

### Test Results (Full Suite)
- **401 passed** (up from 384)
- **5 failed** (down from 10)
- **16 skipped**
- **+17 passing** tests compared to previous run

### Remaining Failures (Test Isolation Issues)
All 5 tests pass individually but fail in full suite:

1. `test_memory_management_integration.py::test_pydantic_ai_annotator_memory_efficiency`
2. `test_pydantic_ai_factory.py::test_create_agent_sets_openai_env_var`
3. `test_pydantic_ai_factory.py::test_create_agent_sets_anthropic_env_var`
4. `test_pydantic_ai_factory.py::test_create_agent_sets_google_env_var`
5. `test_transfomers.py::test_preprocess_images_calls_processor`

## Test Isolation Issue Pattern

**Symptom**: Tests pass individually but fail in full suite
**Likely Causes**:
- Shared state in config_registry not properly cleaned up
- Environment variables persisting between tests
- Cached provider instances not cleared
- Mock patches interfering with each other

## Next Steps

### Phase 3 P3.2: Fix Test Isolation (Priority 1)
1. Investigate conftest.py `reset_global_state` fixture
2. Add cleanup for:
   - Environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
   - Provider cache in PydanticAIProviderFactory
   - Agent cache
   - Config registry state
3. Consider using `pytest-xdist` for isolated test execution
4. Verify all 5 tests pass in full suite

### Phase 3 P4-P7: Remaining Work
- P4: Enable 16 skipped tests
- P5: Increase coverage 16.65% → 75%
- P6: LoRAIro integration
- P7: CI/CD setup

## Technical Notes

### ModelConfigFactory Behavior
```python
# In BaseAnnotator.__init__:
registry_dict = config_registry.get_all_config().get(model_name)
return ModelConfigFactory.from_registry(model_name, registry_dict)

# ModelConfigFactory.from_registry validates:
if "model_name_on_provider" in config_dict:
    return WebAPIModelConfig(**config_dict)
elif "model_path" in config_dict:
    return LocalMLModelConfig(**config_dict)
else:
    raise ConfigurationError("Missing model_path or model_name_on_provider")
```

### Mock Setup Pattern
```python
# OLD (wrong):
mock_config.get.side_effect = lambda model, key, default: values[key]

# NEW (correct):
mock_config.get_all_config.return_value = {
    "test_model": {
        "model_path": "/path/to/model",
        "device": "cpu",
        "class": "MockAnnotator"
    }
}
```
