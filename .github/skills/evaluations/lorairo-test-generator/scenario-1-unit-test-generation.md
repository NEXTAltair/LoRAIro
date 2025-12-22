# Scenario: Unit Test Generation for Repository

## Input
**User request:** "Generate unit tests for the ImageRepository class. Cover all CRUD methods with proper fixtures and achieve 75%+ coverage."

**Context:**
- LoRAIro testing requirements:
  - pytest framework
  - 75%+ code coverage
  - AAA pattern (Arrange, Act, Assert)
  - Fixtures for common setup
  - Proper mocking for external dependencies
- Target class: ImageRepository in `src/lorairo/database/repositories/image_repository.py`
- Test location: `tests/unit/database/repositories/`

## Expected Behavior
1. Skill `lorairo-test-generator` should be invoked automatically
2. Should guide test creation workflow:

   **Phase 1: Pattern Research**
   - Examine existing repository tests
   - Check memory for test patterns
   - Review ImageRepository methods to test

   **Phase 2: Fixture Creation**
   - Create session fixture
   - Create sample Image model fixtures
   - Create repository instance fixture

   **Phase 3: Test Implementation**
   - Generate tests for each CRUD method:
     ```python
     def test_create_image(image_repository, sample_image):
         # Arrange
         assert sample_image.id is None

         # Act
         result = image_repository.create(sample_image)

         # Assert
         assert result.id is not None
         assert result.path == sample_image.path

     def test_get_by_id_existing(image_repository, sample_image):
         # Arrange
         created = image_repository.create(sample_image)

         # Act
         result = image_repository.get_by_id(created.id)

         # Assert
         assert result is not None
         assert result.id == created.id

     def test_get_by_id_not_found(image_repository):
         # Act
         result = image_repository.get_by_id(99999)

         # Assert
         assert result is None
     ```

   **Phase 4: Coverage Verification**
   - Suggest running pytest with coverage
   - Ensure 75%+ coverage achieved

3. Should produce:
   - Complete test suite
   - Proper fixtures
   - AAA pattern throughout
   - Edge cases covered
   - Coverage meets requirements

4. Should NOT:
   - Skip edge cases (None, not found, etc.)
   - Forget fixtures (duplicate setup code)
   - Mix test concerns (one assert per concept)
   - Skip pytest markers (@pytest.mark.unit)

## Success Criteria
- [x] Correct skill invoked (lorairo-test-generator)
- [x] Pattern research done (existing tests, memory)
- [x] Fixtures created and reused
- [x] All CRUD methods tested
- [x] AAA pattern followed
- [x] Edge cases covered
- [x] pytest markers present
- [x] Coverage >= 75%
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic tests; may need guidance on fixtures and edge cases
- **Sonnet:** Should create comprehensive test suite; good fixture usage and AAA pattern
- **Opus:** May suggest additional test cases; may optimize fixture structure; excellent coverage of edge cases

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-test-generator` in metadata
2. Check pattern research:
   - Examined existing repository tests
   - Used patterns from memory/existing code
3. Verify fixture structure:
   - Session fixture (database connection)
   - Model fixtures (sample data)
   - Repository fixture (instance under test)
   - Fixtures in conftest.py or test file
4. Check test structure (AAA pattern):
   - Arrange section: Setup
   - Act section: Method call
   - Assert section: Verification
5. Verify coverage:
   - All CRUD methods tested (create, get, update, delete)
   - Edge cases included (not found, None, invalid input)
   - pytest marker: `@pytest.mark.unit`
6. Run tests:
   ```bash
   uv run pytest tests/unit/database/repositories/test_image_repository.py --cov=src/lorairo/database/repositories/image_repository.py
   ```
7. Check coverage report:
   - Coverage >= 75%
   - All critical paths covered

## Edge Cases to Test
- Create with duplicate ID (should handle or fail gracefully)
- Get by ID not found (returns None)
- Update non-existent record (returns None or raises)
- Delete non-existent record (returns False)
- Invalid input types (type checking)
