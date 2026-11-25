---
name: lorairo-repository-pattern
version: "1.0.0"
description: "SQLAlchemy repository pattern for LoRAIro: type-safe transactions, session management, ORM best practices. Use when creating repositories or implementing data persistence patterns."
metadata:
  short-description: LoRAIro向けSQLAlchemyリポジトリ実装(トランザクション、セッション、ORM)。
allowed-tools:
  # Code exploration (recommended)
  - Grep
  - Grep
  - Grep
  # Memory (design patterns)
  - Grep
  # Fallback
  - Read
  - Write
  - Edit
  - Bash
dependencies:
  - sqlalchemy-query-patterns
---

# LoRAIro リポジトリパターン実装ガイド

LoRAIro において、SQLAlchemy を用いた型安全なデータベース操作を実現するためのリポジトリパターン実装ガイドである。

## 適用場面

- 新しいデータベースアクセス層を作成するとき
- 既存のリポジトリを拡張またはリファクタリングするとき
- データベースのトランザクション処理を実装するとき
- クエリパターンやパフォーマンスを調整するとき

## コアリポジトリパターン

### 基本構造

```python
from sqlalchemy import select
from lorairo.database.repository.base import BaseRepository
from lorairo.database.schema import Image

class ImageRepository(BaseRepository):
    """Data access repository for Image aggregate (inherits BaseRepository)."""

    def get_by_id(self, image_id: int) -> Image | None:
        """Retrieve entity by ID using SQLAlchemy 2.0 select()."""
        with self.session_factory() as session:
            stmt = select(Image).where(Image.id == image_id)
            return session.execute(stmt).scalar_one_or_none()

    def add(self, entity: Image) -> Image:
        """Add new entity."""
        with self.session_factory() as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
```

**基本原則:**

- `BaseRepository`(`src/lorairo/database/repository/base.py`)を継承し、`session_factory` と `BATCH_CHUNK_SIZE` を共有する。
- セッション管理には `with self.session_factory() as session:` を使い、終了時の後片付けを自動化する。
- 旧来の `session.query()` ではなく、SQLAlchemy 2.0 の `select()` API(`session.execute(select(...))`)を使う。
- 集約単位で分割したリポジトリを `ImageDatabaseManager` で合成する(ADR 0035)。
- 関連する操作は 1 つのトランザクションにまとめ、安全性を確保する。

## 実装パターン

### 1. セッション管理

コンテキストマネージャーでセッションのライフサイクルを自動管理する。

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

**理由**: 例外が発生しても確実にセッションがクローズされ、リソースリークを防げる。

### 2. トランザクション管理

関連する複数の操作は 1 つのトランザクション内で完結させる。

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

**理由**: ACID 特性とデータ整合性を保ち、エラー発生時の自動ロールバックを保証する。

### 3. 型安全なクエリ

検索条件には `dataclass` を使用する。

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

**理由**: 静的型チェックと IDE 補完が効き、自己文書化された API になる。

### 4. エラーハンドリング

具体的な SQLAlchemy 例外を捕捉して記録する。

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

**理由**: 障害原因に応じた処理と適切なログ出力ができ、安全にフォールバックできる。

## LoRAIro 固有のガイドライン

### ファイル構成(ADR 0035 集約分割)

```
src/lorairo/database/
├── repository/                 # Aggregate-scoped Repository implementations (ADR 0035)
│   ├── base.py                 # BaseRepository (session_factory, BATCH_CHUNK_SIZE)
│   ├── image.py                # ImageRepository (Image, ProcessedImage, ImageFilenameAlias)
│   ├── annotation_record.py    # AnnotationRepository (Tag, Caption, Score, ScoreLabel, Rating)
│   ├── model.py                # ModelRepository (Model, ModelType)
│   ├── project.py              # ProjectRepository (Project)
│   ├── error_record.py         # ErrorRecordRepository (ErrorRecord)
│   ├── provider_batch.py       # ProviderBatchRepository (ProviderBatchJob, ProviderBatchItem)
│   ├── crop_relation.py        # CropRelationRepository (CropRelation)
│   └── generation_metadata.py  # GenerationMetadataRepository (GenerationMetadata)
├── filter_criteria.py          # ImageFilterCriteria / KeywordSearchGroup
├── schema.py                   # SQLAlchemy models
├── db_manager.py               # ImageDatabaseManager (composes the aggregate repositories)
└── db_core.py                  # Session factory, engine initialization (QueuePool / WAL)
```

### 命名規則

- **リポジトリクラス**: `{Entity}Repository`(例: `ImageRepository`、`TagRepository`)
- **CRUD メソッド**: `get_by_id`、`get_all`、`add`、`update`、`delete`
- **検索メソッド**: `search`、`find_by_{field}`、`filter_by_{condition}`

### サービス層との連携

```
Service Layer (business logic)
      ↓ uses
Repository Layer (data access)
      ↓ uses
SQLAlchemy ORM (database abstraction)
      ↓
SQLite Database
```

**責務の分離:**

- **Repository**: 純粋なデータアクセス(CRUD やクエリ)
- **Service**: ビジネスロジック(バリデーション、ワークフロー、処理の調整)
- **Manager**: 高水準の操作(マイグレーション、初期化)

## ベストプラクティスチェックリスト

### 推奨事項

- セッション管理には `with` 文を使う。
- すべてのメソッドに型ヒントを付ける。
- 単一責任を維持する(1 リポジトリ = 1 エンティティ・集約)。
- 関連操作は 1 つのトランザクションにまとめる。
- すべてのデータベースエラーを文脈情報付きでログ出力する。
- N+1 クエリを防ぐため、Eager Loading(`joinedload` など)を使う。
- すべてのリポジトリメソッドにユニットテストを書く。

### 禁止事項

- `try-finally` による手動セッション管理を行わない。
- リポジトリ層にビジネスロジックを混ぜない。
- 生の SQL 文字列を使わない(ORM メソッドを使う)。
- グローバルなセッションオブジェクトを作成しない。
- トランザクション境界を無視しない。
- `refresh` せずにデタッチ済みオブジェクトを返さない。

## パフォーマンスパターン

### Eager Loading(N+1 の回避)

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

### バッチ操作

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

### クエリキャッシュ

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_config(self) -> dict:
    """Cache static configuration data"""
    with self.session_factory() as session:
        return session.query(Config).first().to_dict()
```

## リファレンスファイル

- [examples.md](./examples.md): リポジトリ実装の完全なサンプル
- [reference.md](./reference.md): API パターンとメソッドシグネチャ一覧
- [testing-patterns.md](./testing-patterns.md): テスト戦略と pytest パターン

## クイックリファレンス

**基本操作:**

- セッション: `with self.session_factory() as session:`
- クエリ: `session.execute(select(Entity).where(Entity.field == value)).scalar_one_or_none()`
- 追加: `session.add(entity); session.commit(); session.refresh(entity)`
- 更新: `session.merge(entity); session.commit()`
- 削除: `session.delete(entity); session.commit()`

**ファイル配置:**

- 実装: `src/lorairo/database/repository/*.py`(`src/lorairo/database/db_manager.py` が合成)
- スキーマ: `src/lorairo/database/schema.py`
- テスト: `tests/unit/database/repository/test_*_repository.py`
