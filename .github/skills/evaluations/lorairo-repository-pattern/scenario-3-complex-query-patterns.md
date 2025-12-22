# Scenario: Complex Query with Joins and Filtering

## Input
**User request:** "I need to query images that have specific tags AND were annotated after a certain date. The query should use SQLAlchemy ORM with proper joins. Show me the repository method pattern."

**Context:**
- Complex query requirements:
  - Join: Images → ImageTags → Tags
  - Filter: Tag names in specific list
  - Filter: Annotation date > threshold
  - Return: List of Image models
- Should use SQLAlchemy ORM (not raw SQL)
- Type-safe return values
- Efficient query (proper joins, not N+1)

## Expected Behavior
1. Skill `lorairo-repository-pattern` should be invoked automatically
2. Should demonstrate complex query pattern:

   **Phase 1: Pattern Research**
   - Search for existing complex queries in repositories
   - Check memory for join patterns
   - Review SQLAlchemy best practices

   **Phase 2: Implementation**
   - Show proper repository method:
     ```python
     def find_by_tags_and_date(
         self,
         tag_names: list[str],
         after_date: datetime,
     ) -> list[Image]:
         """
         Find images with specific tags annotated after date.

         Args:
             tag_names: List of tag names to filter by
             after_date: Minimum annotation date

         Returns:
             List of matching Image models
         """
         return (
             self.session.query(Image)
             .join(ImageTag, Image.id == ImageTag.image_id)
             .join(Tag, ImageTag.tag_id == Tag.id)
             .filter(Tag.name.in_(tag_names))
             .filter(Image.annotated_at > after_date)
             .distinct()
             .all()
         )
     ```
   - Explain join strategy
   - Discuss `.distinct()` for many-to-many
   - Type hints for parameters and return

   **Phase 3: Optimization Notes**
   - Mention eager loading if relationships needed
   - Discuss query performance considerations
   - Suggest adding database indexes

3. Should produce:
   - Complete repository method
   - Proper SQLAlchemy ORM query
   - Type-safe implementation
   - Performance considerations
   - Anti-patterns to avoid

4. Should NOT:
   - Use raw SQL (should use ORM)
   - Return query object instead of results
   - Create N+1 query problem
   - Skip type hints

## Success Criteria
- [x] Correct skill invoked (lorairo-repository-pattern)
- [x] Pattern research done (explores existing queries)
- [x] SQLAlchemy ORM query is correct
- [x] Joins are proper (no N+1)
- [x] Type hints present
- [x] Docstring follows Google style
- [x] Performance considerations mentioned
- [x] Completes without errors

## Model Variations
- **Haiku:** Should create basic query; may need guidance on joins and distinct()
- **Sonnet:** Should create complete query with proper joins; good type hints and docstring
- **Opus:** May suggest query optimization strategies; may proactively add eager loading; may recommend database indexes

## Test Validation
After running this scenario:
1. Verify skill invoked: Check `lorairo-repository-pattern` in metadata
2. Check pattern research:
   - Explored existing complex queries
   - Checked memory for join patterns
3. Verify query structure:
   - Uses `self.session.query(Image)` (ORM, not raw SQL)
   - Proper joins: Image → ImageTag → Tag
   - Correct filter conditions
   - Uses `.distinct()` for many-to-many
   - Returns `.all()` (list[Image])
4. Check type safety:
   - Parameter types: `list[str]`, `datetime`
   - Return type: `list[Image]`
   - No `Any` types
5. Verify documentation:
   - Google-style docstring
   - Args section with types and descriptions
   - Returns section with type and description
6. Test query correctness (if possible):
   - Can be executed in actual database
   - Returns expected results
   - No N+1 queries (use SQLAlchemy query logging)

## Edge Cases to Test
- Empty tag_names list (should handle gracefully)
- Tags that don't exist (returns empty list)
- Images with multiple matching tags (distinct() prevents duplicates)
- Performance with large dataset (mention indexing)
