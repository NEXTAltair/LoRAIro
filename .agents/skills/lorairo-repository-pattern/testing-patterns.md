# リポジトリのテストパターン

LoRAIro のリポジトリ層に向けたテスト戦略と `pytest` パターンをまとめる。

## テスト戦略

### リポジトリ層のテストピラミッド

```
        /----------\
       / Integration \      (10%) - 一連のワークフロー検証
      /----------------\
     /   Repository     \   (90%) - リポジトリのユニットテスト
    /--------------------\
```

**方針:** リポジトリ層のテストは、インメモリ SQLite を使ったユニットテストを中心に構成する。

### カバレッジ目標

- **リポジトリメソッド**: カバレッジ 100%(すべての CRUD 操作)
- **エラーパス**: すべての例外ハンドリングを検証する
- **エッジケース**: 空の結果、`None`/NULL 値、制約違反を検証する
- **トランザクション挙動**: コミット、ロールバック、セーブポイントを検証する

## テスト環境のセットアップ

### `conftest.py`

```python
# tests/conftest.py または tests/database/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from src.lorairo.database.schema import Base
from src.lorairo.database.db_repository import ImageRepository

@pytest.fixture(scope="function")
def test_engine():
    """
    Create in-memory SQLite engine for each test.

    Scope: function - Fresh database for each test
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def session_factory(test_engine):
    """
    Create session factory for test database.

    Returns:
        scoped_session - Session factory for repository
    """
    factory = scoped_session(sessionmaker(bind=test_engine))
    yield factory
    factory.remove()

@pytest.fixture(scope="function")
def image_repository(session_factory):
    """
    Create ImageRepository instance for testing.

    Returns:
        ImageRepository - Repository instance with test session
    """
    return ImageRepository(session_factory)

@pytest.fixture
def sample_image():
    """
    Create sample Image instance (not saved to database).

    Returns:
        Image - Sample image with test data
    """
    from src.lorairo.database.schema import Image
    return Image(
        path="/test/sample.jpg",
        phash="abc123def456",
        width=1024,
        height=768,
        score=0.85
    )

@pytest.fixture
def sample_images():
    """
    Create multiple sample Image instances.

    Returns:
        list[Image] - List of sample images
    """
    from src.lorairo.database.schema import Image
    return [
        Image(path=f"/test/image_{i}.jpg", phash=f"hash{i}", score=0.5 + i * 0.1)
        for i in range(5)
    ]
```

## 基本的な CRUD テスト

### 追加操作のテスト

```python
import pytest
from src.lorairo.database.schema import Image

@pytest.mark.unit
def test_add_image(image_repository, sample_image):
    """Test adding single image"""
    # Act
    result = image_repository.add(sample_image)

    # Assert
    assert result.id is not None, "ID should be generated"
    assert result.path == sample_image.path
    assert result.phash == sample_image.phash
    assert result.score == sample_image.score

@pytest.mark.unit
def test_add_image_returns_detached_object(image_repository, sample_image):
    """Test that returned image is usable outside session"""
    result = image_repository.add(sample_image)

    # セッション外でもデタッチ済みオブジェクトの各属性を参照できることを確認する
    assert result.id is not None
    assert result.path == "/test/sample.jpg"  # Lazy Load エラーが起きない

@pytest.mark.unit
def test_batch_add_images(image_repository, sample_images):
    """Test adding multiple images in single transaction"""
    # Act
    results = image_repository.batch_add(sample_images)

    # Assert
    assert len(results) == len(sample_images)
    assert all(img.id is not None for img in results)
    assert all(img.path for img in results)
```

### 取得操作のテスト

```python
@pytest.mark.unit
def test_get_by_id_existing(image_repository, sample_image):
    """Test retrieving existing image by ID"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    result = image_repository.get_by_id(added.id)

    # Assert
    assert result is not None
    assert result.id == added.id
    assert result.path == sample_image.path

@pytest.mark.unit
def test_get_by_id_nonexistent(image_repository):
    """Test retrieving non-existent image returns None"""
    # Act
    result = image_repository.get_by_id(99999)

    # Assert
    assert result is None

@pytest.mark.unit
def test_get_all_empty(image_repository):
    """Test get_all with empty database"""
    # Act
    results = image_repository.get_all()

    # Assert
    assert results == []

@pytest.mark.unit
def test_get_all_with_limit(image_repository, sample_images):
    """Test get_all respects limit parameter"""
    # Arrange
    image_repository.batch_add(sample_images)

    # Act
    results = image_repository.get_all(limit=3)

    # Assert
    assert len(results) == 3

@pytest.mark.unit
def test_exists(image_repository, sample_image):
    """Test checking image existence"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    exists = image_repository.exists(added.id)
    not_exists = image_repository.exists(99999)

    # Assert
    assert exists is True
    assert not_exists is False
```

