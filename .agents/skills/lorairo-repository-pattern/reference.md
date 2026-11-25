# リポジトリパターン API リファレンス

LoRAIro における SQLAlchemy リポジトリパターンの完全な API リファレンスである。

## コアリポジトリインターフェース

### 標準メソッドシグネチャ

すべてのリポジトリは、次の標準メソッド群を実装する。

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

## クエリパターン

### 基本クエリ

```python
# 単一レコードの取得
entity = session.query(Entity).filter(Entity.id == value).first()

# 複数レコードの取得
entities = session.query(Entity).filter(Entity.field == value).all()

# 件数の取得
count = session.query(Entity).filter(Entity.field == value).count()

# 存在確認
exists = session.query(Entity.id).filter(Entity.id == value).first() is not None
```

### フィルタリングパターン

```python
# 等価
query.filter(Entity.field == value)

# 不等価
query.filter(Entity.field != value)

# 大小比較
query.filter(Entity.score >= min_value)
query.filter(Entity.score <= max_value)

# 範囲指定 (AND)
query.filter(Entity.score >= min_value, Entity.score <= max_value)

# IN 句
query.filter(Entity.id.in_([1, 2, 3]))

# LIKE (大文字・小文字を区別)
query.filter(Entity.name.like("pattern%"))

# ILIKE (大文字・小文字を区別しない、PostgreSQL 専用)
query.filter(Entity.name.ilike("pattern%"))

# IS NULL / IS NOT NULL
query.filter(Entity.field.is_(None))
query.filter(Entity.field.isnot(None))

# AND 条件 (複数条件)
from sqlalchemy import and_
query.filter(and_(
    Entity.field1 == value1,
    Entity.field2 == value2
))

# OR 条件
from sqlalchemy import or_
query.filter(or_(
    Entity.field1 == value1,
    Entity.field2 == value2
))

# NOT 条件
from sqlalchemy import not_
query.filter(not_(Entity.field == value))
# または ~ 演算子を使う
query.filter(~Entity.field == value)
```

### 並び替えパターン

```python
# 昇順
query.order_by(Entity.created_at)

# 降順
query.order_by(Entity.score.desc())

# 複数カラム
query.order_by(Entity.category, Entity.score.desc())

# NULL 値の先頭/末尾配置
query.order_by(Entity.field.nullsfirst())
query.order_by(Entity.field.nullslast())
```

### ページネーションパターン

```python
# 件数上限
query.limit(10)

# 開始位置
query.offset(20)

# 併用 (3 ページ目、1 ページ 10 件)
page = 3
page_size = 10
query.offset((page - 1) * page_size).limit(page_size)

# スライス記法
query.slice(20, 30)  # オフセット 20、件数 10
```

### 集計パターン

```python
from sqlalchemy import func

# 件数
count = session.query(func.count(Entity.id)).scalar()

# 合計
total = session.query(func.sum(Entity.score)).scalar()

# 平均
avg_score = session.query(func.avg(Entity.score)).scalar()

# 最小値/最大値
min_score = session.query(func.min(Entity.score)).scalar()
max_score = session.query(func.max(Entity.score)).scalar()

# グルーピング
results = session.query(
    Entity.category,
    func.count(Entity.id)
).group_by(Entity.category).all()

# HAVING 句
results = session.query(
    Entity.category,
    func.count(Entity.id)
).group_by(Entity.category)\
 .having(func.count(Entity.id) > 5).all()
```

## 結合パターン

### Eager Loading(N+1 問題の回避)

```python
from sqlalchemy.orm import joinedload, selectinload, subqueryload

# joinedload - LEFT OUTER JOIN による単一クエリ
# 適用先: 1 対 1、または要素数の少ない 1 対多
entities = session.query(Entity)\
    .options(joinedload(Entity.related))\
    .all()

# selectinload - 別の SELECT IN クエリで一括取得
# 適用先: 要素数の多い 1 対多
entities = session.query(Entity)\
    .options(selectinload(Entity.related_items))\
    .all()

# subqueryload - サブクエリで一括取得
# 適用先: 複雑なリレーションシップ
entities = session.query(Entity)\
    .options(subqueryload(Entity.related_items))\
    .all()

# ネストした Eager Loading
entities = session.query(Entity)\
    .options(
        joinedload(Entity.related)\
        .joinedload(Related.nested)
    )\
    .all()

# 複数リレーションシップの同時読み込み
entities = session.query(Entity)\
    .options(
        joinedload(Entity.related1),
        selectinload(Entity.related2)
    )\
    .all()
```

