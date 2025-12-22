# Scenario: Complex Transaction Handling

## Input
**User request:** "I need to update multiple image records and their associated tags in a single transaction. If any update fails, everything should rollback. Show me the correct pattern."

**Context:**
- LoRAIro uses SQLAlchemy session-based transactions
- Need to update multiple models atomically
- Must handle rollback on error
- Should follow LoRAIro's transaction patterns from existing code
- Files involved:
  - ImageRepository for image updates
  - TagRepository for tag updates

## Expected Behavior
1. Skill `lorairo-repository-pattern` should be invoked automatically
2. Should demonstrate transaction pattern:

   **Phase 1: Pattern Research**
   - Search existing code for transaction examples
   - Check memory for transaction handling patterns
   - Identify best practices

   **Phase 2: Implementation Guidance**
   - Show correct transaction pattern:
     ```python
     from src.lorairo.database.db_core import get_session

     def update_images_and_tags(updates: list[ImageUpdate], tag_updates: list[TagUpdate]) -> None:
         with get_session() as session:
             try:
                 image_repo = ImageRepository(session)
                 tag_repo = TagRepository(session)

                 for update in updates:
                     image_repo.update(update)

                 for tag_update in tag_updates:
                     tag_repo.update(tag_update)

                 session.commit()
             except Exception as e:
                 session.rollback()
                 logger.error(f"Transaction failed: {e}")
                 raise
     ```
   - Explain session lifecycle
   - Discuss error handling
   - Mention logging best practices

   **Phase 3: Anti-Patterns**
   - Show what NOT to do:
     - Multiple separate sessions (breaks atomicity)
     - Manual commit without error handling
     - Swallowing exceptions

3. Should produce:
   - Complete transaction example
   - Explanation of pattern
   - Error handling guidance
   - Anti-patterns to avoid

4. Should NOT:
   - Suggest manual transaction management (use context manager)
   - Forget rollback on error
   - Use multiple sessions for atomic operation

## Success Criteria
- [x] Correct skill invoked (lorairo-repository-pattern)
- [x] Pattern research done (checks existing code/memory)
- [x] Transaction pattern is correct (single session, proper rollback)
- [x] Error handling is comprehensive
- [x] Anti-patterns are mentioned
- [x] Example is complete and runnable
- [x] Follows LoRAIro conventions
- [x] Completes without errors

## Model Variations
- **Haiku:** Should show basic transaction pattern; may need guidance on error handling details
- **Sonnet:** Should provide complete pattern with error handling; good explanation of lifecycle
- **Opus:** May discuss advanced scenarios (nested transactions, savepoints); may suggest testing strategy for transaction failures

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-repository-pattern` in metadata
2. Check pattern research:
   - Explored existing transaction patterns in codebase
   - Checked memory for best practices
3. Verify transaction pattern:
   - Single session used via `get_session()` context manager
   - Multiple repository operations in same session
   - `session.commit()` called after all operations
   - `session.rollback()` in exception handler
   - Exception re-raised after rollback
4. Check error handling:
   - Try-except block present
   - Specific exception types (not bare `except`)
   - Logging before raising
5. Verify anti-patterns mentioned:
   - Multiple sessions (breaks atomicity)
   - No rollback (data corruption risk)
   - Swallowed exceptions (silent failures)
6. Test execution:
   - Example code is syntactically correct
   - Imports are accurate
   - Can be run in LoRAIro project
