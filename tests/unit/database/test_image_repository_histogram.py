"""Phase 4: get_created_at_histogram() メソッドのテスト。"""

import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.image import ImageRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def _create_image(session_factory, created_at: datetime.datetime | None = None):
    """テスト用 Image を1件作成して id を返す。"""
    from lorairo.database.schema import Image

    with session_factory() as session:
        img = Image(
            uuid=str(uuid.uuid4()),
            phash=f"aa{uuid.uuid4().hex[:10]}",
            original_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            stored_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            width=100,
            height=100,
            format="PNG",
            extension="png",
            created_at=created_at,
        )
        session.add(img)
        session.commit()
        return img.id


# ---------------------------------------------------------------------------
# get_created_at_histogram
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCreatedAtHistogram:
    """get_created_at_histogram() メソッドのテスト。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    def test_empty_db_returns_empty_list(self, repository):
        """画像が存在しない場合は空リストを返す。"""
        result = repository.get_created_at_histogram(bins=10)
        assert result == []

    def test_single_date_returns_single_bin(self, repository, session_factory):
        """全画像が同一 created_at の場合、1 ビンのみ返す。"""
        ts = datetime.datetime(2025, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        _create_image(session_factory, created_at=ts)
        _create_image(session_factory, created_at=ts)

        result = repository.get_created_at_histogram(bins=5)
        assert len(result) == 1
        # count は画像数と一致
        assert result[0][2] == 2

    def test_returns_bins_count_tuples(self, repository, session_factory):
        """bins 数と一致するタプルリストを返す。"""
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        for i in range(20):
            _create_image(
                session_factory,
                created_at=base + datetime.timedelta(days=i),
            )

        bins = 5
        result = repository.get_created_at_histogram(bins=bins)
        assert len(result) == bins

    def test_total_count_equals_image_count(self, repository, session_factory):
        """全ビンのカウント合計が総画像数と一致する。"""
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        image_count = 15
        for i in range(image_count):
            _create_image(
                session_factory,
                created_at=base + datetime.timedelta(hours=i),
            )

        result = repository.get_created_at_histogram(bins=10)
        total = sum(entry[2] for entry in result)
        assert total == image_count

    def test_bins_are_chronologically_ordered(self, repository, session_factory):
        """ビンの開始時刻が昇順に並んでいる。"""
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        for i in range(10):
            _create_image(
                session_factory,
                created_at=base + datetime.timedelta(days=i),
            )

        result = repository.get_created_at_histogram(bins=5)
        starts = [entry[0] for entry in result]
        assert starts == sorted(starts)

    def test_each_entry_is_tuple_of_datetime_datetime_int(self, repository, session_factory):
        """各エントリが (datetime, datetime, int) の形式である。"""
        base = datetime.datetime(2025, 3, 1, tzinfo=datetime.timezone.utc)
        for i in range(6):
            _create_image(
                session_factory,
                created_at=base + datetime.timedelta(days=i),
            )

        result = repository.get_created_at_histogram(bins=3)
        for entry in result:
            assert len(entry) == 3
            bin_start, bin_end, count = entry
            assert isinstance(bin_start, datetime.datetime)
            assert isinstance(bin_end, datetime.datetime)
            assert isinstance(count, int)
            assert bin_start <= bin_end