### 明示的な結合

```python
# 内部結合
query.join(Entity.related)

# 左外部結合
query.outerjoin(Entity.related)

# 結合先テーブルでの絞り込み
query.join(Entity.related).filter(Related.field == value)

# 複数テーブルの結合
query.join(Entity.related1).join(Entity.related2)

# 条件を明示した結合
from sqlalchemy import and_
query.join(
    Related,
    and_(
        Entity.id == Related.entity_id,
        Related.active == True
    )
)
```

## トランザクションパターン

### 基本トランザクション

```python
with session_factory() as session:
    # すべての操作を 1 つのトランザクションにまとめる
    entity1 = Entity(field="value1")
    session.add(entity1)

    entity2 = Entity(field="value2")
    session.add(entity2)

    session.commit()  # アトミックにコミット
    # 例外発生時は自動ロールバック
```

### 手動ロールバック

```python
with session_factory() as session:
    try:
        # DB 操作
        session.add(entity)
        session.commit()
    except IntegrityError:
        session.rollback()  # 明示的にロールバック
        # エラー処理
```

### セーブポイント(ネストしたトランザクション)

```python
with session_factory() as session:
    session.add(entity1)
    session.commit()

    # セーブポイントを作成
    savepoint = session.begin_nested()

    try:
        session.add(entity2)
        session.commit()
    except Exception:
        savepoint.rollback()  # セーブポイントまでロールバック
        # entity1 のコミットは維持される
```

### `flush` と `commit` の違い

```python
with session_factory() as session:
    entity = Entity(field="value")
    session.add(entity)

    # flush: トランザクションをコミットせずに SQL を発行する
    # コミット前に自動採番 ID を取得したいときに使う
    session.flush()
    print(f"Generated ID: {entity.id}")  # flush 後に参照できる

    # commit: トランザクションを確定する
    session.commit()
```

## エラーハンドリングパターン

### 具体的な例外の捕捉

```python
from sqlalchemy.exc import (
    IntegrityError,      # 制約違反 (一意制約、外部キー制約など)
    DataError,           # 不正なデータ型
    OperationalError,    # 接続障害、タイムアウト
    DatabaseError,       # 一般的なデータベースエラー
    SQLAlchemyError      # 基底例外クラス
)

def safe_operation(entity: Entity) -> Optional[Entity]:
    try:
        with session_factory() as session:
            session.add(entity)
            session.commit()
            return entity

    except IntegrityError as e:
        # 制約違反
        logger.error(f"Integrity error: {e}")
        return None

    except OperationalError as e:
        # 接続エラー/タイムアウト
        logger.error(f"Operational error: {e}")
        return None

    except DataError as e:
        # 不正なデータ
        logger.error(f"Data error: {e}")
        return None

    except SQLAlchemyError as e:
        # その他のデータベースエラー
        logger.error(f"Database error: {e}")
        return None
```

### リトライパターン

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

## パフォーマンスパターン

### バルク操作

```python
# バルクインサート (最速だが ORM のイベント等は経由しない)
session.bulk_insert_mappings(
    Entity,
    [{"field1": "value1", "field2": "value2"} for _ in range(1000)]
)

# バルクアップデート
session.bulk_update_mappings(
    Entity,
    [{"id": 1, "field": "new_value"}, {"id": 2, "field": "new_value2"}]
)

# バルクデリート
session.query(Entity).filter(Entity.id.in_(ids)).delete(synchronize_session=False)
```

### クエリ最適化

```python
# 必要なカラムだけを選択する
results = session.query(Entity.id, Entity.name).all()

# サイズの大きいカラムの読み込みを遅延させる
from sqlalchemy.orm import defer
query.options(defer(Entity.large_binary_field))

# 指定カラムのみ読み込む (defer の逆)
from sqlalchemy.orm import load_only
query.options(load_only(Entity.id, Entity.name))

# リレーションシップの事前読み込みを無効化する
from sqlalchemy.orm import lazyload
query.options(lazyload(Entity.related))
```

