# Tag Database Duplicate Handling Fix - 2025-08-30

## Problem Identified
- Error during dataset registration/crop processing: "Multiple rows were found when one or none was required"
- Method `_get_or_create_tag_id_external` in `db_repository.py` was using `scalar_one_or_none()` 
- Tag `:d` had duplicate entries in the external tag database (tag_db.TAGS)
- This caused SQLAlchemy to throw an error when expecting exactly 0 or 1 result

## Root Cause Analysis
- The tag database (tags_v3.db from genai-tag-db-tools) contains duplicate entries for certain tags
- Original method used `scalar_one_or_none()` which strictly enforces single result expectation
- When multiple rows exist for same tag, the query fails instead of handling gracefully

## Solution Implemented
**File**: `src/lorairo/database/db_repository.py`
**Method**: `_get_or_create_tag_id_external`

### Changes Made:
1. **Replaced `scalar_one_or_none()`** with `first()` to get the first matching row
2. **Added duplicate detection logic** with count query to log warnings when duplicates exist
3. **Enhanced logging** to show duplicate count and recommend database cleanup
4. **Maintained error handling** and None return behavior for missing tags

### Key Improvements:
- **Graceful Handling**: Method now handles duplicate tags without crashing
- **Warning System**: Logs when duplicates are detected for potential cleanup
- **Backward Compatibility**: Still returns None for missing tags as expected
- **Performance**: Uses first match instead of failing on duplicates

## Implementation Details

```python
# Before: Strict single result expectation
result = session.execute(stmt, {"tag_name": tag_string}).scalar_one_or_none()

# After: Graceful duplicate handling with warning
result = session.execute(stmt, {"tag_name": tag_string}).first()
if result:
    tag_id = result[0]
    # Check for duplicates and warn
    count_result = session.execute(count_stmt, {"tag_name": tag_string}).scalar()
    if count_result > 1:
        logger.warning(f"Multiple entries ({count_result}) found for tag '{tag_string}'...")
    return tag_id
```

## Branch Information
- **Branch**: `fix/tag-database-duplicate-handling`
- **Status**: Implementation complete, ready for testing

## Next Steps
1. Test with actual dataset registration process
2. Monitor for duplicate warnings in logs
3. Consider tag database cleanup if many duplicates exist
4. Validate fix resolves crop processing errors

## Technical Context
- **External DB**: tag_db.TAGS accessed via ATTACH DATABASE mechanism
- **Integration**: Part of image annotation save flow during dataset registration
- **Impact**: Affects all workflows that save tag annotations to external tag database