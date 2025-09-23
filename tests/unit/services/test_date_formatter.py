"""Tests for date_formatter module."""

from datetime import UTC, datetime

import pytest

from lorairo.services.date_formatter import format_datetime_for_display


class TestDateFormatter:
    """Test date formatting functionality."""

    def test_format_datetime_object(self):
        """Test formatting of datetime object."""
        dt = datetime(2025, 9, 22, 15, 30, 45)
        result = format_datetime_for_display(dt)
        assert result == "2025-09-22 15:30:45"

    def test_format_none_value(self):
        """Test formatting of None value."""
        result = format_datetime_for_display(None)
        assert result == "Unknown"

    def test_format_string_value(self):
        """Test formatting of string value (unexpected type)."""
        result = format_datetime_for_display("2025-09-22")
        assert result == "Unknown"

    def test_format_invalid_value(self):
        """Test formatting of invalid value."""
        result = format_datetime_for_display(123)
        assert result == "Unknown"

    def test_format_datetime_with_timezone(self):
        """Test formatting of timezone-aware datetime."""
        from datetime import timezone

        dt = datetime(2025, 9, 22, 15, 30, 45, tzinfo=UTC)
        result = format_datetime_for_display(dt)
        assert result == "2025-09-22 15:30:45"