### 更新操作のテスト

```python
@pytest.mark.unit
def test_update_image(image_repository, sample_image):
    """Test updating image fields"""
    # Arrange
    added = image_repository.add(sample_image)
    original_score = added.score

    # Act
    added.score = 0.95
    updated = image_repository.update(added)

    # Assert
    assert updated.score == 0.95
    assert updated.score != original_score

    # DB 上の永続化結果も検証する
    retrieved = image_repository.get_by_id(added.id)
    assert retrieved.score == 0.95

@pytest.mark.unit
def test_update_nonexistent_creates_new(image_repository, sample_image):
    """Test update with non-existent ID creates new entry (merge behavior)"""
    # Arrange
    sample_image.id = 99999  # 存在しない ID

    # Act
    result = image_repository.update(sample_image)

    # Assert
    assert result.id is not None
    # merge の挙動により新規作成されるか失敗するかは実装に依存する
```

### 削除操作のテスト

```python
@pytest.mark.unit
def test_delete_existing(image_repository, sample_image):
    """Test deleting existing image"""
    # Arrange
    added = image_repository.add(sample_image)

    # Act
    deleted = image_repository.delete(added.id)

    # Assert
    assert deleted is True
    assert image_repository.get_by_id(added.id) is None

@pytest.mark.unit
def test_delete_nonexistent(image_repository):
    """Test deleting non-existent image returns False"""
    # Act
    deleted = image_repository.delete(99999)

    # Assert
    assert deleted is False
```

## 検索・クエリのテスト

### 型安全な検索のテスト

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SearchCriteria:
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None

@pytest.mark.unit
def test_search_by_min_score(image_repository, sample_images):
    """Test searching with minimum score filter"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.7)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert all(img.score >= 0.7 for img in results)

@pytest.mark.unit
def test_search_by_score_range(image_repository, sample_images):
    """Test searching with score range"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.6, max_score=0.8)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert all(0.6 <= img.score <= 0.8 for img in results)

@pytest.mark.unit
def test_search_no_matches(image_repository, sample_images):
    """Test search with no matching results"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.99)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert results == []

@pytest.mark.unit
def test_count_matching(image_repository, sample_images):
    """Test counting matches without fetching data"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=0.7)

    # Act
    count = image_repository.count_matching(criteria)
    results = image_repository.search(criteria)

    # Assert
    assert count == len(results)
```

## エラーハンドリングのテスト

### 制約違反のテスト

```python
from sqlalchemy.exc import IntegrityError

@pytest.mark.unit
def test_add_duplicate_phash_fails(image_repository, sample_image):
    """Test adding image with duplicate phash raises IntegrityError"""
    # Arrange
    image_repository.add(sample_image)
    duplicate = Image(path="/different/path.jpg", phash=sample_image.phash)

    # Act & Assert
    with pytest.raises(IntegrityError):
        image_repository.add(duplicate)

@pytest.mark.unit
def test_add_safe_handles_duplicate(image_repository, sample_image):
    """Test safe add returns None on constraint violation"""
    # Arrange
    image_repository.add(sample_image)
    duplicate = Image(path="/different/path.jpg", phash=sample_image.phash)

    # Act
    result = image_repository.add_safe(duplicate)

    # Assert
    assert result is None
```

### トランザクションロールバックのテスト

```python
@pytest.mark.unit
def test_transaction_rollback_on_error(image_repository, sample_images):
    """Test transaction rolls back entirely on error"""
    # Arrange
    # 正常な画像データを 1 件用意する
    valid_image = sample_images[0]

    # 制約違反を起こす不正な画像データを用意する
    invalid_image = Image(path=None, phash="hash123")  # NULL の path で NOT NULL 制約に違反

    # Act & Assert
    with pytest.raises(Exception):  # 何らかの DB エラーが発生する
        with image_repository.session_factory() as session:
            session.add(valid_image)
            session.add(invalid_image)
            session.commit()

    # ロールバックにより正常な画像も保存されていないことを検証する
    all_images = image_repository.get_all()
    assert len(all_images) == 0, "Transaction should have rolled back"
```

## トランザクションのテスト

### アトミック操作のテスト

```python
@pytest.mark.unit
def test_batch_add_is_atomic(image_repository, sample_images, monkeypatch):
    """Test batch add commits all or nothing"""
    # Arrange
    def mock_commit_fail(self):
        raise Exception("Commit failed")

    # Act & Assert
    with pytest.raises(Exception):
        with monkeypatch.context() as m:
            # コミット失敗を再現する
            m.setattr("sqlalchemy.orm.Session.commit", mock_commit_fail)
            image_repository.batch_add(sample_images)

    # 1 件もコミットされていないことを検証する
    assert len(image_repository.get_all()) == 0

