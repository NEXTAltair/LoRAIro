"""登録日フィルタの境界ポリシー (registration_date_range) のテスト (#1457 / #1440)。"""

import datetime as dt
import itertools

import pytest

from lorairo.domain.registration_date_range import (
    PRESET_CUSTOM,
    PRESET_LAST_7_DAYS,
    PRESET_LAST_30_DAYS,
    PRESET_TODAY,
    PRESET_YESTERDAY,
    LocalDayRange,
    build_histogram_day_bins,
    coerce_saved_day,
    match_preset,
    preset_day_range,
    to_utc_bounds,
    utc_bounds_to_day_range,
    utc_to_local_date,
)

JST = dt.timezone(dt.timedelta(hours=9))
UTC = dt.UTC
HST = dt.timezone(dt.timedelta(hours=-9))


@pytest.mark.unit
class TestToUtcBounds:
    """ローカル暦日の範囲 → [開始日 00:00, 終了日の翌日 00:00) の naive UTC。"""

    @pytest.mark.parametrize(
        ("tz", "start", "end", "expected_start", "expected_end"),
        [
            # UTC: そのまま
            (
                UTC,
                dt.date(2026, 11, 7),
                dt.date(2026, 11, 7),
                dt.datetime(2026, 11, 7),
                dt.datetime(2026, 11, 8),
            ),
            # JST (+9): 前日 15:00 UTC 起点
            (
                JST,
                dt.date(2026, 11, 7),
                dt.date(2026, 11, 7),
                dt.datetime(2026, 11, 6, 15),
                dt.datetime(2026, 11, 7, 15),
            ),
            # UTC-9: 当日 09:00 UTC 起点
            (
                HST,
                dt.date(2026, 11, 7),
                dt.date(2026, 11, 7),
                dt.datetime(2026, 11, 7, 9),
                dt.datetime(2026, 11, 8, 9),
            ),
            # 月・年をまたぐ範囲
            (
                JST,
                dt.date(2025, 12, 31),
                dt.date(2026, 1, 1),
                dt.datetime(2025, 12, 30, 15),
                dt.datetime(2026, 1, 1, 15),
            ),
        ],
    )
    def test_bounds_table(self, tz, start, end, expected_start, expected_end):
        start_utc, end_utc = to_utc_bounds(LocalDayRange(start, end), tz)
        assert (start_utc, end_utc) == (expected_start, expected_end)
        # DB (SQLite) の保存形式に合わせて naive UTC で返す
        assert start_utc.tzinfo is None
        assert end_utc.tzinfo is None

    def test_system_local_timezone_is_used_by_default(self):
        start_utc, end_utc = to_utc_bounds(LocalDayRange(dt.date(2026, 11, 7), dt.date(2026, 11, 7)))
        expected = dt.datetime(2026, 11, 7).astimezone().astimezone(UTC).replace(tzinfo=None)
        assert start_utc == expected
        assert end_utc - start_utc == dt.timedelta(days=1)

    def test_reversed_range_is_rejected(self):
        with pytest.raises(ValueError):
            LocalDayRange(dt.date(2026, 11, 8), dt.date(2026, 11, 7))


@pytest.mark.unit
class TestUtcToLocalDate:
    """DB の naive UTC → ローカル暦日。aware はその時差を尊重する。"""

    @pytest.mark.parametrize(
        ("value", "tz", "expected"),
        [
            # naive は UTC とみなす: JST では 15:00 UTC から翌日
            (dt.datetime(2026, 11, 6, 14, 59, 59, 999999), JST, dt.date(2026, 11, 6)),
            (dt.datetime(2026, 11, 6, 15, 0, 0), JST, dt.date(2026, 11, 7)),
            # 小数秒付き
            (dt.datetime(2026, 11, 6, 15, 0, 0, 500000), JST, dt.date(2026, 11, 7)),
            # UTC-9
            (dt.datetime(2026, 11, 7, 8, 59, 59), HST, dt.date(2026, 11, 6)),
            (dt.datetime(2026, 11, 7, 9, 0, 0), HST, dt.date(2026, 11, 7)),
            # aware
            (dt.datetime(2026, 11, 7, 0, 0, tzinfo=JST), UTC, dt.date(2026, 11, 6)),
        ],
    )
    def test_table(self, value, tz, expected):
        assert utc_to_local_date(value, tz) == expected

    def test_round_trip_with_bounds(self):
        day_range = LocalDayRange(dt.date(2026, 11, 1), dt.date(2026, 11, 7))
        bounds = to_utc_bounds(day_range, JST)
        assert utc_bounds_to_day_range(*bounds, tz=JST) == day_range


