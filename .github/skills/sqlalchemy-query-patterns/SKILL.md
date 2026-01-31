---
name: sqlalchemy-query-patterns
version: "1.0.0"
description: SQLAlchemy の効率的なクエリパターン集。N+1回避、サブクエリ、バルク操作、インデックス活用、EXPLAIN解析など、LoRAIroのSQLiteデータベースに特化したクエリ最適化ガイド。Use when writing new queries, optimizing slow queries, or reviewing database access patterns.
metadata:
  short-description: SQLAlchemy効率クエリ（N+1回避、バルク操作、インデックス、EXPLAIN）。
allowed-tools:
  # Code exploration
  - mcp__serena__find_symbol
  - mcp__serena__get_symbols_overview
  - mcp__serena__find_referencing_symbols
  - mcp__serena__search_for_pattern
  # Memory
  - mcp__serena__read_memory
  # Fallback
  - Read
  - Write
  - Edit
  - Bash
dependencies:
  - lorairo-repository-pattern
  - lorairo-mem
---

# SQLAlchemy Efficient Query Patterns

LoRAIro の SQLite データベースに特化した、効率的な SQLAlchemy クエリパターン集。

## When to Use

Use this skill when:
- 新しいクエリメソッドを作成する
- 既存クエリのパフォーマンスを改善する
- N+1 クエリ問題を検出・修正する
- バルク操作を実装する
- クエリの実行計画を確認する

## LoRAIro データベース構成

```
Image ──┬── Tag (1:N)         - タグアノテーション
        ├── Caption (1:N)     - キャプション
        ├── Score (1:N)       - 品質スコア
        ├── Rating (1:N)      - レーティング
        ├── ProcessedImage (1:N) - 加工済み画像
        └── ErrorRecord (1:N) - エラー記録

Model ──── ModelType (M:N)    - AIモデルと機能タイプ
```

**ファイル構成:**
- Schema: `src/lorairo/database/schema.py`
- Repository: `src/lorairo/database/db_repository.py`
- Core: `src/lorairo/database/db_core.py`

## 1. N+1 クエリ回避

### 問題: N+1 クエリ

```python
# ❌ BAD: N+1 クエリ（画像ごとにタグを個別取得）
with session_factory() as session:
    images = session.execute(select(Image)).scalars().all()
    for img in images:
        tags = img.tags  # 画像ごとに追加クエリ発行！
```

### 解決策 1: selectinload（推奨・LoRAIro標準）

```python
from sqlalchemy.orm import selectinload

# ✅ GOOD: IN句で一括取得（2クエリ）
def get_images_with_tags(self) -> list[Image]:
    """画像一覧をタグ付きで取得（selectinload）。

    Returns:
        タグをeager loadした画像リスト。
    """
    with self.session_factory() as session:
        stmt = (
            select(Image)
            .options(selectinload(Image.tags))
            .order_by(Image.id)
        )
        return list(session.execute(stmt).scalars().all())
```

### 解決策 2: joinedload（1対1 / 少数リレーション向け）

```python
from sqlalchemy.orm import joinedload

# ✅ GOOD: JOINで1クエリ（子が少ない場合に有効）
def get_image_with_model(self, image_id: int) -> Image | None:
    """画像とモデル情報をJOINで一括取得。

    Args:
        image_id: 画像ID。

    Returns:
        モデル情報付きの画像。見つからない場合はNone。
    """
    with self.session_factory() as session:
        stmt = (
            select(Image)
            .options(joinedload(Image.scores).joinedload(Score.model))
            .where(Image.id == image_id)
        )
        return session.execute(stmt).unique().scalar_one_or_none()
```

### 解決策 3: 複数リレーション同時ロード

```python
# ✅ GOOD: タグ・キャプション・スコアを一括ロード
def get_image_full(self, image_id: int) -> Image | None:
    """画像の全関連データを一括取得。

    Args:
        image_id: 画像ID。

    Returns:
        全リレーションをeager loadした画像。
    """
    with self.session_factory() as session:
        stmt = (
            select(Image)
            .options(
                selectinload(Image.tags),
                selectinload(Image.captions),
                selectinload(Image.scores),
                selectinload(Image.ratings),
            )
            .where(Image.id == image_id)
        )
        return session.execute(stmt).unique().scalar_one_or_none()
```

