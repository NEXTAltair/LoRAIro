# Plan: resilient-launching-hammock

**Created**: 2025-12-26 11:01:47
**Source**: plan_mode
**Original File**: resilient-launching-hammock.md
**Status**: planning

---

# CRUD Operations Complete Separation Plan: TagRepository & MergedTagReader

## Overview

Complete separation of read/write operations in genai-tag-db-tools:
- **TagRepository**: Write operations only (create/update/delete)
- **MergedTagReader**: Read operations only (all get_*/list_*/search_*)

**User Decisions:**
- ❌ No deprecation period - immediate removal of get_* methods from TagRepository
- ✅ Split `get_default_repository()` into `get_default_reader()` + `get_default_repository()`

## Current State Analysis

**Missing methods in MergedTagReader (6 total):**
1. `get_max_tag_id()` - Pattern C (max across all DBs)
2. `get_metadata_value(key)` - Pattern A (user → base priority)
3. `get_type_name_by_format_type_id()` - Pattern A (first-match)
4. `get_type_id(type_name)` - Pattern A (first-match)
5. `get_tag_format_ids()` - Pattern C (union of format_ids)
6. `list_translations()` - Pattern B (merge by (tag_id, language))

**Critical files to modify:**
- [repository.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py) - Add 6 methods, split factory, remove get_*
- [app_services.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/app_services.py) - Update TagRegisterService (5+ call sites)
- [db_maintenance_tool.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/db_maintenance_tool.py) - Update 8+ get_* calls
- [tag_statistics.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_statistics.py) - Inject reader
- [tag_search.py](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_search.py) - Inject reader

## Implementation Phases

### Phase 1: Introduce Read-Only Repository (session_factory based)

**Goal:** MergedTagReader must not depend on TagRepository read methods. Implement a read-only class (e.g. `TagReader`) that uses `session_factory` and existing query utilities to provide all get_*/list_*/search_*.

**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py`

**Plan:**
- Create `TagReader` that accepts `session_factory` and implements all read APIs currently in TagRepository.
- Reuse existing query utilities (e.g. `query_utils`) to avoid duplicating SQL.
- MergedTagReader should aggregate `TagReader` instances (base + optional user).
- TagRepository becomes write-only and no longer implements read APIs.

### Phase 2: Add Missing Methods to MergedTagReader

**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py`

**Add 6 methods after `get_database_version()` (line ~919):**

```python
def get_max_tag_id(self) -> int:
    """現在の最大tag_idを返す（全DB統合）"""
    max_id = 0
    for repo in self._iter_repos():
        repo_max = repo.get_max_tag_id()
        if repo_max > max_id:
            max_id = repo_max
    return max_id

def get_metadata_value(self, key: str) -> str | None:
    """DATABASE_METADATAの値を取得する（user → base優先）"""
    if self._has_user():
        value = self.user_repo.get_metadata_value(key)
        if value is not None:
            return value
    for repo in self._iter_base_repos():
        value = repo.get_metadata_value(key)
        if value is not None:
            return value
    return None

def get_type_name_by_format_type_id(self, format_id: int, type_id: int) -> str | None:
    """(format_id, type_id)からtype_nameを取得する（first-match）"""
    if self._has_user():
        name = self.user_repo.get_type_name_by_format_type_id(format_id, type_id)
        if name is not None:
            return name
    for repo in self._iter_base_repos():
        name = repo.get_type_name_by_format_type_id(format_id, type_id)
        if name is not None:
            return name
    return None

def get_type_id(self, type_name: str) -> int | None:
    """type_nameからtype_idを取得する（first-match）"""
    if self._has_user():
        type_id = self.user_repo.get_type_id(type_name)
        if type_id is not None:
            return type_id
    for repo in self._iter_base_repos():
        type_id = repo.get_type_id(type_name)
        if type_id is not None:
            return type_id
    return None

def get_tag_format_ids(self) -> list[int]:
    """全format_idを取得する（set union）"""
    format_ids: set[int] = set()
    for repo in self._iter_repos():
        format_ids |= set(repo.get_tag_format_ids())
    return list(format_ids)

def list_translations(self) -> list[TagTranslation]:
    """全翻訳を取得する（全DB統合、重複削除）"""
    translations: list[TagTranslation] = []
    for repo in self._iter_base_repos_low_to_high():
        translations += repo.list_translations()
    if self._has_user():
        translations += self.user_repo.list_translations()

    # Deduplicate by (tag_id, language, translation)
    seen: set[tuple[int, str, str]] = set()
    unique: list[TagTranslation] = []
    for tr in translations:
        key = (tr.tag_id, tr.language, tr.translation)
        if key in seen:
            continue
        seen.add(key)
        unique.append(tr)
    return unique
```