@pytest.mark.unit
class TestPresets:
    """クイック選択はローカル暦日 (今日を含む直近 N 日) で決める。"""

    TODAY = dt.date(2026, 11, 8)

    @pytest.mark.parametrize(
        ("preset", "expected"),
        [
            (PRESET_TODAY, LocalDayRange(dt.date(2026, 11, 8), dt.date(2026, 11, 8))),
            (PRESET_YESTERDAY, LocalDayRange(dt.date(2026, 11, 7), dt.date(2026, 11, 7))),
            (PRESET_LAST_7_DAYS, LocalDayRange(dt.date(2026, 11, 2), dt.date(2026, 11, 8))),
            (PRESET_LAST_30_DAYS, LocalDayRange(dt.date(2026, 10, 10), dt.date(2026, 11, 8))),
        ],
    )
    def test_preset_day_range(self, preset, expected):
        assert preset_day_range(preset, self.TODAY) == expected
        assert match_preset(expected, self.TODAY) == preset

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError):
            preset_day_range(PRESET_CUSTOM, self.TODAY)

    def test_non_preset_range_matches_custom(self):
        day_range = LocalDayRange(dt.date(2026, 11, 1), dt.date(2026, 11, 3))
        assert match_preset(day_range, self.TODAY) == PRESET_CUSTOM


@pytest.mark.unit
class TestHistogramDayBins:
    """ヒストグラムのビンは暦日単位で連続し、重複も隙間もない。"""

    def test_single_day(self):
        day = dt.date(2026, 11, 7)
        assert build_histogram_day_bins(day, day, 20) == [LocalDayRange(day, day)]

    def test_fewer_days_than_bins_gives_one_day_bins(self):
        first = dt.date(2026, 11, 1)
        bins = build_histogram_day_bins(first, dt.date(2026, 11, 5), 20)
        assert [b.start for b in bins] == [first + dt.timedelta(days=i) for i in range(5)]
        assert all(b.start == b.end for b in bins)

    def test_bins_are_contiguous_and_cover_range(self):
        first, last = dt.date(2026, 1, 1), dt.date(2026, 3, 15)
        bins = build_histogram_day_bins(first, last, 20)
        assert len(bins) <= 20
        assert bins[0].start == first
        assert bins[-1].end == last
        for prev, nxt in itertools.pairwise(bins):
            assert nxt.start == prev.end + dt.timedelta(days=1)


@pytest.mark.unit
class TestCoerceSavedDay:
    """保存フィルタの値 (ISO 日付 / 旧形式の epoch 秒) を暦日へ戻す。"""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-11-07", dt.date(2026, 11, 7)),
            # 旧形式: epoch 秒 (2026-11-06T15:00:00Z = JST 11/07 00:00)
            (int(dt.datetime(2026, 11, 6, 15, tzinfo=UTC).timestamp()), dt.date(2026, 11, 7)),
            (float(dt.datetime(2026, 11, 6, 15, tzinfo=UTC).timestamp()), dt.date(2026, 11, 7)),
            ("not-a-date", None),
            (None, None),
            (True, None),
        ],
    )
    def test_table(self, value, expected):
        assert coerce_saved_day(value, JST) == expected