### 使い分けガイド

| パターン | 用途 | SQL | LoRAIro での例 |
|---|---|---|---|
| `selectinload` | 1:N リレーション | `SELECT ... WHERE id IN (...)` | Image→Tags, Image→Captions |
| `joinedload` | 1:1 / N:1 リレーション | `LEFT JOIN` | Score→Model |
| `subqueryload` | 大量データの1:N | サブクエリ | 大規模バッチ処理 |
| `raiseload` | アクセス禁止（検出用） | N/A | デバッグ時のN+1検出 |

## 2. 効率的な SELECT パターン

### 必要なカラムだけ取得

```python
# ❌ BAD: 全カラム取得（不要なデータもメモリに載る）
images = session.execute(select(Image)).scalars().all()

# ✅ GOOD: 必要なカラムだけ取得
stmt = select(Image.id, Image.phash, Image.file_name).where(Image.is_active == True)
rows = session.execute(stmt).all()  # Row オブジェクト（軽量）
```

### EXISTS で存在チェック

```python
from sqlalchemy import exists

# ❌ BAD: 全件取得してlen()で判定
images = session.execute(select(Image).where(...)).scalars().all()
has_images = len(images) > 0

# ✅ GOOD: EXISTS サブクエリ（即座にbool返却）
def has_unprocessed_images(self) -> bool:
    """未処理画像の存在を高速チェック。

    Returns:
        未処理画像が1件以上あればTrue。
    """
    with self.session_factory() as session:
        stmt = select(
            exists().where(
                and_(
                    Image.is_active == True,
                    ~exists().where(ProcessedImage.image_id == Image.id),
                )
            )
        )
        return bool(session.execute(stmt).scalar())
```

### COUNT の効率化

```python
# ❌ BAD: Pythonでlen()
count = len(session.execute(select(Image)).scalars().all())

# ✅ GOOD: SQLレベルでCOUNT
def count_images_by_model(self, model_id: int) -> int:
    """特定モデルでアノテーション済みの画像数を取得。

    Args:
        model_id: モデルID。

    Returns:
        アノテーション済み画像数。
    """
    with self.session_factory() as session:
        stmt = (
            select(func.count(func.distinct(Tag.image_id)))
            .where(Tag.model_id == model_id)
        )
        return session.execute(stmt).scalar() or 0
```

## 3. バルク操作

### バルク INSERT

```python
# ❌ BAD: 1件ずつ追加（N回のINSERT）
for tag_data in tag_list:
    session.add(Tag(**tag_data))
    session.commit()

# ✅ GOOD: バルクINSERT（1回のINSERT）
def bulk_add_tags(self, tags: list[dict[str, Any]]) -> int:
    """タグを一括挿入。

    Args:
        tags: タグデータのリスト。各dictは Tag モデルのカラムに対応。

    Returns:
        挿入された件数。
    """
    with self.session_factory() as session:
        session.execute(Tag.__table__.insert(), tags)
        session.commit()
        return len(tags)
```

### バルク UPDATE

```python
# ❌ BAD: 1件ずつUPDATE
for image_id, score in updates.items():
    img = session.get(Image, image_id)
    img.aesthetic_score = score
    session.commit()

# ✅ GOOD: バルクUPDATE（WHERE IN句）
def bulk_update_scores(
    self,
    score_updates: list[dict[str, Any]],
) -> int:
    """スコアを一括更新。

    Args:
        score_updates: [{"id": 1, "aesthetic_score": 0.85}, ...] 形式のリスト。

    Returns:
        更新された件数。
    """
    with self.session_factory() as session:
        session.bulk_update_mappings(Image, score_updates)
        session.commit()
        return len(score_updates)
```

### バルク UPSERT（INSERT OR REPLACE）