### Phase 3: Split get_default_repository()

**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py` (line ~960)

**Replace current `get_default_repository()` with:**

```python
def get_default_reader() -> MergedTagReader:
    """デフォルトのMergedTagReaderを返す（読み取り専用）"""
    @staticmethod
    def _parse_version(value: str) -> tuple[int, ...] | None:
        if not value:
            return None
        cleaned = value.strip()
        if cleaned.lower().startswith("v"):
            cleaned = cleaned[1:]
        parts = cleaned.split(".")
        try:
            return tuple(int(part) for part in parts)
        except (TypeError, ValueError):
            return None

    def get_database_version(self) -> str | None:
        versions: list[str] = []
        for repo in self._iter_repos():
            if hasattr(repo, "get_database_version"):
                version = repo.get_database_version()
                if version:
                    versions.append(version)
        if not versions:
            return None

        parsed: list[tuple[tuple[int, ...], str]] = []
        raw: list[str] = []
        for value in versions:
            parsed_value = self._parse_version(value)
            if parsed_value is not None:
                parsed.append((parsed_value, value))
            else:
                raw.append(value)

        if parsed:
            return max(parsed, key=lambda item: item[0])[1]
        return max(raw)

    from genai_tag_db_tools.db.runtime import (
        get_base_session_factories,
        get_user_session_factory_optional,
    )

    user_factory = get_user_session_factory_optional()
    user_repo = TagReader(session_factory=user_factory) if user_factory else None

    base_factories = get_base_session_factories()
    if not base_factories:
        if user_repo:
            return MergedTagReader(base_repo=user_repo, user_repo=None)
        raise ValueError("No database available")

    if len(base_factories) == 1:
        base_repo = TagReader(session_factory=base_factories[0])
        return MergedTagReader(base_repo=base_repo, user_repo=user_repo)

    base_repos = [TagReader(session_factory=f) for f in base_factories]
    return MergedTagReader(base_repo=base_repos, user_repo=user_repo)


def get_default_repository() -> TagRepository:
    """デフォルトのTagRepositoryを返す（書き込み可能、ユーザーDBのみ）"""
    from genai_tag_db_tools.db.runtime import get_user_session_factory_optional

    user_factory = get_user_session_factory_optional()
    if not user_factory:
        raise ValueError("User database not available for write operations")

    return TagRepository(session_factory=user_factory, reader=get_default_reader())
```

### Phase 4: Update TagRepository Constructor

**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py`

**Add reader parameter and use for write ops that need read:**

```python
def __init__(
    self,
    session_factory: Callable[[], Session] | None = None,
    reader: MergedTagReader | None = None
):
    self.logger = logging.getLogger("TagRepository")
    if session_factory:
        self.session_factory = session_factory
    else:
        self.session_factory = get_session_factory()
    self._reader = reader  # For read ops in write methods
```

**Update create_tag() / ensure_tag_with_id() to use injected reader (same as previous plan).**

### Phase 5: Update Service Layer Call Sites

- Update read operations to use get_default_reader() instead of TagRepository.
- Ensure TagRegisterService and TagStatistics/TagSearch use reader for get_* and list_*.

### Phase 6: Remove get_* Methods from TagRepository

Remove all get_*/list_*/search_* from TagRepository after TagReader is in place.

### Phase 7: Update Tests

- Add tests for TagReader and new MergedTagReader methods.
- Update TagRepository tests to write-only.

## Verification Checklist

### After Phase 1:
- [ ] 6 new methods added to MergedTagReader
- [ ] 18+ unit tests pass
- [ ] Coverage ≥75%

