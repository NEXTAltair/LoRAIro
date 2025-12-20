# Repository Pattern API Reference

Complete API reference for SQLAlchemy repository pattern in LoRAIro.

## Core Repository Interface

### Standard Method Signatures

All repositories should implement these standard methods:

```python
class EntityRepository:
    """Base repository pattern for entity data access"""

    def __init__(self, session_factory: scoped_session) -> None:
        """Initialize with session factory"""

    def get_by_id(self, entity_id: int) -> Optional[Entity]:
        """Retrieve single entity by primary key"""

    def get_all(self, limit: Optional[int] = None) -> list[Entity]:
        """Retrieve all entities with optional limit"""

    def add(self, entity: Entity) -> Entity:
        """Add new entity and return with generated ID"""

    def batch_add(self, entities: list[Entity]) -> list[Entity]:
        """Add multiple entities in single transaction"""

    def update(self, entity: Entity) -> Entity:
        """Update existing entity"""

    def delete(self, entity_id: int) -> bool:
        """Delete entity by ID, return True if found"""

    def exists(self, entity_id: int) -> bool:
        """Check if entity exists"""

    def count(self) -> int:
        """Count total entities"""
```

## Query Patterns

### Basic Queries

```python
# Single result
entity = session.query(Entity).filter(Entity.id == value).first()

# Multiple results
entities = session.query(Entity).filter(Entity.field == value).all()

# Count
count = session.query(Entity).filter(Entity.field == value).count()

# Exists check
exists = session.query(Entity.id).filter(Entity.id == value).first() is not None
```

### Filtering Patterns

```python
# Equality
query.filter(Entity.field == value)

# Inequality
query.filter(Entity.field != value)

# Comparison
query.filter(Entity.score >= min_value)
query.filter(Entity.score <= max_value)

# Range (AND)
query.filter(Entity.score >= min_value, Entity.score <= max_value)

# IN clause
query.filter(Entity.id.in_([1, 2, 3]))

# LIKE (case-sensitive)
query.filter(Entity.name.like("pattern%"))

# ILIKE (case-insensitive, PostgreSQL only)
query.filter(Entity.name.ilike("pattern%"))

# IS NULL / IS NOT NULL
query.filter(Entity.field.is_(None))
query.filter(Entity.field.isnot(None))

# AND logic (multiple conditions)
from sqlalchemy import and_
query.filter(and_(
    Entity.field1 == value1,
    Entity.field2 == value2
))

# OR logic
from sqlalchemy import or_
query.filter(or_(
    Entity.field1 == value1,
    Entity.field2 == value2
))

# NOT logic
from sqlalchemy import not_
query.filter(not_(Entity.field == value))
# Or using ~
query.filter(~Entity.field == value)
```

### Ordering Patterns

```python
# Ascending
query.order_by(Entity.created_at)

# Descending
query.order_by(Entity.score.desc())

# Multiple columns
query.order_by(Entity.category, Entity.score.desc())

# Null values first/last
query.order_by(Entity.field.nullsfirst())
query.order_by(Entity.field.nullslast())
```

### Pagination Patterns

```python
# Limit
query.limit(10)

# Offset
query.offset(20)

# Combined (page 3, page size 10)
page = 3
page_size = 10
query.offset((page - 1) * page_size).limit(page_size)

# Slice notation
query.slice(20, 30)  # Offset 20, limit 10
```

### Aggregation Patterns

```python
from sqlalchemy import func

# Count
count = session.query(func.count(Entity.id)).scalar()

# Sum
total = session.query(func.sum(Entity.score)).scalar()

# Average
avg_score = session.query(func.avg(Entity.score)).scalar()

# Min/Max
min_score = session.query(func.min(Entity.score)).scalar()
max_score = session.query(func.max(Entity.score)).scalar()

# Group by
results = session.query(
    Entity.category,
    func.count(Entity.id)
).group_by(Entity.category).all()

# Having clause
results = session.query(
    Entity.category,
    func.count(Entity.id)
).group_by(Entity.category)\
 .having(func.count(Entity.id) > 5).all()
```

## Join Patterns

### Eager Loading (Avoid N+1)

```python
from sqlalchemy.orm import joinedload, selectinload, subqueryload

# joinedload - Single query with LEFT OUTER JOIN
# Best for: One-to-one, one-to-many (small collections)
entities = session.query(Entity)\
    .options(joinedload(Entity.related))\
    .all()

# selectinload - Separate SELECT IN query
# Best for: One-to-many (large collections)
entities = session.query(Entity)\
    .options(selectinload(Entity.related_items))\
    .all()

# subqueryload - Separate subquery
# Best for: Complex relationships
entities = session.query(Entity)\
    .options(subqueryload(Entity.related_items))\
    .all()

# Nested eager loading
entities = session.query(Entity)\
    .options(
        joinedload(Entity.related)\
        .joinedload(Related.nested)
    )\
    .all()

# Multiple relationships
entities = session.query(Entity)\
    .options(
        joinedload(Entity.related1),
        selectinload(Entity.related2)
    )\
    .all()
```

