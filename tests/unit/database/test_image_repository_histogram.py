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
        ts = datetime.datetime(2025, 6, 1, 12, 0, 0, tzinfo=datetime.UTC)
        _create_image(session_factory, created_at=ts)
        _create_image(session_factory, created_at=ts)

        result = repository.get_created_at_histogram(bins=5)
        assert len(result) == 1
        # count は画像数と一致
        assert result[0][2] == 2

    def test_returns_bins_count_tuples(self, repository, session_factory):
        """bins 数と一致するタプルリストを返す。"""
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
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
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
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
        base = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
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
        base = datetime.datetime(2025, 3, 1, tzinfo=datetime.UTC)
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


# ---------------------------------------------------------------------------
# ヒストグラムのビンと日付フィルタの整合 (#1440)
# ---------------------------------------------------------------------------

_BASE = datetime.datetime(2026, 1, 1, 0, 0, 0)


def _filter_ids(repository, session_factory, start: datetime.datetime, end: datetime.datetime) -> set[int]:
    """GUI と同じく UTC aware -> isoformat -> 日付フィルタの経路で実 DB を絞り込む。"""
    from sqlalchemy import select

    from lorairo.database.schema import Image

    def _to_iso(value: datetime.datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=datetime.UTC)
        return aware.isoformat()

    start_dt = repository._parse_datetime_str(_to_iso(start))
    end_dt = repository._parse_datetime_str(_to_iso(end))
    query = repository._apply_date_filter(select(Image.id), start_dt, end_dt)
    with session_factory() as session:
        return set(session.execute(query).scalars().all())


def _to_server_default_text(session_factory) -> None:
    """created_at を server_default (CURRENT_TIMESTAMP) と同じ秒精度テキストへ書き換える。"""
    from sqlalchemy import text

    with session_factory() as session:
        session.execute(text("UPDATE images SET created_at = strftime('%Y-%m-%d %H:%M:%S', created_at)"))
        session.commit()


def _assert_bins_match_filter(repository, session_factory, bins: list, all_ids: set[int]) -> list[set[int]]:
    """各ビンのフィルタ結果が count と一致し、互いに素で全画像を覆うことを検証する。"""
    selected = [_filter_ids(repository, session_factory, start, end) for start, end, _ in bins]
    for (start, end, count), ids in zip(bins, selected, strict=True):
        assert start <= end
        assert len(ids) == count, f"bin {start}..{end}: count={count}, filter={len(ids)}"
    union: set[int] = set()
    for ids in selected:
        assert not (union & ids), "ビン同士でフィルタ結果が重複している"
        union |= ids
    assert union == all_ids
    return selected


@pytest.mark.unit
class TestHistogramBinsMatchDateFilter:
    """ヒストグラムのバーを選んだ検索結果が、そのバーの count と一致する (#1440)。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    @pytest.mark.parametrize("server_default_text", [False, True])
    def test_21_images_per_second_first_and_last_bins(
        self, repository, session_factory, server_default_text: bool
    ) -> None:
        """0〜20 秒の 21 枚: 先頭バーは 1 枚、最終バーは上限 (20 秒) の画像を含む。"""
        ids = [
            _create_image(session_factory, created_at=_BASE + datetime.timedelta(seconds=i))
            for i in range(21)
        ]
        if server_default_text:
            _to_server_default_text(session_factory)

        bins = repository.get_created_at_histogram(bins=20)
        assert len(bins) == 20
        assert bins[0][2] == 1
        selected = _assert_bins_match_filter(repository, session_factory, bins, set(ids))

        assert selected[0] == {ids[0]}  # 内部境界 (1 秒) の画像は先頭バーに含まれない
        assert selected[1] == {ids[1]}
        assert selected[-1] == {ids[19], ids[20]}  # 最終バーは上限ちょうどを含む

    @pytest.mark.parametrize("server_default_text", [False, True])
    def test_single_timestamp_sole_bin(
        self, repository, session_factory, server_default_text: bool
    ) -> None:
        """全画像が同一時刻なら 1 ビンで、そのバーで全画像が返る。"""
        ids = {_create_image(session_factory, created_at=_BASE) for _ in range(3)}
        if server_default_text:
            _to_server_default_text(session_factory)

        bins = repository.get_created_at_histogram(bins=20)

        assert len(bins) == 1
        _assert_bins_match_filter(repository, session_factory, bins, ids)

    def test_sub_millisecond_values_near_boundaries(self, repository, session_factory) -> None:
        """マイクロ秒付きの値が境界の前後 (±0.4ms) にあっても count とフィルタが一致する。"""
        offsets_us = [0, 999_600, 1_000_400, 1_999_999, 7_500_000, 20_000_000]
        ids = {
            _create_image(session_factory, created_at=_BASE + datetime.timedelta(microseconds=us))
            for us in offsets_us
        }

        bins = repository.get_created_at_histogram(bins=20)

        _assert_bins_match_filter(repository, session_factory, bins, ids)

    def test_fractional_bin_width(self, repository, session_factory) -> None:
        """ビン幅が小数秒 (19 秒 / 20 ビン) でも count とフィルタが一致する。"""
        ids = {
            _create_image(session_factory, created_at=_BASE + datetime.timedelta(seconds=i))
            for i in range(20)
        }
        _to_server_default_text(session_factory)

        bins = repository.get_created_at_histogram(bins=20)

        _assert_bins_match_filter(repository, session_factory, bins, ids)

    def test_span_shorter_than_bins_in_ms_reduces_bins(self, repository, session_factory) -> None:
        """期間 (5ms) がビン数より短い場合はビン数を減らし、空区間 (start > end) を作らない。"""
        ids = {
            _create_image(session_factory, created_at=_BASE + datetime.timedelta(milliseconds=ms))
            for ms in (0, 2, 5)
        }

        bins = repository.get_created_at_histogram(bins=20)

        assert len(bins) == 5
        _assert_bins_match_filter(repository, session_factory, bins, ids)

    def test_non_utc_aware_bounds_are_converted(self, repository, session_factory) -> None:
        """JST の aware 境界は UTC に換算して比較される (タイムゾーン)。"""
        jst = datetime.timezone(datetime.timedelta(hours=9))
        target = _create_image(session_factory, created_at=_BASE + datetime.timedelta(hours=1))
        _create_image(session_factory, created_at=_BASE + datetime.timedelta(hours=3))
        _to_server_default_text(session_factory)

        start = (_BASE + datetime.timedelta(hours=1)).replace(tzinfo=datetime.UTC).astimezone(jst)
        end = (_BASE + datetime.timedelta(hours=2)).replace(tzinfo=datetime.UTC).astimezone(jst)

        assert _filter_ids(repository, session_factory, start, end) == {target}

    def test_inverted_range_returns_no_images(self, repository, session_factory) -> None:
        """開始 > 終了の空範囲 (スライダーとの積集合が空) は 0 件になる。"""
        _create_image(session_factory, created_at=_BASE)
        _create_image(session_factory, created_at=_BASE + datetime.timedelta(days=1))

        start = _BASE + datetime.timedelta(hours=12)
        end = _BASE + datetime.timedelta(hours=6)

        assert _filter_ids(repository, session_factory, start, end) == set()