### After Phase 2:
- [ ] `get_default_reader()` and `get_default_repository()` both exist
- [ ] `get_default_reader()` returns MergedTagReader
- [ ] `get_default_repository()` returns TagRepository (user DB only)

### After Phase 3:
- [ ] TagRepository accepts `reader` parameter
- [ ] `create_tag()` uses injected reader
- [ ] `ensure_tag_with_id()` uses injected reader

### After Phase 4:
- [ ] All service layer files updated (5 files)
- [ ] All tests pass
- [ ] No import errors

### After Phase 5:
- [ ] All get_*/list_*/search_* methods removed from TagRepository
- [ ] Grep confirms no external usage: `git grep "TagRepository.*get_" | wc -l` = 0
- [ ] Only write methods remain

### After Phase 6:
- [ ] Full test suite passes (unit + integration)
- [ ] Coverage ≥75%
- [ ] No mypy errors

## Risk Mitigation

**High-Risk Files:**
1. app_services.py (TagRegisterService) - Qt signals, 5+ call sites
2. db_maintenance_tool.py - 8+ get_* calls, external tool
3. tag_statistics.py - Core service with multiple read ops

**Mitigation:**
- Run tests after each phase
- Manual QA for maintenance tool
- Integration tests for service layer

## Estimated Effort

| Phase | Hours | Risk |
|-------|-------|------|
| Phase 1 | 2-3 | Low |
| Phase 2 | 1-2 | Low |
| Phase 3 | 2-3 | Medium |
| Phase 4 | 4-5 | High |
| Phase 5 | 1 | Low |
| Phase 6 | 2-3 | Medium |
| **Total** | **12-17** | **Medium-High** |

## Critical Files Summary

1. **repository.py** - Add 6 methods, split factory, remove get_*, update constructor
2. **app_services.py** - Update TagRegisterService (highest risk)
3. **db_maintenance_tool.py** - Update 8+ call sites
4. **tag_statistics.py** - Inject reader for all read ops
5. **tag_search.py** - Inject reader for format/type queries

## Critical Architectural Issue (2025-12-26)

**Problem:** MergedTagReaderは現在TagRepositoryのget_*メソッドに委譲している。TagRepositoryからget_*を削除するとMergedTagReaderが壊れる。

**User Feedback:**
- MergedTagReaderに生のSQL/ORMロジックを詰め込むと保守性が低下
- 既存TagRepositoryのreadロジック（query_utils等）を再利用しないと二重実装になる
- search_tags等の複雑なロジックは特に重複コストが高い

**Revised Solution: 3-Class Architecture**

```
TagReader (NEW)          - Read-only operations, reuses query_utils
    ↑                    - Contains all get_*/list_*/search_* logic
    |                    - Single DB access (no merging)
    |
MergedTagReader          - Multi-DB coordination layer
    ↑                    - Delegates to TagReader instances
    |                    - Implements priority/merge rules (user優先, union, dedupe)
    |
TagRepository            - Write-only operations
                         - create/update/delete only
```

**Benefits:**
1. **Code Reuse**: TagReaderはTagRepositoryの既存readロジック（query_utils等）を継承
2. **Single Responsibility**: TagReader（単一DB読取）、MergedTagReader（複数DB統合）、TagRepository（書込）の責任分離
3. **Maintainability**: 複雑なsearch_tags等のロジックは1箇所に集約

**Revised Implementation Strategy:**

### Phase 0: Create TagReader Class (NEW)
**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py` (insert before MergedTagReader)

```python
class TagReader:
    """Read-only tag repository for single database access.

    Contains all get_*/list_*/search_* methods extracted from TagRepository.
    Reuses existing query_utils and database logic.
    """

    def __init__(self, session_factory: Callable[[], Session]):
        self.logger = logging.getLogger("TagReader")
        self.session_factory = session_factory

    # Move all 27 get_*/list_*/search_* methods from TagRepository here
    def get_tag_id_by_name(self, keyword: str, partial: bool = False) -> int | None:
        # Existing implementation from TagRepository (lines ~70-92)
        ...

    def get_tag_by_id(self, tag_id: int) -> Tag | None:
        # Existing implementation from TagRepository (lines ~94-99)
        ...

    # ... (all other read methods)