### キャッシュパターン

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_static_config() -> dict:
    """Cache static configuration"""
    with session_factory() as session:
        return session.query(Config).first().to_dict()

# データ変更時にキャッシュをクリアする
get_static_config.cache_clear()
```

## 型安全パターン

### 型付き検索条件

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class SearchCriteria:
    """Type-safe search criteria"""
    # 必須フィールド
    entity_type: str

    # 任意フィルター
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    created_after: Optional[datetime] = None

    # ページネーション
    page: int = 1
    page_size: int = 20

    def validate(self) -> None:
        """Validate criteria"""
        if self.min_score and self.max_score:
            assert self.min_score <= self.max_score
        assert self.page > 0
        assert self.page_size > 0
```

### 型付き戻り値オブジェクト

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
        # フィルター条件を適用する...

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

## ユースケース別パターン

### 読み込み中心のアプリケーション

```python
class CachedRepository(EntityRepository):
    """Repository with read caching"""

    def __init__(self, session_factory, cache):
        super().__init__(session_factory)
        self.cache = cache

    def get_by_id(self, entity_id: int) -> Optional[Entity]:
        # まずキャッシュを確認する
        cache_key = f"entity:{entity_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # キャッシュミス時はデータベースへ問い合わせる
        entity = super().get_by_id(entity_id)
        if entity:
            self.cache.set(cache_key, entity, timeout=300)
        return entity

    def update(self, entity: Entity) -> Entity:
        # 更新時にキャッシュを無効化する
        cache_key = f"entity:{entity.id}"
        self.cache.delete(cache_key)
        return super().update(entity)
```

### 書き込み中心のアプリケーション

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

### 監査ログ

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

## SQLAlchemy 2.0 スタイル(将来対応)

### モダンクエリ API

```python
from sqlalchemy import select

# 2.0 スタイルの select
stmt = select(Entity).where(Entity.id == value)
result = session.execute(stmt).scalars().all()

# 2.0 スタイルの結合
stmt = select(Entity).join(Entity.related).where(Related.field == value)
results = session.execute(stmt).scalars().all()

# 2.0 スタイルの集計
stmt = select(func.count(Entity.id)).where(Entity.active == True)
count = session.execute(stmt).scalar()
```

### 非同期サポート(SQLAlchemy 2.0+)

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

async def async_get_by_id(session: AsyncSession, entity_id: int) -> Optional[Entity]:
    """Async repository method"""
    stmt = select(Entity).where(Entity.id == entity_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

## ベストプラクティスまとめ

### セッション管理

- 推奨: 必ずコンテキストマネージャー(`with session_factory() as session:`)を使う。
- 推奨: 1 リクエストまたは 1 トランザクションにつき 1 セッションとする。
- 禁止: セッションをインスタンス変数に保持しない。
- 禁止: グローバルセッションを使わない。

### クエリパフォーマンス

- 推奨: Eager Loading を使って N+1 クエリを防ぐ。
- 推奨: 大規模データセットでは必要なカラムのみ取得する。
- 推奨: バッチ処理にはバルク操作を使う。
- 禁止: ループ内での Lazy Loading を避ける。
- 禁止: ループ内で個別クエリを発行しない(バッチクエリを使う)。

### エラーハンドリング

- 推奨: 具体的な SQLAlchemy 例外クラスを捕捉する。
- 推奨: すべてのデータベースエラーを文脈情報付きでログ出力する。
- 推奨: `None` を返すか、ドメイン固有のカスタム例外を送出する。
- 禁止: エラーを黙って握りつぶさない。
- 禁止: 内部のデータベース例外をそのまま UI へ露出させない。

### 型安全性

- 推奨: すべてのメソッドに型ヒントを付ける。
- 推奨: 検索条件には `dataclass` を使う。
- 推奨: 戻り値には `NamedTuple` または `dataclass` を使う。
- 禁止: `Any` 型を安易に使わない。
- 禁止: 構造化データに生の `dict` を使わない。

### テスト

- 推奨: テストにはインメモリ SQLite を使う。
- 推奨: セッションファクトリはフィクスチャで提供する。
- 推奨: エラー系・例外パスも必ずテストする。
- 禁止: 本番データベースに対してテストを実行しない。
- 禁止: テスト間でセッションを共有しない。