### Explicit Joins

```python
# Inner join
query.join(Entity.related)

# Left outer join
query.outerjoin(Entity.related)

# Join with filter
query.join(Entity.related).filter(Related.field == value)

# Multiple joins
query.join(Entity.related1).join(Entity.related2)

# Join on specific condition
from sqlalchemy import and_
query.join(
    Related,
    and_(
        Entity.id == Related.entity_id,
        Related.active == True
    )
)
```

## Transaction Patterns

### Basic Transaction

```python
with session_factory() as session:
    # All operations in single transaction
    entity1 = Entity(field="value1")
    session.add(entity1)

    entity2 = Entity(field="value2")
    session.add(entity2)

    session.commit()  # Atomic commit
    # Auto-rollback on exception
```

### Manual Rollback

```python
with session_factory() as session:
    try:
        # Operations
        session.add(entity)
        session.commit()
    except IntegrityError:
        session.rollback()  # Explicit rollback
        # Handle error
```

### Savepoints (Nested Transactions)

```python
with session_factory() as session:
    session.add(entity1)
    session.commit()

    # Create savepoint
    savepoint = session.begin_nested()

    try:
        session.add(entity2)
        session.commit()
    except Exception:
        savepoint.rollback()  # Rollback to savepoint
        # entity1 still committed
```

### Flush vs Commit

```python
with session_factory() as session:
    entity = Entity(field="value")
    session.add(entity)

    # Flush: Execute SQL without committing transaction
    # Use to get generated ID before commit
    session.flush()
    print(f"Generated ID: {entity.id}")  # Available after flush

    # Commit: Commit transaction
    session.commit()
```

## Error Handling Patterns

### Specific Exception Handling

```python
from sqlalchemy.exc import (
    IntegrityError,      # Constraint violations (unique, foreign key)
    DataError,           # Invalid data type
    OperationalError,    # Connection issues, timeout
    DatabaseError,       # Generic database error
    SQLAlchemyError      # Base exception class
)

def safe_operation(entity: Entity) -> Optional[Entity]:
    try:
        with session_factory() as session:
            session.add(entity)
            session.commit()
            return entity

    except IntegrityError as e:
        # Constraint violation
        logger.error(f"Integrity error: {e}")
        return None

    except OperationalError as e:
        # Connection/timeout
        logger.error(f"Operational error: {e}")
        return None

    except DataError as e:
        # Invalid data
        logger.error(f"Data error: {e}")
        return None

    except SQLAlchemyError as e:
        # Other database errors
        logger.error(f"Database error: {e}")
        return None
```

### Retry Pattern

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def resilient_operation(entity: Entity) -> Entity:
    """Retry on transient failures"""
    with session_factory() as session:
        session.add(entity)
        session.commit()
        session.refresh(entity)
        return entity
```

## Performance Patterns

### Bulk Operations

```python
# Bulk insert (fastest, but bypasses ORM)
session.bulk_insert_mappings(
    Entity,
    [{"field1": "value1", "field2": "value2"} for _ in range(1000)]
)

# Bulk update
session.bulk_update_mappings(
    Entity,
    [{"id": 1, "field": "new_value"}, {"id": 2, "field": "new_value2"}]
)

# Bulk delete
session.query(Entity).filter(Entity.id.in_(ids)).delete(synchronize_session=False)
```

### Query Optimization

```python
# Select specific columns only
results = session.query(Entity.id, Entity.name).all()

# Defer loading expensive columns
from sqlalchemy.orm import defer
query.options(defer(Entity.large_binary_field))

# Load only (opposite of defer)
from sqlalchemy.orm import load_only
query.options(load_only(Entity.id, Entity.name))

# Disable relationship loading
from sqlalchemy.orm import lazyload
query.options(lazyload(Entity.related))
```

### Caching Patterns

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_static_config() -> dict:
    """Cache static configuration"""
    with session_factory() as session:
        return session.query(Config).first().to_dict()

# Clear cache when data changes
get_static_config.cache_clear()
```

## Type Safety Patterns

### Typed Search Criteria

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class SearchCriteria:
    """Type-safe search criteria"""
    # Required fields
    entity_type: str

    # Optional filters
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    created_after: Optional[datetime] = None

    # Pagination
    page: int = 1
    page_size: int = 20

    def validate(self) -> None:
        """Validate criteria"""
        if self.min_score and self.max_score:
            assert self.min_score <= self.max_score
        assert self.page > 0
        assert self.page_size > 0
