"""エクスポートタブの専用ウィジェット (Epic #867 / #872)。

データセットエクスポート UI (`DatasetExportWidget`) をホストする薄いタブ
ウィジェット。対象 = ステージング集合 (ADR 0055/0019)。エクスポート対象の
画像 ID は MainWindow (Search 側導線 + staging fan-out) から ``set_image_ids``
で push される。エクスポート入口バー (btnExportData 等) は Search タブの導線の
ため本ウィジェットには含めず、MainWindow が glue として保持する (#869 で SearchTab へ)。
"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...services.service_container import ServiceContainer
from ..widgets.dataset_export_widget import DatasetExportWidget


class ExportTabWidget(QWidget):
    """エクスポートタブのルートウィジェット (Wireframes v11 Frame 7 · Export)。

    `DatasetExportWidget` を内包し、エクスポート対象 ID の差し替えを委譲する。
    """

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        initial_image_ids: list[int],
        parent: QWidget | None = None,
    ) -> None:
        """エクスポートタブを初期化する。

        Args:
            service_container: DatasetExportWidget への依存注入コンテナ。
            initial_image_ids: 初期エクスポート対象の画像 ID (ステージング集合)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._export_widget = DatasetExportWidget(
            service_container=service_container,
            initial_image_ids=initial_image_ids,
            parent=self,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._export_widget)

    @property
    def export_widget(self) -> DatasetExportWidget:
        """内包する `DatasetExportWidget` を返す (タブ内配線・テスト用)。"""
        return self._export_widget

    @Slot(list)
    def set_image_ids(self, image_ids: list[int]) -> None:
        """エクスポート対象の画像 ID を更新する (内包 widget へ委譲)。"""
        self._export_widget.set_image_ids(image_ids)
