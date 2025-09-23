"""Date formatting utilities for display purposes."""

from datetime import datetime
from typing import Any

from ..utils.log import logger


def format_datetime_for_display(dt: Any) -> str:
    """
    Convert datetime object to display-friendly string format.

    Args:
        dt: Input value (expected to be datetime object from database)

    Returns:
        str: Formatted date string in "YYYY-MM-DD HH:MM:SS" format or "Unknown"
    """
    try:
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        # Log unexpected types for debugging
        if dt is not None:
            logger.warning(f"Unexpected date type for display formatting: {type(dt)}, value: {dt}")

        return "Unknown"

    except Exception as e:
        logger.error(f"Date formatting failed for value: {dt}, type: {type(dt)}, error: {e}")
        return "Unknown"
