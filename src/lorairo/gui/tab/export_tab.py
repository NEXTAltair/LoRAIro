"""エクスポートタブの専用ウィジェット (Epic #867 / #872 / #896)。

データセットエクスポート UI (`DatasetExportWidget`) をホストする薄いタブ
ウィジェット。対象 = ステージング集合 (ADR 0055/0019)。エクスポート対象は
``StagingStateManager`` (ADR 0074) を SSoT とし、本ウィジェットが
``staged_images_changed`` を直接購読してライブ更新する自治構成 (#896)。
エクスポート入口バー (btnExportData 等) は Search 側導線のため本ウィジェットには
含めず、MainWindow が glue として保持する (#869 で SearchTab へ)。
"""

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...services.service_container import ServiceContainer
from ..state.staging_state import StagingStateManager
from ..widgets.dataset_export_widget import DatasetExportWidget


class ExportTabWidget(QWidget):
    """エクスポートタブのルートウィジェット (Wireframes v11 Frame 7 · Export)。

    `DatasetExportWidget` を内包し、エクスポート対象 ID をステージング集合へ
    自治同期する。初期対象は注入された ``StagingStateManager`` から読み、以降は
    ``staged_images_changed`` 購読でライブ更新する (#896)。
    """

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        staging_state_manager: StagingStateManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """エクスポートタブを初期化する。

        Args:
            service_container: DatasetExportWidget への依存注入コンテナ。
            staging_state_manager: エクスポート対象の SSoT (ADR 0074)。初期対象を
                読み出し、``staged_images_changed`` を購読してライブ更新する。
                None の場合は空集合で構築し購読も行わない。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._staging_state_manager = staging_state_manager
        initial_image_ids = (
            staging_state_manager.get_image_ids() if staging_state_manager is not None else []
        )
        self._export_widget = DatasetExportWidget(
            service_container=service_container,
            initial_image_ids=initial_image_ids,
            parent=self,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._export_widget)

        # ステージング集合 (SSoT) をライブ購読する。clear() も changed([]) を発行する
        # ため、staged_images_changed の購読だけで set / clear 双方を同期できる。
        if staging_state_manager is not None:
            staging_state_manager.staged_images_changed.connect(self.set_image_ids)

    @property
    def export_widget(self) -> DatasetExportWidget:
        """内包する `DatasetExportWidget` を返す (タブ内配線・テスト用)。"""
        return self._export_widget

    @Slot(list)
    def set_image_ids(self, image_ids: list[int]) -> None:
        """エクスポート対象の画像 ID を更新する (内包 widget へ委譲)。"""
        self._export_widget.set_image_ids(image_ids)

    def refresh(self) -> None:
        """ステージング集合を再読込してエクスポート対象へ反映する (ADR 0055 安全網)。

        タブ表示時にシグナル取りこぼしがあっても、SSoT である
        ``StagingStateManager`` を読み直して対象件数の整合を取る (#896)。
        """
        if self._staging_state_manager is not None:
            self._export_widget.set_image_ids(self._staging_state_manager.get_image_ids())

    def current_export_ids(self) -> list[int]:
        """現在のエクスポート対象 ID を返す (テスト・検証用)。"""
        return self._export_widget.image_ids
