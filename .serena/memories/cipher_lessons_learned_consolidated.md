# LoRAIro Lessons Learned (Cipher統合記録)

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## Architecture Lessons

### State Management
- Use `DatasetStateManager` (centralized), NOT `WorkflowStateManager` (deprecated)
- `src/lorairo/gui/state/workflow_state.py` = dead code

### Incremental Refactoring
- Phase 1: Service extraction → Phase 2: Controller introduction → Phase 3: Final polish
- Phased approach prevents breaking changes

### Dependency Injection
- Controller/Service via ServiceContainer
- Separates PySide6-specific logic from domain logic

## PydanticAI Testing Lessons (2025-07-01)

### Problem
Memory management integration tests: high failure rates due to complex mocks, misunderstanding test patterns

### Best Practices
- Use TestModel/FunctionModel for LLM mocks
- Use Agent.override() for model replacement
- Prevent real API calls with models.ALLOW_MODEL_REQUESTS=False
- Do NOT mock internal PydanticAI Agent directly

### Test Design Principles
1. Understanding First, Not Test First
2. Incremental Complexity
3. Test Public Interfaces (not implementation details)
4. Respect Framework Best Practices

### Error Pattern Classification
- Configuration: "base_model が設定されていません" → verify required params
- Mock: "MagicMock can't be used in await" → use correct PydanticAI test patterns
- Class Registration: "Model not found" → pre-configure test class mapping

## Phase C Testing Lessons (2025-12-05)
- **Worked**: Shared fixtures, Level 1-3 mock strategy, incremental testing, docstring docs
- **Didn't work**: Complex API error tests, ambitious 75% target, solid color pHash test
- **Future**: Start with coverage analysis, create model fixtures first, realistic targets

## pytest-bdd Known Issue
- Japanese + <param> notation causes parsing failures
- Workaround: English steps, concrete values, or regex steps

## Legacy Library Integration History
- image-annotator-lib = consolidated scorer_wrapper_lib + tagger_wrapper_lib
- Class hierarchy optimization, result format unification, memory management improvement
