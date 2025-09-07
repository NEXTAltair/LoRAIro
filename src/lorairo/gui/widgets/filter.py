"""Stub implementation for TagFilterWidget.

This is a minimal stub to support UI generation. The actual tag filtering
functionality is handled by FilterSearchPanel in filter_search_panel.py.
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget


class TagFilterWidget(QWidget):
    """Stub implementation of TagFilterWidget for UI compatibility."""

    def __init__(self, parent=None):
        """Initialize empty widget stub."""
        super().__init__(parent)

        # Create minimal layout to prevent errors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
