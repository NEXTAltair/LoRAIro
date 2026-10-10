"""Persistent annotation phase and target context, refreshed only by a UI timer."""

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from lorairo.services.annotation_progress import AnnotationPhase, AnnotationProgress


class AnnotationProgressWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress: AnnotationProgress | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.phase_label = QLabel(self)
        self.context_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        for widget in (self.phase_label, self.context_label, self.detail_label, self.progress_bar):
            layout.addWidget(widget)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    @Slot(object)
    def set_progress(self, progress: AnnotationProgress) -> None:
        self._progress = progress
        self.phase_label.setText(progress.phase.value)
        self.detail_label.setText(progress.detail_text())
        self.detail_label.setVisible(bool(progress.detail_text()))
        self._update_elapsed()
        if progress.phase.is_terminal:
            self._elapsed_timer.stop()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100 if progress.phase is AnnotationPhase.COMPLETED else 0)
        else:
            self.progress_bar.setRange(0, 0)
            self._elapsed_timer.start()

    def stop(self) -> None:
        """Stop animations immediately before removing a view."""
        self._elapsed_timer.stop()
        self.progress_bar.setRange(0, 100)

    @Slot()
    def _update_elapsed(self) -> None:
        if self._progress is not None:
            self.context_label.setText(self._progress.context_text())