```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

def upsert_tags(self, tags: list[dict[str, Any]]) -> int:
    """タグのUPSERT（存在すれば更新、なければ挿入）。

    SQLite の ON CONFLICT を使用。

    Args:
        tags: タグデータのリスト。

    Returns:
        処理された件数。
    """
    with self.session_factory() as session:
        stmt = sqlite_insert(Tag).values(tags)
        stmt = stmt.on_conflict_do_update(
            index_elements=["image_id", "tag_text"],
            set_={
                "confidence_score": stmt.excluded.confidence_score,
                "model_id": stmt.excluded.model_id,
            },
        )
        session.execute(stmt)
        session.commit()
        return len(tags)
```

## 4. サブクエリとCTE

### 相関サブクエリ

```python
# 最新スコアのみ取得（画像ごとに最新の1件）
def get_latest_scores(self) -> list[Row]:
    """各画像の最新スコアを取得。

    Returns:
        (image_id, score, model_id) のリスト。
    """
    with self.session_factory() as session:
        # サブクエリ: 画像ごとの最大スコアID
        latest_score = (
            select(func.max(Score.id).label("max_id"))
            .where(Score.image_id == Image.id)
            .correlate(Image)
            .scalar_subquery()
        )
        stmt = (
            select(Score.image_id, Score.score_value, Score.model_id)
            .where(Score.id == latest_score)
        )
        return list(session.execute(stmt).all())
```

### CTE（Common Table Expression）

```python
from sqlalchemy import cte

def get_images_with_tag_count(self, min_tags: int = 5) -> list[Row]:
    """タグ数が閾値以上の画像を取得。

    Args:
        min_tags: 最小タグ数。

    Returns:
        (image_id, file_name, tag_count) のリスト。
    """
    with self.session_factory() as session:
        # CTE: 画像ごとのタグ数を集計
        tag_counts = (
            select(
                Tag.image_id,
                func.count(Tag.id).label("tag_count"),
            )
            .group_by(Tag.image_id)
            .cte("tag_counts")
        )
        # メインクエリ: CTEとJOIN
        stmt = (
            select(Image.id, Image.file_name, tag_counts.c.tag_count)
            .join(tag_counts, Image.id == tag_counts.c.image_id)
            .where(tag_counts.c.tag_count >= min_tags)
            .order_by(tag_counts.c.tag_count.desc())
        )
        return list(session.execute(stmt).all())
```

## 5. 動的フィルタ構築

### 条件の動的組み立て

```python
from dataclasses import dataclass, field

@dataclass
class ImageSearchCriteria:
    """画像検索条件（型安全）。"""

    tags: list[str] = field(default_factory=list)
    min_score: float | None = None
    max_score: float | None = None
    model_name: str | None = None
    has_caption: bool | None = None
    limit: int = 100
    offset: int = 0

def search_images(self, criteria: ImageSearchCriteria) -> list[Image]:
    """条件に基づく画像検索（動的フィルタ）。

    Args:
        criteria: 検索条件。

    Returns:
        条件に合致する画像リスト。
    """
    with self.session_factory() as session:
        stmt = select(Image).where(Image.is_active == True)
        conditions: list = []

        if criteria.tags:
            # タグを持つ画像のサブクエリ
            tag_subq = (
                select(Tag.image_id)
                .where(Tag.tag_text.in_(criteria.tags))
                .group_by(Tag.image_id)
                .having(func.count(func.distinct(Tag.tag_text)) == len(criteria.tags))
            )
            conditions.append(Image.id.in_(tag_subq))

        if criteria.min_score is not None:
            score_subq = select(Score.image_id).where(
                Score.score_value >= criteria.min_score
            )
            conditions.append(Image.id.in_(score_subq))

        if criteria.max_score is not None:
            score_subq = select(Score.image_id).where(
                Score.score_value <= criteria.max_score
            )
            conditions.append(Image.id.in_(score_subq))

        if criteria.has_caption is True:
            caption_subq = select(Caption.image_id)
            conditions.append(Image.id.in_(caption_subq))
        elif criteria.has_caption is False:
            caption_subq = select(Caption.image_id)
            conditions.append(~Image.id.in_(caption_subq))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.limit(criteria.limit).offset(criteria.offset)
        return list(session.execute(stmt).scalars().all())
```

