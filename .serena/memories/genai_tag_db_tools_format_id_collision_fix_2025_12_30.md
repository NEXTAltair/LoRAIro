# genai-tag-db-tools format_id Collision Fix (2025-12-30)

## Issue Identified
**Critical Design Flaw**: User DB format_id collides with base DB (HuggingFace download) format_id when using auto-increment.

### Problem Scenario
- Base DB (downloaded): `format_id=1` → `"danbooru"`
- User DB (auto-created): `format_id=1` → `"Lorairo"` (auto-increment starts from 1)
- `MergedTagReader.get_format_map()` merges both dictionaries
- User DB entry **overwrites** base DB entry → format_id=1 incorrectly maps to "Lorairo"
- Tag lookups fail: tags with `format_id=1` from base DB are misidentified

### Root Cause
SQLite `AUTOINCREMENT` in user DB starts from 1 without checking base DB IDs.

## Solution Implemented

### Code Changes (Commit: 60f156d)

#### 1. `TagRepository.create_format_if_not_exists()` (repository.py:603-650)
```python
def create_format_if_not_exists(
    self, format_name: str, description: str | None = None, reader: "MergedTagReader | None" = None
) -> int:
    """Create a TagFormat if it doesn't exist, return format_id.
    
    Args:
        reader: Optional MergedTagReader to check base DB format_ids and avoid collisions
    """
    with self.session_factory() as session:
        # Check if format already exists
        format_obj = session.query(TagFormat).filter(TagFormat.format_name == format_name).one_or_none()
        if format_obj:
            return format_obj.format_id
        
        # Determine next format_id to avoid collision with base DBs
        next_format_id = None
        if reader is not None:
            # Get all format_ids from base DBs
            base_format_map = {}
            for base_repo in reader._iter_base_repos():
                base_format_map.update(base_repo.get_format_map())
            
            if base_format_map:
                max_base_format_id = max(base_format_map.keys())
                next_format_id = max_base_format_id + 1
                self.logger.info(
                    f"Allocating format_id={next_format_id} for '{format_name}' "
                    f"(max base DB format_id: {max_base_format_id})"
                )
        
        # Create new format
        new_format = TagFormat(
            format_id=next_format_id,  # None uses auto-increment, explicit value prevents collision
            format_name=format_name,
            description=description,
        )
        session.add(new_format)
        session.commit()
        session.refresh(new_format)
        return new_format.format_id
```

**Key Points**:
- Optional `reader` parameter for collision avoidance
- Queries all base DBs via `reader._iter_base_repos()`
- Allocates `format_id = max(base_format_ids) + 1`
- Backward compatible: `reader=None` uses auto-increment (legacy)

#### 2. `TagRegisterService.register_tag()` (tag_register.py:142-147)
```python
# Auto-create format if it doesn't exist
try:
    fmt_id = self._reader.get_format_id(request.format_name)
except ValueError:
    # Format doesn't exist, create it
    # Pass reader to avoid format_id collision with base DBs
    fmt_id = self._repo.create_format_if_not_exists(
        format_name=request.format_name,
        description=f"Auto-created format: {request.format_name}",
        reader=self._reader,  # ← Added this parameter
    )
    self.logger.info(f"Auto-created format_name: {request.format_name} (ID: {fmt_id})")
```

**Key Change**: Pass `self._reader` to enable collision detection.

#### 3. Type Import (repository.py:1-12)
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader
```

### Test Coverage

#### New Test File: `tests/unit/test_format_id_collision_avoidance.py`

**Test 1: Basic Collision Avoidance**
- Base DB: `format_id=1` → `"danbooru"`
- User creates `"Lorairo"` → allocates `format_id=2` (not 1)
- Verifies merged view correctly shows both formats

**Test 2: Multiple Base DBs**
- Base DB 1: `format_id=1` → `"danbooru"`
- Base DB 2: `format_id=5` → `"e621"`
- User creates `"Lorairo"` → allocates `format_id=6` (max + 1)

**Test 3: Legacy Behavior**
- Without reader parameter → uses auto-increment from 1
- Ensures backward compatibility

**All Tests Pass**: ✅ 3/3

### Existing Tests

**LoRAIro Tests**: ✅ 6/6 passing
- `tests/unit/database/test_db_repository_tag_registration.py`

**genai-tag-db-tools Tests**: ✅ 4/4 passing
- `tests/unit/test_tag_register_service.py`

## Technical Insights

### MergedTagReader Architecture
```python
class MergedTagReader:
    def get_format_map(self) -> dict[int, str]:
        formats: dict[int, str] = {}
        for repo in self._iter_base_repos_low_to_high():
            formats.update(repo.get_format_map())  # Base DBs first
        if self._has_user():
            formats.update(self.user_repo.get_format_map())  # User DB OVERWRITES
        return formats
```

**Critical Behavior**: `dict.update()` overwrites existing keys → user DB format_ids MUST NOT collide with base DB IDs.

### ID Allocation Strategy

**Before Fix**:
```
Base DB:  format_id=1 (danbooru), format_id=2 (e621), ...
User DB:  format_id=1 (Lorairo) ← COLLISION!
Merged:   {1: "Lorairo", 2: "e621", ...} ← Wrong!
```

**After Fix**:
```
Base DB:  format_id=1 (danbooru), format_id=2 (e621), ...
User DB:  format_id=3 (Lorairo) ← No collision
Merged:   {1: "danbooru", 2: "e621", 3: "Lorairo"} ← Correct!
```

## Integration with LoRAIro

### Workflow
1. User triggers tag registration in LoRAIro GUI
2. `ImageRepository._get_or_create_tag_id_external()` calls `search_tags()`
3. If tag not found, initializes `TagRegisterService` with reader
4. `TagRegisterService.register_tag()` auto-creates format if missing
5. **Now**: Passes `reader` to ensure format_id doesn't collide
6. User DB format correctly created with safe ID

### Example Log
```
INFO - Allocating format_id=10 for 'Lorairo' (max base DB format_id: 9)
INFO - Created new TagFormat: Lorairo (ID: 10)
INFO - Auto-created format_name: Lorairo (ID: 10)
```

## Related Work

### Plan Reference
- `.serena/memories/plan_parallel_humming_garden_2025_12_28.md`
- Original plan included format/type auto-creation but didn't address ID collision

### Tags v3 Cleanup
- `.serena/memories/genai_tag_db_tools_tags_v3_reference_cleanup_todo_2025_12_30.md`
- Old `tags_v3.db` references need cleanup (separate task)

## Impact

### What This Fixes
✅ User DB formats no longer overwrite base DB formats in merged view
✅ Tag lookups correctly resolve format names
✅ Multi-base-DB scenarios handled correctly
✅ LoRAIro tag registration works reliably

### Backward Compatibility
✅ Legacy code without reader parameter still works (auto-increment)
✅ No breaking changes to public API
✅ All existing tests pass

## Future Considerations

### Potential Enhancements
1. **Reserved ID Ranges**: Allocate user DB IDs starting from 10000+ for clearer separation
2. **Type ID Collision**: Apply same fix to `TagTypeName` type_name_id (currently hardcoded)
3. **Database Metadata**: Store max_base_format_id in user DB metadata for faster lookups

### Monitoring
- Log format_id allocations to detect potential issues
- Add validation to ensure no collisions in production
