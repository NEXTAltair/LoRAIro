"""Changed-since datetime filter widget for export/search style panels."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from PySide6.QtCore import QDateTime, QTime, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QDateTimeEdit, QHBoxLayout, QWidget


class ChangedSinceFilterWidget(QWidget):
    """Reusable checkbox + datetime picker for "changed since" filters."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._check_box = QCheckBox("変更日時")
        self._check_box.setObjectName("changedSinceCheckBox")
        self._check_box.setToolTip("指定日時以降にタグ変更があった画像だけを対象にします")
        layout.addWidget(self._check_box)

        self._date_time_edit = QDateTimeEdit()
        self._date_time_edit.setObjectName("changedSinceDateTimeEdit")
        self._date_time_edit.setCalendarPopup(True)
        self._date_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._date_time_edit.setEnabled(False)
        default_cutoff = QDateTime.currentDateTime()
        default_cutoff.setTime(QTime(default_cutoff.time().hour(), default_cutoff.time().minute()))
        self._date_time_edit.setDateTime(default_cutoff)
        layout.addWidget(self._date_time_edit)

        layout.addStretch(1)

    def _connect_signals(self) -> None:
        self._check_box.toggled.connect(self._on_toggled)
        self._date_time_edit.dateTimeChanged.connect(lambda _value: self.changed.emit())

    def is_enabled(self) -> bool:
        """Return whether the changed-since filter is active."""
        return self._check_box.isChecked()

    def since(self) -> datetime:
        """Return the selected cutoff datetime."""
        return cast(datetime, self._date_time_edit.dateTime().toPython())

    def set_filter(self, enabled: bool, since: datetime | None = None) -> None:
        """Set filter state for tests and future preset restore paths."""
        self._check_box.setChecked(enabled)
        if since is not None:
            self._date_time_edit.setDateTime(QDateTime(since))

    @Slot(bool)
    def _on_toggled(self, checked: bool) -> None:
        self._date_time_edit.setEnabled(checked)
        self.changed.emit()