## 6. SQLite 固有の最適化

### インデックス設計

```python
from sqlalchemy import Index

# schema.py でのインデックス定義
class Image(Base):
    __tablename__ = "images"
    __table_args__ = (
        # 複合インデックス: phashで重複検索 + アクティブフィルタ
        Index("ix_image_phash_active", "phash", "is_active"),
        # カバリングインデックス: ファイル名検索時にidも返せる
        Index("ix_image_filename", "file_name"),
    )

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        # 複合インデックス: 画像ごとのタグ検索に最適
        Index("ix_tag_image_text", "image_id", "tag_text"),
        # タグテキスト検索用
        Index("ix_tag_text", "tag_text"),
    )
```

### SQLite WAL モード

```python
from sqlalchemy import event

# db_core.py で設定（読み取り並行性向上）
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.close()
```

### EXPLAIN で実行計画を確認

```python
# デバッグ用: クエリの実行計画を表示
def explain_query(self, stmt: Select) -> list[str]:
    """クエリの実行計画を取得（デバッグ用）。

    Args:
        stmt: 解析対象のSELECT文。

    Returns:
        EXPLAIN出力の各行。
    """
    with self.session_factory() as session:
        # SQLite の EXPLAIN QUERY PLAN
        compiled = stmt.compile(
            dialect=session.bind.dialect,
            compile_kwargs={"literal_binds": True},
        )
        result = session.execute(
            text(f"EXPLAIN QUERY PLAN {compiled}")
        )
        return [str(row) for row in result.all()]
```

## 7. ページネーション

### Keyset ページネーション（推奨）

```python
# ❌ BAD: OFFSET ページネーション（大量データで遅い）
stmt = select(Image).offset(10000).limit(100)

# ✅ GOOD: Keyset ページネーション（一定速度）
def get_images_page(
    self,
    last_id: int | None = None,
    page_size: int = 100,
) -> list[Image]:
    """Keysetベースのページネーション。

    Args:
        last_id: 前ページ最後のID。Noneなら先頭から。
        page_size: 1ページの件数。

    Returns:
        画像リスト（page_size件）。
    """
    with self.session_factory() as session:
        stmt = select(Image).order_by(Image.id)
        if last_id is not None:
            stmt = stmt.where(Image.id > last_id)
        stmt = stmt.limit(page_size)
        return list(session.execute(stmt).scalars().all())
```

## 8. アンチパターン集

| アンチパターン | 問題 | 正しいアプローチ |
|---|---|---|
| `session.query(X).all()` + Python フィルタ | 全件メモリロード | `WHERE` 句で DB 側フィルタ |
| `len(query.all())` | 全件取得してカウント | `func.count()` |
| ループ内 `session.get()` | N+1 クエリ | `selectinload` / `IN` 句 |
| `OFFSET` 大量ページング | 深いページほど遅い | Keyset ページネーション |
| `SELECT *` 常用 | 不要データ転送 | 必要カラム明示 |
| コミット多発 | トランザクションオーバーヘッド | バッチでまとめてコミット |
| 文字列連結 SQL | SQLインジェクション | ORM / パラメータバインド |

## Quick Reference

**Eager Loading:**
```python
selectinload(Image.tags)       # 1:N → IN句（推奨）
joinedload(Score.model)        # N:1 → JOIN
subqueryload(Image.tags)       # 1:N → サブクエリ
```

**バルク操作:**
```python
session.execute(Table.insert(), data_list)   # バルクINSERT
session.bulk_update_mappings(Model, updates)  # バルクUPDATE
sqlite_insert().on_conflict_do_update(...)    # UPSERT
```

**集計:**
```python
func.count(), func.sum(), func.avg()  # 集計関数
func.distinct()                        # 重複排除
exists().where(...)                    # 存在チェック
```

**フィルタ構築:**
```python
and_(*conditions)   # AND結合
or_(*conditions)    # OR結合
Image.id.in_(subq)  # サブクエリIN
~Image.id.in_(subq) # NOT IN
```
