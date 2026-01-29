# LoRAIro Testing Strategy (Cipher統合記録)

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## Test Policy (2025-11-06)

**Unit**: Single class/function, mock external only, real internal logic
**Integration**: API calls ONLY mocked, internal resources real, CI/CD runnable
**E2E/BDD**: Real API usage, requires API keys

## Coverage Standards
- Target: 75%+
- Status (Phase C): 69% (4855 stmts, 1491 missed)
- Total: 721 tests (713 passed, 1 failed, 7 skipped)

## Mock Strategy (Phase C)

### Level 1: Mock External Library Loading
onnxruntime.InferenceSession, transformers.AutoModel, torch.cuda.*

### Level 2: Mock Inference Execution
model.forward(), session.run(), pydantic_ai.Agent.run()

### Level 3: Use Real Internal Logic
Image preprocessing, score normalization, config loading, device determination

## Coverage Gap Analysis (Top Gaps)
1. model_factory.py: 47% (710 stmts)
2. api_model_discovery.py: 15% (149 stmts)
3. tagger_transformers.py: 35%
4. openai_api_chat.py: 17%
5. simplified_agent_wrapper.py: 26%

## High Coverage Modules
- base/annotator.py: 100%
- types.py: 99%
- error_messages.py: 98%
- pydantic_ai_factory.py: 96%

## Path to 75%
- Model Factory Integration Tests (12 tests)
- Model Inference Tests (8 tests)
- API Discovery Tests (6 tests)
- WebAPI Integration Tests (8 tests)
- Registry Tests (6 tests)
