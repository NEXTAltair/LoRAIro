"""登録日 (Image.created_at) フィルタの境界ポリシー (ADR 0100, #1457 / #1440)。

登録日フィルタの「丸め・包含規則・ローカル時刻 ⇔ UTC 変換」はこのモジュールだけで決める。
検索条件・ヒストグラム・表示はすべてここを経由する (Qt 非依存の純粋関数)。

規則:
    - 粒度はローカル時刻の暦日。範囲は開始日と終了日の両端を含む (:class:`LocalDayRange`)。
    - DB 比較の境界は「開始日 00:00:00 以上、終了日の翌日 00:00:00 未満」(半開区間)。
    - DB (SQLite) の datetime は naive な UTC なので、境界も naive な UTC で返す。
    - ローカル時刻 → UTC の変換は :func:`to_utc_bounds` の中で 1 回だけ行う。
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

PRESET_ALL = "all"
PRESET_TODAY = "today"
PRESET_YESTERDAY = "yesterday"
PRESET_LAST_7_DAYS = "last_7_days"
PRESET_LAST_30_DAYS = "last_30_days"
PRESET_CUSTOM = "custom"

# プリセット → (今日から何日前が開始日か, 今日から何日前が終了日か)
_PRESET_OFFSETS: dict[str, tuple[int, int]] = {
    PRESET_TODAY: (0, 0),
    PRESET_YESTERDAY: (1, 1),
    PRESET_LAST_7_DAYS: (6, 0),
    PRESET_LAST_30_DAYS: (29, 0),
}


@dataclass(frozen=True)
class LocalDayRange:
    """ローカル時刻の暦日範囲 (開始日・終了日とも含む)。

    Attributes:
        start: 開始日 (含む)。
        end: 終了日 (含む)。

    Raises:
        ValueError: 開始日が終了日より後の場合。
    """

    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"開始日が終了日より後です: {self.start} > {self.end}")


def _local_midnight(day: dt.date, tz: dt.tzinfo | None) -> dt.datetime:
    """暦日のローカル 00:00 を aware datetime で返す (tz=None はシステムのローカル時刻)。"""
    if tz is None:
        # naive を astimezone するとシステムのローカル時刻として解釈される (DST も考慮)
        return dt.datetime.combine(day, dt.time.min).astimezone()
    return dt.datetime.combine(day, dt.time.min, tzinfo=tz)


def to_utc_bounds(day_range: LocalDayRange, tz: dt.tzinfo | None = None) -> tuple[dt.datetime, dt.datetime]:
    """暦日範囲を DB 比較用の半開区間 [開始, 終了) に変換する。

    Args:
        day_range: ローカル時刻の暦日範囲。
        tz: ローカル時刻のタイムゾーン。None はシステムのローカル時刻。

    Returns:
        (開始日 00:00 以上, 終了日の翌日 00:00 未満) の naive UTC datetime。
    """
    start = _local_midnight(day_range.start, tz)
    end = _local_midnight(day_range.end + dt.timedelta(days=1), tz)
    return (
        start.astimezone(dt.UTC).replace(tzinfo=None),
        end.astimezone(dt.UTC).replace(tzinfo=None),
    )


def utc_to_local_date(value: dt.datetime, tz: dt.tzinfo | None = None) -> dt.date:
    """DB の日時をローカル時刻の暦日に変換する。

    Args:
        value: 日時。naive は UTC とみなす (SQLite の保存形式)。
        tz: ローカル時刻のタイムゾーン。None はシステムのローカル時刻。

    Returns:
        ローカル時刻での暦日。
    """
    aware = value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
    return aware.astimezone(tz).date()


def utc_bounds_to_day_range(
    start_utc: dt.datetime, end_utc_exclusive: dt.datetime, tz: dt.tzinfo | None = None
) -> LocalDayRange:
    """:func:`to_utc_bounds` の逆変換 (表示用)。

    Args:
        start_utc: 開始 (含む)。
        end_utc_exclusive: 終了 (含まない)。
        tz: ローカル時刻のタイムゾーン。None はシステムのローカル時刻。

    Returns:
        暦日範囲。
    """
    end_day = utc_to_local_date(end_utc_exclusive, tz) - dt.timedelta(days=1)
    return LocalDayRange(utc_to_local_date(start_utc, tz), end_day)


def local_today(tz: dt.tzinfo | None = None) -> dt.date:
    """ローカル時刻の今日を返す。"""
    return dt.datetime.now(tz).date() if tz is not None else dt.date.today()


def preset_day_range(preset: str, today: dt.date) -> LocalDayRange:
    """クイック選択の暦日範囲を返す (「過去 N 日」は今日を含む直近 N 暦日)。

    Args:
        preset: ``PRESET_TODAY`` などのプリセット値。
        today: ローカル時刻の今日。

    Returns:
        暦日範囲。

    Raises:
        ValueError: 日付範囲を持たないプリセット (すべて / カスタム) や未知の値の場合。
    """
    offsets = _PRESET_OFFSETS.get(preset)
    if offsets is None:
        raise ValueError(f"日付範囲を持たないプリセットです: {preset}")
    start_offset, end_offset = offsets
    return LocalDayRange(today - dt.timedelta(days=start_offset), today - dt.timedelta(days=end_offset))


def match_preset(day_range: LocalDayRange, today: dt.date) -> str:
    """暦日範囲に一致するプリセットを返す。一致しなければ ``PRESET_CUSTOM``。"""
    for preset in _PRESET_OFFSETS:
        if preset_day_range(preset, today) == day_range:
            return preset
    return PRESET_CUSTOM


def build_histogram_day_bins(first_day: dt.date, last_day: dt.date, bins: int) -> list[LocalDayRange]:
    """ヒストグラム用に、暦日単位で連続するビンを作る。

    各ビンの幅は同じ日数 (最終ビンだけ短い場合がある) で、重複も隙間もない。

    Args:
        first_day: 最初の暦日。
        last_day: 最後の暦日。
        bins: 最大ビン数 (1 以上)。

    Returns:
        暦日範囲のリスト (昇順)。
    """
    total_days = (last_day - first_day).days + 1
    width = max(1, math.ceil(total_days / max(1, bins)))
    result: list[LocalDayRange] = []
    start = first_day
    while start <= last_day:
        end = min(start + dt.timedelta(days=width - 1), last_day)
        result.append(LocalDayRange(start, end))
        start = end + dt.timedelta(days=1)
    return result


def coerce_saved_day(value: object, tz: dt.tzinfo | None = None) -> dt.date | None:
    """保存フィルタの日付値を暦日へ戻す。

    現行形式は ISO 日付文字列 (``YYYY-MM-DD``)。旧形式 (スライダーが秒単位だった頃の
    epoch 秒) も受け付け、ローカル時刻の暦日へ変換する。

    Args:
        value: 保存値。
        tz: ローカル時刻のタイムゾーン。None はシステムのローカル時刻。

    Returns:
        暦日。解釈できない場合は None。
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        try:
            return utc_to_local_date(dt.datetime.fromtimestamp(value, dt.UTC), tz)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None
