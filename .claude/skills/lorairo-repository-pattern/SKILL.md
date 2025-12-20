---
name: lorairo-repository-pattern
description: SQLAlchemy repository pattern implementation guide for LoRAIro database operations with type-safe transactions, session management, and ORM best practices. Use when creating new repositories, implementing database access layers, or following LoRAIro's data persistence patterns.
allowed-tools:
  # Code exploration (recommended)
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  - mcp__serena__find_referencing_symbols
  # Memory (design patterns)
  - mcp__serena__read_memory
  - mcp__cipher__cipher_memory_search
  # Fallback
  - Read
  - Write
  - Edit
---

# LoRAIro Repository Pattern

SQLAlchemy repository pattern implementation guide for type-safe database operations in LoRAIro.

## When to Use

Use this skill when:
- Creating new database access layers
- Extending or refactoring existing repositories
- Implementing database transaction processing
- Query patterns and performance tuning

## Core Repository Pattern

### Basic Structure

```python
from typing import Optional
from sqlalchemy.orm import Session
from src.lorairo.database.schema import Entity

class EntityRepository:
    """Data access repository for Entity"""

    def __init__(self, session_factory):
        """Args: session_factory - SQLAlchemy scoped_session"""
        self.session_factory = session_factory

    def get_by_id(self, entity_id: int) -> Optional[Entity]:
        """Retrieve entity by ID"""
        with self.session_factory() as session:
            return session.query(Entity).filter(Entity.id == entity_id).first()

    def add(self, entity: Entity) -> Entity:
        """Add new entity"""
        with self.session_factory() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
```

**Key Principles:**
- Session management via `with` statement (automatic commit/rollback)
- Type hints for all parameters and returns
- Single responsibility (one repository per entity)
- Transaction safety (related operations in single transaction)

## Implementation Patterns

### 1. Session Management

**Pattern:** Context manager for automatic session lifecycle

```python
# ✅ Good: with statement (auto-managed)
with self.session_factory() as session:
    result = session.query(Entity).all()
    return result  # Auto commit/rollback on exit

# ❌ Bad: Manual session management
session = self.session_factory()
try:
    result = session.query(Entity).all()
    session.commit()
finally:
    session.close()  # Verbose and error-prone
```

**Why:** Context manager ensures proper cleanup even on exceptions.

### 2. Transaction Management

**Pattern:** Single transaction for related operations

```python
def batch_add(self, entities: list[Entity]) -> list[Entity]:
    """Batch add entities in single transaction"""
    with self.session_factory() as session:
        session.add_all(entities)
        session.commit()
        return entities

def complex_operation(self, data: dict) -> bool:
    """Multi-table operation in single transaction"""
    with self.session_factory() as session:
        entity1 = Entity(**data['entity1'])
        session.add(entity1)

        entity2 = RelatedEntity(parent_id=entity1.id, **data['entity2'])
        session.add(entity2)

        session.commit()  # Atomic: all or nothing
        return True
```

**Why:** ACID compliance, data consistency, automatic rollback on error.

### 3. Type-Safe Queries

**Pattern:** Use dataclass for search criteria

```python
from dataclasses import dataclass

@dataclass
class SearchCriteria:
    """Type-safe search criteria"""
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None

def search(self, criteria: SearchCriteria) -> list[Entity]:
    """Type-safe search with criteria"""
    with self.session_factory() as session:
        query = session.query(Entity)

        if criteria.tags:
            query = query.filter(Entity.tags.contains(criteria.tags))
        if criteria.min_score is not None:
            query = query.filter(Entity.score >= criteria.min_score)

        return query.all()
```

**Why:** Compile-time type checking, IDE autocomplete, self-documenting API.

### 4. Error Handling

**Pattern:** Catch specific SQLAlchemy exceptions

```python
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from loguru import logger

def add_safe(self, entity: Entity) -> Optional[Entity]:
    """Safe add with error handling"""
    try:
        with self.session_factory() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
    except IntegrityError as e:
        logger.error(f"Integrity error: {e}")
        return None
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        return None
```

**Why:** Specific error handling, proper logging, graceful degradation.

## LoRAIro-Specific Guidelines

### File Structure
```
src/lorairo/database/
├── db_repository.py    # Repository implementations
├── schema.py           # SQLAlchemy models
├── db_manager.py       # High-level database operations
└── db_core.py          # Session factory, engine initialization
```

