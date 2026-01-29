# LoRAIro Project Status - December 2025 (Cipher統合記録)

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)
**Branch**: feature/annotator-library-integration

---

## Key Milestones (as of 2025-12-08)

### MainWindow: 688 lines (58.2% reduction from 1,645)
### Test Coverage: 69% (target 75% not yet reached)
### Total Tests: 721 (713 passed, 1 failed, 7 skipped)

## Recent Critical Fixes
- Simplified Agent Wrapper Bug Fix (2025-12-07)
- Annotator Result Save Fix (2025-12-01) - multi-phase
- CUDA Device Handling Fix (2025-12-01)
- pHash Dictionary Key Fix (2025-12-02)

## Architecture State
- Controller/Service: Separated, loosely coupled via DI
- Event Delegation: 3 service-specific helper methods
- PipelineControlService + ProgressStateService: Async workflow management
- ProviderManager + PydanticAI: Stable, agent cache documented

## DevContainer (2025-11-21)
- Removed local package .venv directories
- Single folder workspace configuration
- 1472 tests collected successfully

## Development Policy
- Memory-First: .serena/memories/ (short-term) + Cipher (long-term)
- Command-Based: /check-existing → /planning → /implement → /test
- YAGNI: Minimum necessary implementation
