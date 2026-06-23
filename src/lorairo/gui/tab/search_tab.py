"""検索タブ (ワークベンチ) の専用ウィジェット (Epic #867 / #869)。

MainWindow の検索タブ (tabWorkspace) のオーケストレーション —
データセット選択 / DB 検索 / サムネ表示 / プレビュー・詳細編集 / 3 ペイン splitter /
ステージング・エクスポート導線 — を ``SearchTabWidget`` へ集約する。MainWindow には
worker dispatch・PipelineControlService 所有・staging fan-out・タブ間遷移・settings 等の
横断 glue だけを残す。

このファイルは #869 の **凍結契約スタブ** として先行 commit される (placeholder-swap、
#868 で確立した手法)。本実装 (Track A) は ``SearchTab.ui`` を新設して
``class SearchTabWidget(QWidget, Ui_SearchTab)`` へ切り替え、``__init__`` 本体と各メソッドを
埋めるが、**下記の公開シグネチャ (コンストラクタ DI / Signal / スロット / プロパティ) は
変更しないこと**。MainWindow rewire (Track B) はこの契約に対してコードを書く。

== 凍結契約 ==
- コンストラクタ: ``SearchTabWidget(*, service_container, db_manager,
  dataset_state_manager, staging_state_manager, worker_service, parent=None)``
- Signal (タブ → MainWindow glue):
    - ``stage_to_annotation_requested = Signal(list)`` — 選択画像をアノテへステージ
    - ``quick_tag_requested = Signal(list)`` — クイックタグ付与
    - ``export_requested = Signal()`` — エクスポートタブ遷移
    - ``dataset_selection_requested = Signal()`` — データセット選択+登録 dispatch
    - ``settings_requested = Signal()`` — 設定ダイアログ
    - ``search_error_occurred = Signal(str)`` — pipeline エラー (error_notification 更新用)
- スロット (MainWindow → タブ):
    - ``refresh() -> None`` — タブ表示時の再計算
    - ``set_db_info(text: str, tooltip: str = "") -> None`` — DB 状態バー更新
    - ``set_dataset_path(path: str) -> None`` — データセットパス表示更新
    - ``set_export_target_count(count: int) -> None`` — エクスポート対象件数ラベル
    - ``load_images_from_db() -> None`` — 起動時/再読込時の検索開始
    - ``toggle_filter_panel() -> None`` / ``toggle_preview_panel() -> None`` —
      menubar action からのパネル開閉 (splitter サイズ退避/復元はタブが所有)
- プロパティ (タブ内配線・テスト・PipelineControlService 注入用):
    - ``filter_search_panel`` / ``thumbnail_selector`` / ``image_preview_widget``
      / ``selected_image_details_widget`` / ``main_splitter``
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...services.service_container import ServiceContainer
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..state.staging_state import StagingStateManager
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class SearchTabWidget(QWidget):
    """検索タブのルートウィジェット (Wireframes v11 Frame 1 · Search / Workbench)。

    PENDING: Issue #869 本実装 (Track A) — 本クラスは凍結契約スタブ。本実装では
    ``SearchTab.ui`` を ``setupUi`` で展開し ``QWidget, Ui_SearchTab`` を多重継承する。
    """

    stage_to_annotation_requested = Signal(list)
    quick_tag_requested = Signal(list)
    export_requested = Signal()
    dataset_selection_requested = Signal()
    settings_requested = Signal()
    search_error_occurred = Signal(str)

    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        dataset_state_manager: DatasetStateManager | None,
        staging_state_manager: StagingStateManager | None,
        worker_service: WorkerService | None,
        parent: QWidget | None = None,
    ) -> None:
        """検索タブを初期化する。

        Args:
            service_container: SearchFilterService 生成 / favorite filters / merged reader。
            db_manager: rating/score 書込・詳細取得。
            dataset_state_manager: 選択 SSoT (thumbnail/preview/details 接続)。
            staging_state_manager: エクスポート対象・ステージング件数。
            worker_service: 検索 → サムネ pipeline driver。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._service_container = service_container
        self._db_manager = db_manager
        self._dataset_state_manager = dataset_state_manager
        self._staging_state_manager = staging_state_manager
        self._worker_service = worker_service

        # PENDING: Issue #869 — SearchTab.ui の setupUi + 各 widget の setter DI 配線 +
        # 検索/サムネ pipeline 配線 + splitter (#865 orientation 再適用) をここで構築する。
        # 下記は契約 (プロパティ非 Optional) を満たすための暫定スケルトン。
        self._filter_search_panel = FilterSearchPanel(self)
        self._thumbnail_selector = ThumbnailSelectorWidget(self)
        self._image_preview_widget = ImagePreviewWidget(self)
        self._selected_image_details_widget = SelectedImageDetailsWidget(self)
        self._main_splitter = QSplitter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    # -- プロパティ (タブ内配線・テスト・pipeline 注入用) ----------------------

    @property
    def filter_search_panel(self) -> FilterSearchPanel:
        """フィルタ検索パネルを返す。"""
        return self._filter_search_panel

    @property
    def thumbnail_selector(self) -> ThumbnailSelectorWidget:
        """サムネイルセレクタを返す (PipelineControlService 注入用)。"""
        return self._thumbnail_selector

    @property
    def image_preview_widget(self) -> ImagePreviewWidget:
        """画像プレビューを返す。"""
        return self._image_preview_widget

    @property
    def selected_image_details_widget(self) -> SelectedImageDetailsWidget:
        """選択画像の詳細 (rating/score 編集) を返す。"""
        return self._selected_image_details_widget

    @property
    def main_splitter(self) -> QSplitter:
        """3 ペイン横 splitter を返す (QSettings 復元・パネルトグル用)。"""
        return self._main_splitter

    # -- スロット (MainWindow → タブ) ----------------------------------------

    @Slot()
    def refresh(self) -> None:
        """タブ表示時の再計算 (results/errors と同型)。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot(str, str)
    def set_db_info(self, text: str, tooltip: str = "") -> None:
        """DB 状態バーのテキストを更新する。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot(str)
    def set_dataset_path(self, path: str) -> None:
        """データセットパス表示を更新する。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot(int)
    def set_export_target_count(self, count: int) -> None:
        """エクスポート対象件数ラベルを更新する (staging fan-out から駆動)。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot()
    def load_images_from_db(self) -> None:
        """起動時/再読込時に DB 検索を開始する。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot()
    def toggle_filter_panel(self) -> None:
        """フィルタパネルの表示/非表示を切り替える (splitter サイズ退避/復元)。"""
        # PENDING: Issue #869 本実装 (Track A)

    @Slot()
    def toggle_preview_panel(self) -> None:
        """プレビュー/詳細パネルの表示/非表示を切り替える。"""
        # PENDING: Issue #869 本実装 (Track A)