### Naming Conventions
- **Repository class:** `{Entity}Repository` (e.g., `ImageRepository`, `TagRepository`)
- **CRUD methods:** `get_by_id`, `get_all`, `add`, `update`, `delete`
- **Search methods:** `search`, `find_by_{field}`, `filter_by_{condition}`

### Integration with Services
```
Service Layer (business logic)
      ↓ uses
Repository Layer (data access)
      ↓ uses
SQLAlchemy ORM (database abstraction)
      ↓
SQLite Database
```

**Separation of Concerns:**
- **Repository:** Pure data access (CRUD, queries)
- **Service:** Business logic (validation, workflows, coordination)
- **Manager:** High-level operations (migrations, initialization)

## Memory-First Workflow

### Before Implementation
1. **Search past patterns (Cipher):**
   - `mcp__cipher__cipher_memory_search(query="repository pattern sqlalchemy")` → Past repository implementations
2. **Check project status (Serena):**
   - `mcp__serena__read_memory("current-project-status")` → Current database schema
3. **Explore existing repositories (Serena):**
   - `mcp__serena__find_symbol(name_path="Repository", relative_path="src/lorairo/database/")` → Existing patterns

### During Implementation
**Track progress (Serena):**
```markdown
mcp__serena__write_memory(
  memory_name="active-development-tasks",
  content="## Implementing {Entity}Repository
  - [x] Basic CRUD operations
  - [ ] Complex queries
  - [ ] Error handling
  - [ ] Unit tests"
)
```

### After Implementation
**Store knowledge (Cipher):**
```markdown
mcp__cipher__cipher_extract_and_operate_memory(
  interaction="Implemented {Entity}Repository with:
  - Session management via context manager
  - Type-safe search criteria using dataclass
  - Transaction safety for batch operations
  - Comprehensive error handling with logging",
  memoryMetadata={"projectId": "lorairo", "domain": "backend"}
)
```

See [mcp-memory-first-development](../mcp-memory-first-development/SKILL.md) for complete workflow.

## Best Practices Checklist

### DO ✅
- Use `with` statement for session management
- Add type hints to all methods
- Keep single responsibility (1 repository = 1 entity)
- Group related operations in single transaction
- Log all database errors with context
- Use eager loading (`joinedload`) to avoid N+1 queries
- Write unit tests for all repository methods

### DON'T ❌
- Manual session management with try-finally
- Mix business logic into repository layer
- Use raw SQL strings (use ORM methods)
- Create global session objects
- Ignore transaction boundaries
- Return detached objects without refresh

## Performance Patterns

### Eager Loading (Avoid N+1)
```python
from sqlalchemy.orm import joinedload

def get_with_relations(self, entity_id: int) -> Optional[Entity]:
    """Load entity with related data (single query)"""
    with self.session_factory() as session:
        return session.query(Entity)\
            .options(joinedload(Entity.related_items))\
            .filter(Entity.id == entity_id)\
            .first()
```

### Batch Operations
```python
def bulk_update_scores(self, score_updates: dict[int, float]) -> int:
    """Bulk update scores efficiently"""
    with self.session_factory() as session:
        session.bulk_update_mappings(
            Entity,
            [{"id": id, "score": score} for id, score in score_updates.items()]
        )
        session.commit()
        return len(score_updates)
```

### Query Caching
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_config(self) -> dict:
    """Cache static configuration data"""
    with self.session_factory() as session:
        return session.query(Config).first().to_dict()
```

## Reference Files

- [examples.md](./examples.md) - Complete repository implementation examples
- [reference.md](./reference.md) - Full API patterns and method signatures
- [testing-patterns.md](./testing-patterns.md) - Test strategies and pytest patterns

## Quick Reference

**Essential Patterns:**
- Session: `with self.session_factory() as session:`
- Query: `session.query(Entity).filter(Entity.field == value).first()`
- Add: `session.add(entity); session.commit(); session.refresh(entity)`
- Update: `session.merge(entity); session.commit()`
- Delete: `session.delete(entity); session.commit()`

**File Locations:**
- Implementation: `src/lorairo/database/db_repository.py`
- Schema: `src/lorairo/database/schema.py`
- Tests: `tests/database/test_db_repository.py`
