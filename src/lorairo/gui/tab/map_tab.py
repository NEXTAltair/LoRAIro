"""マップタブの専用ウィジェット (Epic #867)。

`TagCloudWidget` をホストし、`db_manager` をコンストラクタ注入で受ける薄いタブ
ウィジェット。マップタブ固有の配置はここに閉じ、MainWindow からは切り離す。
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from ..widgets.tag_cloud_widget import TagCloudWidget


class MapTabWidget(QWidget):
    """マップタブのルートウィジェット。

    キーワード連動の共起タグ探索を提供する `TagCloudWidget` を内包する。
    `db_manager` は構築時に注入し、内部の `TagCloudWidget` へ渡す。
    """

    def __init__(self, db_manager: ImageDatabaseManager, parent: QWidget | None = None) -> None:
        """マップタブを初期化する。

        Args:
            db_manager: タグ共起集計に使うデータベースマネージャ。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._tag_cloud = TagCloudWidget(db_manager=db_manager, parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tag_cloud)

    @property
    def tag_cloud(self) -> TagCloudWidget:
        """内包する `TagCloudWidget` を返す (タブ内配線・テスト用)。"""
        return self._tag_cloud
