"""登録日 (created_at) フィルタとヒストグラムの境界テスト (#1457 / #1440)。

一時ファイルの SQLite に、SQLite が実際に保存する naive な文字列形式
(秒精度・マイクロ秒付き・'T' 区切り・server_default) をそのまま書き込んで検証する。
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.image import ImageRepository
from lorairo.domain.registration_date_range import LocalDayRange, to_utc_bounds

JST = dt.timezone(dt.timedelta(hours=9))


@pytest.fixture
def session_factory(tmp_path):
    from lorairo.database.schema import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'created_at.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def repository(session_factory) -> ImageRepository:
    return ImageRepository(session_factory=session_factory)


def _add_image(repository: ImageRepository, session_factory, created_at_text: str | None) -> int:
    """画像を登録し、created_at を SQLite の生テキストで上書きする (None は server_default のまま)。"""
    name = uuid.uuid4().hex
    image_id, _ = repository.add_original_image(
        {
            "uuid": name,
            "phash": f"ph-{name}",
            "original_image_path": f"/tmp/{name}.png",
            "stored_image_path": f"/tmp/{name}.png",
            "width": 64,
            "height": 64,
            "format": "PNG",
            "extension": ".png",
            "filename": f"{name}.png",
            "has_alpha": False,
            "is_grayscale_like": False,
        }
    )
    if created_at_text is not None:
        with session_factory() as session:
            session.execute(
                text("UPDATE images SET created_at = :v, updated_at = '2000-01-01 00:00:00' WHERE id = :i"),
                {"v": created_at_text, "i": image_id},
            )
            session.commit()
    return image_id


def _search_ids(repository: ImageRepository, day_range: LocalDayRange, tz: dt.tzinfo) -> set[int]:
    start, end = to_utc_bounds(day_range, tz)
    criteria = ImageFilterCriteria(
        start_date=start.isoformat(),
        end_date_exclusive=end.isoformat(),
        include_nsfw=True,
    )
    images, _count = repository.get_images_by_filter(criteria)
    return {int(img["id"]) for img in images}


def _day(day: int) -> LocalDayRange:
    return LocalDayRange(dt.date(2026, 11, day), dt.date(2026, 11, day))


@pytest.mark.unit
class TestCreatedAtDayFilter:
    """検索は created_at を [開始日 00:00, 終了日の翌日 00:00) で絞り込む。"""

    @pytest.mark.parametrize(
        "stored",
        [
            "2026-11-06 15:00:00",  # 秒精度 (CURRENT_TIMESTAMP 形式) = JST 11/07 00:00 ちょうど
            "2026-11-06 15:00:00.000000",  # SQLAlchemy がマイクロ秒付きで保存した形式
            "2026-11-06T15:00:00",  # 'T' 区切り
            "2026-11-06 15:00:00.000",  # ミリ秒
        ],
    )
    def test_lower_boundary_is_included_regardless_of_text_precision(
        self, repository, session_factory, stored
    ):
        image_id = _add_image(repository, session_factory, stored)
        assert _search_ids(repository, _day(7), JST) == {image_id}
        # 前日には含まれない (上限は排他)
        assert _search_ids(repository, _day(6), JST) == set()

    def test_upper_boundary_is_exclusive_with_fractional_seconds(self, repository, session_factory):
        last_moment = _add_image(repository, session_factory, "2026-11-07 14:59:59.999")
        next_midnight = _add_image(repository, session_factory, "2026-11-07 15:00:00")
        assert _search_ids(repository, _day(7), JST) == {last_moment}
        assert _search_ids(repository, _day(8), JST) == {next_midnight}

    def test_filters_by_created_at_not_updated_at(self, repository, session_factory):
        image_id = _add_image(repository, session_factory, "2026-11-07 03:00:00")
        with session_factory() as session:
            session.execute(
                text("UPDATE images SET updated_at = '2026-11-20 03:00:00' WHERE id = :i"), {"i": image_id}
            )
            session.commit()
        assert _search_ids(repository, _day(7), dt.UTC) == {image_id}
        assert _search_ids(repository, _day(20), dt.UTC) == set()

    def test_server_default_timestamp_is_found_for_today(self, repository, session_factory):
        image_id = _add_image(repository, session_factory, None)
        with session_factory() as session:
            stored = session.execute(text("SELECT created_at FROM images WHERE id = :i"), {"i": image_id})
            stored_text = stored.scalar_one()
        # server_default は秒精度の naive UTC テキスト
        assert isinstance(stored_text, str)
        assert "." not in stored_text
        today_utc = dt.datetime.now(dt.UTC).date()
        assert _search_ids(repository, LocalDayRange(today_utc, today_utc), dt.UTC) == {image_id}

    def test_inclusive_end_date_keeps_existing_cli_semantics(self, repository, session_factory):
        image_id = _add_image(repository, session_factory, "2026-11-07 12:00:00")
        criteria = ImageFilterCriteria(
            start_date="2026-11-07T00:00:00", end_date="2026-11-07 12:00:00.000000", include_nsfw=True
        )
        images, _ = repository.get_images_by_filter(criteria)
        assert {int(img["id"]) for img in images} == {image_id}


@pytest.mark.unit
class TestCreatedAtHistogram:
    """ヒストグラムのビンは暦日単位で、各ビンの件数 = そのビンの範囲で検索した件数。"""

    def test_empty_db_returns_empty_list(self, repository):
        assert repository.get_created_at_histogram(bins=10, tz=JST) == []

    def test_bins_are_local_days_and_match_search(self, repository, session_factory):
        stored = [
            "2026-11-01 14:59:59",  # JST 11/01 23:59:59
            "2026-11-01 15:00:00",  # JST 11/02 00:00 (境界ちょうど)
            "2026-11-02 15:00:00.500000",  # JST 11/03 00:00:00.5
            "2026-11-04T03:00:00",
            "2026-11-04 03:00:00.000000",
        ]
        for value in stored:
            _add_image(repository, session_factory, value)

        bins = repository.get_created_at_histogram(bins=20, tz=JST)

        assert [(b[0], b[1]) for b in bins] == [
            (dt.date(2026, 11, d), dt.date(2026, 11, d)) for d in range(1, 5)
        ]
        assert [b[2] for b in bins] == [1, 1, 1, 2]
        for start, end, count in bins:
            assert len(_search_ids(repository, LocalDayRange(start, end), JST)) == count

    def test_single_timestamp_gives_single_bin(self, repository, session_factory):
        for _ in range(3):
            _add_image(repository, session_factory, None)
        bins = repository.get_created_at_histogram(bins=20, tz=dt.UTC)
        assert len(bins) == 1
        start, end, count = bins[0]
        assert count == 3
        assert len(_search_ids(repository, LocalDayRange(start, end), dt.UTC)) == 3

    def test_multi_day_bins_cover_all_images(self, repository, session_factory):
        base = dt.datetime(2026, 1, 1, 12)
        for i in range(60):
            _add_image(repository, session_factory, (base + dt.timedelta(days=i)).isoformat(sep=" "))
        bins = repository.get_created_at_histogram(bins=20, tz=JST)
        assert len(bins) <= 20
        assert sum(b[2] for b in bins) == 60
        for start, end, count in bins:
            assert len(_search_ids(repository, LocalDayRange(start, end), JST)) == count
