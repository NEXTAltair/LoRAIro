"""Tests for date_formatter module."""

from datetime import UTC, datetime

import pytest

from lorairo.services.date_formatter import format_datetime_for_display


@pytest.mark.unit
class TestDateFormatter:
    """Test date formatting functionality."""

    def test_format_datetime_object(self) -> None:
        """Test formatting of datetime object."""
        dt = datetime(2025, 9, 22, 15, 30, 45)
        result = format_datetime_for_display(dt)
        assert result == "2025-09-22 15:30:45"

    def test_format_none_value(self) -> None:
        """Test formatting of None value."""
        result = format_datetime_for_display(None)
        assert result == "Unknown"

    def test_format_string_value(self) -> None:
        """Test formatting of string value (unexpected type)."""
        result = format_datetime_for_display("2025-09-22")
        assert result == "Unknown"

    def test_format_invalid_value(self) -> None:
        """Test formatting of invalid value."""
        result = format_datetime_for_display(123)
        assert result == "Unknown"

    def test_format_datetime_with_timezone(self) -> None:
        """Test formatting of timezone-aware datetime."""

        dt = datetime(2025, 9, 22, 15, 30, 45, tzinfo=UTC)
        result = format_datetime_for_display(dt)
        assert result == "2025-09-22 15:30:45"

    def test_format_datetime_strftime_raises_exception_returns_unknown(self) -> None:
        """Test that exception during strftime is caught and 'Unknown' is returned.

        Covers lines 29-31: except Exception branch.
        datetime のサブクラスで strftime を override して例外を発生させる。
        isinstance(dt, datetime) が True のまま strftime で例外を起こすことで
        except Exception ブランチを通す。
        """

        class BrokenDatetime(datetime):
            def strftime(self, fmt: str) -> str:
                raise OSError("strftime failed")

        broken_dt = BrokenDatetime(2025, 9, 22, 15, 30, 45)
        result = format_datetime_for_display(broken_dt)
        assert result == "Unknown"
