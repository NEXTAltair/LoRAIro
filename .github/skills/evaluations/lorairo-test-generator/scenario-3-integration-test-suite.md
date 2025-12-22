# Scenario: Integration Test Suite for Feature Workflow

## Input
**User request:** "Create integration tests for the image annotation workflow: select image → run annotation worker → save results → update database. Test the full end-to-end flow."

**Context:**
- LoRAIro integration testing requirements:
  - pytest framework
  - @pytest.mark.integration marker
  - Tests multiple components together
  - Real database (SQLite test DB)
  - Worker execution (may use mocks for AI APIs)
  - 75%+ coverage for critical paths
- Components involved:
  - ImageRepository (database)
  - AnnotationWorker (async worker)
  - AnnotationService (business logic)
  - WorkerManager (worker execution)
- Test location: `tests/integration/`

## Expected Behavior
1. Skill `lorairo-test-generator` should be invoked automatically
2. Should guide integration test creation:

   **Phase 1: Pattern Research**
   - Examine existing integration tests
   - Check memory for workflow test patterns
   - Review components involved in annotation flow

   **Phase 2: Fixture Creation**
   - Test database fixture (temporary SQLite)
   - Repository fixtures with test data
   - Service/worker fixtures
   - Cleanup fixtures

   **Phase 3: Integration Test Implementation**
   - Full workflow test:
     ```python
     @pytest.mark.integration
     def test_annotation_workflow_success(
         test_db,
         image_repository,
         annotation_service,
         sample_image_file,
         mock_openai_api
     ):
         # Arrange
         image = image_repository.create(Image(path=sample_image_file))
         assert image.annotation_status == "pending"

         # Act
         # Step 1: Run annotation
         annotation_service.annotate_image(image.id)

         # Step 2: Wait for worker completion (or use synchronous version)
         # (In real integration test, may need to wait or use callbacks)

         # Step 3: Verify results saved
         updated_image = image_repository.get_by_id(image.id)

         # Assert
         assert updated_image.annotation_status == "completed"
         assert updated_image.caption is not None
         assert len(updated_image.tags) > 0
     ```

   - Error handling test:
     ```python
     @pytest.mark.integration
     def test_annotation_workflow_api_failure(
         test_db,
         image_repository,
         annotation_service,
         sample_image_file,
         mock_openai_api_failure
     ):
         # Arrange
         image = image_repository.create(Image(path=sample_image_file))

         # Act
         with pytest.raises(AnnotationError):
             annotation_service.annotate_image(image.id)

         # Assert
         updated_image = image_repository.get_by_id(image.id)
         assert updated_image.annotation_status == "failed"
     ```

   **Phase 4: Coverage Verification**
   - Suggest running integration tests
   - Verify critical paths covered
   - Check database state consistency

3. Should produce:
   - Complete integration test suite
   - End-to-end workflow tests
   - Error handling tests
   - Database consistency checks
   - Proper mocking of external APIs
   - Cleanup fixtures

4. Should NOT:
   - Skip database cleanup (test isolation)
   - Forget error cases
   - Use production database
   - Skip mocking external services (slow, unreliable)

## Success Criteria
- [x] Correct skill invoked (lorairo-test-generator)
- [x] Pattern research done (existing integration tests)
- [x] Test database fixture created
- [x] Full workflow tested end-to-end
- [x] Error cases tested
- [x] Database state verified
- [x] External APIs mocked appropriately
- [x] @pytest.mark.integration marker present
- [x] Test isolation maintained (cleanup)
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic integration tests; may need guidance on fixtures and mocking
- **Sonnet:** Should create comprehensive integration suite; good workflow coverage and error handling
- **Opus:** May suggest additional scenarios (concurrency, race conditions); excellent fixture structure and test isolation

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-test-generator` in metadata
2. Check test database fixture:
   - Temporary SQLite database created
   - Schema initialized
   - Cleanup after test
3. Verify workflow coverage:
   - Success path: Select → Annotate → Save → Verify
   - Failure path: API error → Status updated → Error logged
4. Check component integration:
   - Repository used for database operations
   - Worker executed (or mocked appropriately)
   - Service coordinates workflow
5. Verify mocking:
   - External APIs mocked (OpenAI, Anthropic)
   - Mock responses realistic
   - Mock failures testable
6. Check test isolation:
   - Each test independent
   - Database state reset between tests
   - No side effects from previous tests
7. Run integration tests:
   ```bash
   uv run pytest tests/integration/ -m integration --cov=src/lorairo
   ```
8. Verify execution:
   - All tests pass
   - Critical paths covered (75%+)
   - Database consistent after tests

## Edge Cases to Test
- Concurrent annotation requests (worker pooling)
- Large image file (timeout handling)
- Database connection failure (retry logic)
- Partial workflow completion (cleanup/rollback)
- Worker cancellation mid-execution