@pytest.mark.unit
def test_complex_operation_transactional(image_repository):
    """Test complex multi-step operation is transactional"""
    # 画像のプロジェクト間移動など、複数ステップの操作が
    # アトミック(全成功または全ロールバック)であることを検証する
    pass  # 対象の複合操作に合わせて実装する
```

## パフォーマンステスト

### バルク操作のテスト

```python
@pytest.mark.unit
def test_bulk_update_performance(image_repository, sample_images):
    """Test bulk update is efficient"""
    # Arrange
    added = image_repository.batch_add(sample_images)
    score_updates = {img.id: 0.9 for img in added}

    # Act
    updated_count = image_repository.bulk_update_scores(score_updates)

    # Assert
    assert updated_count == len(score_updates)

    # 更新結果を検証する
    for img in image_repository.get_all():
        assert img.score == 0.9

@pytest.mark.unit
def test_bulk_delete(image_repository, sample_images):
    """Test bulk delete by IDs"""
    # Arrange
    added = image_repository.batch_add(sample_images)
    ids_to_delete = [img.id for img in added[:3]]

    # Act
    deleted_count = image_repository.bulk_delete_by_ids(ids_to_delete)

    # Assert
    assert deleted_count == 3
    assert len(image_repository.get_all()) == 2
```

### N+1 クエリ防止のテスト

```python
@pytest.mark.unit
def test_eager_loading_prevents_n_plus_1(image_repository, session_factory):
    """Test eager loading loads relations in single query"""
    from sqlalchemy import event
    from src.lorairo.database.schema import Image

    # Arrange - アノテーション付き画像を登録する
    with session_factory() as session:
        for i in range(5):
            image = Image(path=f"/image_{i}.jpg", phash=f"hash{i}")
            session.add(image)
            # スキーマに応じて関連アノテーションも追加する
        session.commit()

    # 発行されたクエリ数を記録する
    query_count = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        query_count.append(statement)

    event.listen(test_engine, "before_cursor_execute", before_cursor_execute)

    # Act - Eager Loading 付きで画像を取得する
    images = image_repository.get_all_with_annotations()

    # Assert - N+1 ではなく 1 クエリ(selectinload でも最大 2 クエリ)に収まること
    assert len(query_count) <= 2, f"Too many queries: {len(query_count)}"
```

## テストフィクスチャとヘルパー

### テストデータ用ファクトリーパターン

```python
# tests/factories.py
from dataclasses import dataclass
from typing import Optional
from src.lorairo.database.schema import Image

@dataclass
class ImageFactory:
    """Factory for creating test Image instances"""

    @staticmethod
    def create(
        path: Optional[str] = None,
        phash: Optional[str] = None,
        score: Optional[float] = None,
        **kwargs
    ) -> Image:
        """Create Image with default test values"""
        return Image(
            path=path or "/test/default.jpg",
            phash=phash or "default_hash",
            score=score if score is not None else 0.75,
            **kwargs
        )

    @staticmethod
    def create_batch(count: int, **kwargs) -> list[Image]:
        """Create multiple images with unique paths"""
        return [
            ImageFactory.create(
                path=f"/test/image_{i}.jpg",
                phash=f"hash_{i}",
                **kwargs
            )
            for i in range(count)
        ]
```

### テストでのファクトリー利用

```python
from tests.factories import ImageFactory

@pytest.mark.unit
def test_add_with_factory(image_repository):
    """Test using factory for test data"""
    # Arrange
    image = ImageFactory.create(score=0.9)

    # Act
    result = image_repository.add(image)

    # Assert
    assert result.score == 0.9

@pytest.mark.unit
def test_batch_with_factory(image_repository):
    """Test batch operations with factory"""
    # Arrange
    images = ImageFactory.create_batch(10, score=0.8)

    # Act
    results = image_repository.batch_add(images)

    # Assert
    assert len(results) == 10
    assert all(img.score == 0.8 for img in results)
```

## パラメーター化テスト

### 複数シナリオの検証

```python
@pytest.mark.parametrize("score,expected_count", [
    (0.0, 5),   # 全件
    (0.6, 4),   # score >= 0.6 の画像
    (0.8, 2),   # score >= 0.8 の画像
    (0.99, 0),  # 該当なし
])
@pytest.mark.unit
def test_search_by_score_parametrized(image_repository, sample_images, score, expected_count):
    """Test search with various score thresholds"""
    # Arrange
    image_repository.batch_add(sample_images)
    criteria = SearchCriteria(min_score=score)

    # Act
    results = image_repository.search(criteria)

    # Assert
    assert len(results) == expected_count