```

### Phase 1: Update MergedTagReader to Use TagReader
**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py` (lines ~660-919)

**Change delegation target from TagRepository to TagReader:**

```python
class MergedTagReader:
    def __init__(
        self,
        base_repo: TagReader | list[TagReader],
        user_repo: TagReader | None = None,
    ):
        # Store TagReader instances instead of TagRepository
        if isinstance(base_repo, list):
            self.base_repos = base_repo
        else:
            self.base_repos = [base_repo]
        self.user_repo = user_repo

    def get_tag_id_by_name(self, keyword: str, partial: bool = False) -> int | None:
        if self._has_user():
            user_id = self.user_repo.get_tag_id_by_name(keyword, partial=partial)  # ← Now calls TagReader
            if user_id is not None:
                return user_id
        for repo in self._iter_base_repos():
            base_id = repo.get_tag_id_by_name(keyword, partial=partial)  # ← Now calls TagReader
            if base_id is not None:
                return base_id
        return None
```

**Add 6 missing methods** (same merge logic, delegate to TagReader):
- get_max_tag_id() - Pattern C (max across all)
- get_metadata_value(key) - Pattern A (user → base priority)
- get_type_name_by_format_type_id() - Pattern A (first-match)
- get_type_id(type_name) - Pattern A (first-match)
- get_tag_format_ids() - Pattern C (union)
- list_translations() - Pattern B (merge + dedupe)

### Phase 2: Update Factory Functions
**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py` (line ~960)

**Split into 3 functions:**

```python
def get_default_reader() -> MergedTagReader:
    """デフォルトのMergedTagReaderを返す（読み取り専用）"""
    from genai_tag_db_tools.db.runtime import (
        get_base_session_factories,
        get_user_session_factory_optional,
    )

    user_factory = get_user_session_factory_optional()
    user_reader = TagReader(session_factory=user_factory) if user_factory else None

    base_factories = get_base_session_factories()
    if not base_factories:
        if user_reader:
            return MergedTagReader(base_repo=user_reader, user_repo=None)
        raise ValueError("No database available")

    if len(base_factories) == 1:
        base_reader = TagReader(session_factory=base_factories[0])
        return MergedTagReader(base_repo=base_reader, user_repo=user_reader)

    base_readers = [TagReader(session_factory=f) for f in base_factories]
    return MergedTagReader(base_repo=base_readers, user_repo=user_reader)


def get_default_repository() -> TagRepository:
    """デフォルトのTagRepositoryを返す（書き込み可能、ユーザーDBのみ）"""
    from genai_tag_db_tools.db.runtime import get_user_session_factory_optional

    user_factory = get_user_session_factory_optional()
    if not user_factory:
        raise ValueError("User database not available for write operations")

    # Inject reader for create_tag/ensure_tag_with_id
    reader = get_default_reader()
    return TagRepository(session_factory=user_factory, reader=reader)
```

### Phase 3: Update TagRepository (Simplified)
**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py` (line ~32)

**Only inject reader (no major constructor changes):**

```python
def __init__(
    self,
    session_factory: Callable[[], Session] | None = None,
    reader: MergedTagReader | None = None
):
    self.logger = logging.getLogger("TagRepository")
    if session_factory:
        self.session_factory = session_factory
    else:
        self.session_factory = get_session_factory()
    self._reader = reader  # For read ops in create_tag/ensure_tag_with_id
```

**Update create_tag() and ensure_tag_with_id()** to use `self._reader` instead of `self.get_*()`.

### Phase 4: Remove Read Methods from TagRepository
**Location:** `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py`

**Delete lines ~70-622 (all 27 get_*/list_*/search_* methods).**

Keep only:
- create_tag
- create_tag_with_id
- ensure_tag_with_id
- update_tag
- delete_tag
- update_tag_status
- delete_tag_status
- update_usage_count
- add_or_update_translation
- bulk_insert_tags
- _fetch_existing_tags_as_map

**Rationale:** All read logic now in TagReader, no duplication.

### Phase 5-6: Service Layer & Tests (Unchanged)
Same as original plan - update call sites to use `get_default_reader()` and inject reader where needed.