```

### Typed Return Objects

```python
from typing import NamedTuple

class SearchResult(NamedTuple):
    """Type-safe search results"""
    entities: list[Entity]
    total_count: int
    page: int
    page_size: int
    total_pages: int

def search_typed(criteria: SearchCriteria) -> SearchResult:
    """Return type-safe results"""
    with session_factory() as session:
        query = session.query(Entity)
        # Apply filters...

        total_count = query.count()
        entities = query.offset((criteria.page - 1) * criteria.page_size)\
            .limit(criteria.page_size)\
            .all()

        total_pages = (total_count + criteria.page_size - 1) // criteria.page_size

        return SearchResult(
            entities=entities,
            total_count=total_count,
            page=criteria.page,
            page_size=criteria.page_size,
            total_pages=total_pages
        )
```

## Common Patterns by Use Case

### Read-Heavy Application

```python
class CachedRepository(EntityRepository):
    """Repository with read caching"""

    def __init__(self, session_factory, cache):
        super().__init__(session_factory)
        self.cache = cache

    def get_by_id(self, entity_id: int) -> Optional[Entity]:
        # Check cache first
        cache_key = f"entity:{entity_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Cache miss: query database
        entity = super().get_by_id(entity_id)
        if entity:
            self.cache.set(cache_key, entity, timeout=300)
        return entity

    def update(self, entity: Entity) -> Entity:
        # Invalidate cache on update
        cache_key = f"entity:{entity.id}"
        self.cache.delete(cache_key)
        return super().update(entity)
```

### Write-Heavy Application

```python
class BatchingRepository(EntityRepository):
    """Repository with write batching"""

    def __init__(self, session_factory, batch_size=1000):
        super().__init__(session_factory)
        self.batch_size = batch_size

    def add_many_optimized(self, entities: list[Entity]) -> list[Entity]:
        """Add with automatic batching"""
        added = []

        for i in range(0, len(entities), self.batch_size):
            batch = entities[i:i + self.batch_size]
            added.extend(self.batch_add(batch))

        return added
```

### Audit Logging

```python
class AuditedRepository(EntityRepository):
    """Repository with automatic audit logging"""

    def add(self, entity: Entity) -> Entity:
        result = super().add(entity)
        self._log_audit("CREATE", result.id, result)
        return result

    def update(self, entity: Entity) -> Entity:
        result = super().update(entity)
        self._log_audit("UPDATE", result.id, result)
        return result

    def delete(self, entity_id: int) -> bool:
        result = super().delete(entity_id)
        if result:
            self._log_audit("DELETE", entity_id, None)
        return result

    def _log_audit(self, action: str, entity_id: int, entity: Optional[Entity]):
        with self.session_factory() as session:
            audit = AuditLog(
                action=action,
                entity_type="Entity",
                entity_id=entity_id,
                timestamp=datetime.utcnow()
            )
            session.add(audit)
            session.commit()
```

## SQLAlchemy 2.0 Style (Future)

### Modern Query API

```python
from sqlalchemy import select

# 2.0 style select
stmt = select(Entity).where(Entity.id == value)
result = session.execute(stmt).scalars().all()

# 2.0 style with joins
stmt = select(Entity).join(Entity.related).where(Related.field == value)
results = session.execute(stmt).scalars().all()

# 2.0 style aggregation
stmt = select(func.count(Entity.id)).where(Entity.active == True)
count = session.execute(stmt).scalar()
```

### Async Support (SQLAlchemy 2.0+)

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

async def async_get_by_id(session: AsyncSession, entity_id: int) -> Optional[Entity]:
    """Async repository method"""
    stmt = select(Entity).where(Entity.id == entity_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

## Best Practices Summary

### Session Management
- ✅ Always use context manager (`with session_factory() as session:`)
- ✅ One session per request/transaction
- ❌ Never store session as instance variable
- ❌ Never use global session

### Query Performance
- ✅ Use eager loading to avoid N+1 queries
- ✅ Select only needed columns for large datasets
- ✅ Use bulk operations for batch processing
- ❌ Avoid lazy loading in loops
- ❌ Don't query in loops (use batch queries)

### Error Handling
- ✅ Catch specific SQLAlchemy exceptions
- ✅ Log all database errors with context
- ✅ Return None or raise custom exceptions
- ❌ Don't silently swallow errors
- ❌ Don't expose internal exceptions to UI

### Type Safety
- ✅ Use type hints for all methods
- ✅ Use dataclasses for criteria
- ✅ Use NamedTuple/dataclass for results
- ❌ Don't use Any type
- ❌ Don't use dict for structured data

### Testing
- ✅ Use in-memory SQLite for tests
- ✅ Use fixtures for session factory
- ✅ Test error cases
- ❌ Don't test against production database
- ❌ Don't share sessions between tests