@pytest.mark.parametrize("field,value,should_raise", [
    ("path", None, True),           # NULL の path は例外を送出
    ("phash", None, True),          # NULL の phash は例外を送出
    ("score", -1.0, False),         # 負のスコアは制約なしのため許容
    ("width", -100, False),         # 負の幅は制約なしのため許容
])
@pytest.mark.unit
def test_field_constraints(image_repository, field, value, should_raise):
    """Test database field constraints"""
    # Arrange
    image_data = {
        "path": "/test/image.jpg",
        "phash": "hash123",
        "score": 0.75,
        field: value  # 指定フィールドのみ上書き
    }
    image = Image(**image_data)

    # Act & Assert
    if should_raise:
        with pytest.raises(Exception):  # IntegrityError など
            image_repository.add(image)
    else:
        result = image_repository.add(image)
        assert result is not None
```

## 統合テスト

### 一連のワークフロー検証

```python
@pytest.mark.integration
def test_full_image_lifecycle(image_repository):
    """Test complete CRUD lifecycle"""
    # 作成
    image = Image(path="/test/lifecycle.jpg", phash="lifecycle_hash", score=0.5)
    created = image_repository.add(image)
    assert created.id is not None

    # 取得
    retrieved = image_repository.get_by_id(created.id)
    assert retrieved.path == image.path

    # 更新
    retrieved.score = 0.9
    updated = image_repository.update(retrieved)
    assert updated.score == 0.9

    # 更新が永続化されたことを検証する
    verify = image_repository.get_by_id(created.id)
    assert verify.score == 0.9

    # 削除
    deleted = image_repository.delete(created.id)
    assert deleted is True

    # 削除されたことを検証する
    assert image_repository.get_by_id(created.id) is None
```

## カバレッジのベストプラクティス

### カバレッジ計測

```bash
# カバレッジ付きでテストを実行する
uv run pytest tests/database/test_repository.py --cov=src/lorairo/database --cov-report=html

# カバレッジレポートを開く
open htmlcov/index.html
```

### カバレッジ目標

- **リポジトリメソッド**: 100%(すべてのメソッドをテストする)
- **エラーパス**: すべての例外ハンドラーをテストする
- **分岐カバレッジ**: すべての `if`/`else` 分岐をテストする
- **全体**: リポジトリ層全体で 75% 以上を維持する

### カバレッジ除外の指定

```python
# 到達しない防御的コードには除外マーカーを付ける
def defensive_check(self, value):
    if not isinstance(value, int):  # pragma: no cover
        raise TypeError("Defensive check, should never reach")
```

## テストの実行コマンド

```bash
# リポジトリテスト全体を実行
uv run pytest tests/database/test_repository.py -v

# 単一テストを実行
uv run pytest tests/database/test_repository.py::test_add_image -v

# カバレッジ付きで実行
uv run pytest tests/database/ --cov=src/lorairo/database --cov-report=term-missing

# 並列実行
uv run pytest tests/database/ -n auto
```

## よくある落とし穴

### テスト間でセッションを共有する(非推奨)

```python
# 非推奨: 複数テストでセッションが共有される
@pytest.fixture(scope="module")  # スコープが不適切
def session_factory(test_engine):
    return scoped_session(sessionmaker(bind=test_engine))
```

### テストごとに新しいセッションを作る(推奨)

```python
# 推奨: テスト関数ごとに独立したセッションを使う
@pytest.fixture(scope="function")
def session_factory(test_engine):
    factory = scoped_session(sessionmaker(bind=test_engine))
    yield factory
    factory.remove()  # 後片付け
```

### 本番データベースに対してテストを実行する(非推奨)

```python
# 非推奨: 本番 DB の URL を使う
@pytest.fixture
def test_engine():
    return create_engine("postgresql://prod_db")  # 厳禁
```

### インメモリテストデータベースを使う(推奨)

```python
# 推奨: インメモリ SQLite を使う
@pytest.fixture
def test_engine():
    return create_engine("sqlite:///:memory:")
```

### エラーパスをテストしない(非推奨)

```python
# 非推奨: 正常系しかテストしていない
def test_add_image(repository, image):
    result = repository.add(image)
    assert result.id is not None
    # 追加失敗時の検証が欠けている
```

### 正常系と異常系の両方をテストする(推奨)

```python
# 推奨: 成功ケースと失敗ケースの両方を検証する
def test_add_image_success(repository, image):
    result = repository.add(image)
    assert result.id is not None

def test_add_image_duplicate_fails(repository, image):
    repository.add(image)
    with pytest.raises(IntegrityError):
        repository.add(image)  # 重複 phash
```
