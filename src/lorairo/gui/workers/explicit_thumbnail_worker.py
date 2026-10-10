"""Load explicit-path thumbnails without search/page state or GUI-thread image I/O."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QImage

from ...utils.log import logger

type ThumbnailKey = tuple[Path, int, int]


@dataclass(frozen=True)
class ExplicitThumbnailRequest:
    """A versioned image request; removal/readdition must receive a new token."""

    image_id: int
    key: ThumbnailKey
    token: int


@dataclass(frozen=True)
class ExplicitThumbnailResult:
    request: ExplicitThumbnailRequest
    image: QImage


class ExplicitThumbnailSignals(QObject):
    loaded = Signal(list)  # list[ExplicitThumbnailResult], at most 16 per delivery
    finished = Signal(str)  # task_id


class ExplicitThumbnailWorker(QRunnable):
    """QImage decoding/scaling only; QPixmap conversion belongs to the receiver."""

    BATCH_SIZE = 16

    def __init__(
        self,
        task_id: str,
        requests: list[ExplicitThumbnailRequest],
        shutdown: Event,
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self.requests = requests
        self.shutdown = shutdown
        self.canceled = Event()
        self.signals = ExplicitThumbnailSignals()

    @staticmethod
    def load_image(key: ThumbnailKey) -> QImage:
        """Match ThumbnailWorker's QImage scaling, without database access."""
        path, width, height = key
        image = QImage(str(path))
        if image.isNull():
            return image
        return image.scaled(
            QSize(width, height),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def run(self) -> None:
        batch: list[ExplicitThumbnailResult] = []
        try:
            for request in self.requests:
                if self.canceled.is_set() or self.shutdown.is_set():
                    break
                try:
                    image = self.load_image(request.key)
                except Exception:
                    logger.exception("Explicit thumbnail load failed: {}", request.key[0])
                    image = QImage()
                batch.append(ExplicitThumbnailResult(request, image))
                if len(batch) == self.BATCH_SIZE:
                    self.signals.loaded.emit(batch)
                    batch = []
            if batch and not self.canceled.is_set() and not self.shutdown.is_set():
                self.signals.loaded.emit(batch)
        finally:
            self.signals.finished.emit(self.task_id)
