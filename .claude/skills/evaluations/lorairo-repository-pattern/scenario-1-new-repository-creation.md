# Scenario: New Repository Creation Following Pattern

## Input
**User request:** "Create a new ExportConfigRepository for managing export configuration settings. Follow the LoRAIro repository pattern like ImageRepository and TagRepository."

**Context:**
- LoRAIro uses repository pattern for data access layer
- Existing patterns: ImageRepository, TagRepository in `src/lorairo/database/repositories/`
- Should use:
  - SQLAlchemy ORM
  - Type-safe transactions
  - Session management via db_core
  - Consistent error handling
- New repository for ExportConfig model

## Expected Behavior
1. Skill `lorairo-repository-pattern` should be invoked automatically
2. Should guide repository creation workflow:

   **Phase 1: Explore Existing Pattern**
   - Use `mcp__serena__find_symbol` to find ImageRepository or TagRepository
   - Analyze structure, methods, session handling
   - Identify common patterns to follow

   **Phase 2: Check Memory for Patterns**
   - `mcp__cipher__cipher_memory_search` for "repository pattern"
   - Look for past repository implementations
   - Review design decisions

   **Phase 3: Implement Following Pattern**
   - Create ExportConfigRepository class
   - Implement CRUD methods (create, get_by_id, update, delete)
   - Add session management
   - Type hints for all methods
   - Proper error handling

   **Phase 4: Test Creation**
   - Suggest creating tests following pattern
   - Reference pytest fixtures from existing repository tests

3. Should produce:
   - Complete repository implementation
   - Follows LoRAIro patterns consistently
   - Type-safe and well-documented
   - Test recommendation

4. Should NOT:
   - Create pattern that differs from existing repositories
   - Use raw SQL instead of ORM
   - Skip error handling
   - Forget type hints

## Success Criteria
- [x] Correct skill invoked (lorairo-repository-pattern)
- [x] Explores existing repositories before implementing
- [x] Checks memory for past patterns
- [x] Implementation follows LoRAIro conventions
- [x] All CRUD methods included
- [x] Type hints present
- [x] Error handling consistent with existing code
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic repository; may need guidance on session management and error handling
- **Sonnet:** Should create complete repository following all patterns; good consistency with existing code
- **Opus:** May suggest additional methods beyond CRUD; may optimize query patterns; excellent pattern adherence

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-repository-pattern` in metadata
2. Check exploration phase:
   - Used `find_symbol` to examine ImageRepository or TagRepository
   - Analyzed existing patterns before implementing
3. Check memory integration:
   - Searched Cipher for repository patterns
   - Applied past knowledge to new implementation
4. Verify repository structure:
   ```python
   class ExportConfigRepository:
       def __init__(self, session: Session): ...
       def create(self, config: ExportConfig) -> ExportConfig: ...
       def get_by_id(self, config_id: int) -> ExportConfig | None: ...
       def update(self, config: ExportConfig) -> ExportConfig: ...
       def delete(self, config_id: int) -> bool: ...
   ```
5. Check consistency with existing repositories:
   - Session management same as ImageRepository
   - Error handling same as TagRepository
   - Type hints match project standards
6. Verify code quality:
   - No `# type: ignore` comments
   - Proper docstrings (Google style)
   - Logging where appropriate
