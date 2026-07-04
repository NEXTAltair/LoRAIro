"""
Staging Widget - サムネイルステージングウィジェット

複数画像を個別実行フローや Provider Batch 実行フローで共通利用するための
サムネイル表示付きステージングコンポーネント。

主要機能:
- ステージングリストへの画像追加（最大500枚）
- 重複排除・追加順保持（OrderedDict）
- サムネイル表示（ThumbnailSelectorWidget）
- staged_images_changed / staging_cleared シグナル

アーキテクチャ:
- ADR 0036: Compound Widget 分割方針に従いステージング責務を分離
- ADR 0041: BatchTagAddWidget / ProviderBatchJobWidget の共通コンポーネント
"""

from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QFrame, QGraphicsView, QSplitter, QWidget

from ...gui.designer.StagingWidget_ui import Ui_StagingWidget
from ...utils.log import logger
from ..state.staging_state import StagingStateManager

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager
    from .thumbnail_selector_widget import ThumbnailSelectorWidget


class StagingWidget(QWidget):
    """
    サムネイルステージングウィジェット

    複数画像のステージング管理（追加・削除・クリア）とサムネイル表示を担当する
    共有コンポーネント。BatchTagAddWidget と ProviderBatchJobWidget の両方から
    利用される。

    データフロー:
    1. add_image_ids() / add_selected_images() -> ステージングリストに追加
    2. staged_images_changed シグナル発行（追加後）
    3. clear() -> ステージングリストを全削除
    4. staging_cleared / staged_images_changed([]) シグナル発行（クリア後）

    UI 構成:
    - groupBoxStagingList: ステージング一覧グループボックス
    - labelStagingCount: N / 500 枚 カウントラベル
    - listWidgetStaging (非表示, ThumbnailSelectorWidget に置換)
    - pushButtonClearStaging: クリアボタン

    ステージングリスト仕様:
    - 最大500枚まで
    - 重複なし（OrderedDict キー存在確認）
    - 追加順を保持（OrderedDict）
    """

    # シグナル (StagingStateManager のシグナルを再 emit し、既存の消費者契約を維持する)
    staged_images_changed = Signal(list)  # list[int] - ステージング画像IDリスト
    staging_cleared = Signal()  # ステージングリストクリア

    # 定数
    MAX_STAGING_IMAGES = StagingStateManager.MAX_STAGING_IMAGES

    def __init__(self, parent: QWidget | None = None):
        """
        StagingWidget 初期化

        UIコンポーネントの初期化、内部状態の設定、サムネイルウィジェット設定を実行。
        ステージング集合の SSoT は StagingStateManager に持たせ、本ウィジェットは
        その view として振る舞う (ADR 0074)。既定では自前の manager を生成し、
        set_staging_state_manager() で共有 manager に差し替える。

        Args:
            parent: 親ウィジェット
        """
        super().__init__(parent)
        logger.debug("StagingWidget.__init__() called")

        # ステージング集合の SSoT (既定は自前。共有時は set_staging_state_manager で差替)
        self._staging_state = StagingStateManager(self)

        # サムネイルキャッシュ（表示用の縮小Pixmap、view ローカル）
        self._thumbnail_cache: dict[int, QPixmap] = {}

        # DatasetStateManager への参照（パス解決フォールバック用、view ローカル保持）
        self._dataset_state_manager: DatasetStateManager | None = None

        # UI 設定
        self.ui = Ui_StagingWidget()
        setup_ui = cast(Callable[[QWidget], None], self.ui.setupUi)
        setup_ui(self)

        # splitter クランプの再入ガード (setSizes/setMaximumHeight が resizeEvent を誘発するため)
        self._fitting = False
        # 幅変化時のクランプ再計算はサムネ viewport 幅の反映後 (次イベントループ) に遅延する。
        # 連続 resize を合体させるため single-shot タイマで coalesce する (#1097 Codex P2-1)。
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(lambda: self._fit_enclosing_splitter_pane(redistribute=True))

        self._staging_thumbnail_widget: ThumbnailSelectorWidget | None = None
        self._setup_staging_thumbnail_widget()

        self._connect_state_signals()

        # 初期状態更新
        self._update_staging_count_label()

        logger.debug("StagingWidget initialized")

    def _connect_state_signals(self) -> None:
        """現在の StagingStateManager のシグナルを view へ接続する。"""
        self._staging_state.staged_images_changed.connect(self._on_state_changed)
        self._staging_state.staging_cleared.connect(self._on_state_cleared)

    @Slot(list)
    def _on_state_changed(self, image_ids: list[int]) -> None:
        """SSoT の変更を表示へ反映し、ウィジェットシグナルとして再 emit する。"""
        self._refresh_staging_list_ui()
        self.staged_images_changed.emit(image_ids)

    @Slot()
    def _on_state_cleared(self) -> None:
        """SSoT のクリアを表示へ反映し、ウィジェットシグナルとして再 emit する。"""
        self._thumbnail_cache.clear()
        self._refresh_staging_list_ui()
        self.staging_cleared.emit()

    def set_staging_state_manager(self, manager: StagingStateManager) -> None:
        """共有 StagingStateManager に差し替える (タブ間でステージングを共有する)。

        旧 manager のシグナル接続を解除し、新 manager へ接続し直して再描画する。
        従来の connect_shared_staging を置換する (ADR 0074)。

        Args:
            manager: 共有する StagingStateManager インスタンス。
        """
        if manager is self._staging_state:
            return
        try:
            self._staging_state.staged_images_changed.disconnect(self._on_state_changed)
            self._staging_state.staging_cleared.disconnect(self._on_state_cleared)
        except (RuntimeError, TypeError):
            pass
        self._staging_state = manager
        # view が把握している DatasetStateManager を新 manager にも引き継ぐ
        if self._dataset_state_manager is not None:
            manager.set_dataset_state_manager(self._dataset_state_manager)
        self._connect_state_signals()
        self._refresh_staging_list_ui()

    def get_staging_state_manager(self) -> StagingStateManager:
        """現在の SSoT である StagingStateManager を返す。"""
        return self._staging_state

    def set_dataset_state_manager(self, dataset_state_manager: "DatasetStateManager") -> None:
        """DatasetStateManager への参照を設定する (view と SSoT 双方へ)。

        Args:
            dataset_state_manager: DatasetStateManager インスタンス
        """
        self._dataset_state_manager = dataset_state_manager
        self._staging_state.set_dataset_state_manager(dataset_state_manager)
        logger.debug("DatasetStateManager reference set in StagingWidget")

    def _setup_staging_thumbnail_widget(self) -> None:
        """ステージング一覧を ThumbnailSelectorWidget で表示するセットアップ。"""
        from .thumbnail_selector_widget import ThumbnailSelectorWidget

        layout = self.ui.verticalLayoutStaging
        list_widget = self.ui.listWidgetStaging

        widget = ThumbnailSelectorWidget(parent=self.ui.groupBoxStagingList, dataset_state=None)
        widget.setObjectName("stagingThumbnailWidget")
        widget.thumbnail_size = QSize(96, 96)
        widget.sliderThumbnailSize.setValue(96)
        widget.sliderThumbnailSize.hide()
        widget.frameThumbnailHeader.hide()
        widget.graphics_view.setDragMode(QGraphicsView.DragMode.NoDrag)
        widget.graphics_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        widget.scrollAreaThumbnails.setFrameShape(QFrame.Shape.NoFrame)
        # サムネイル数に応じて枠の高さを自動調整する (最大3行、#1097)。
        # QSplitter 手動リサイズは維持される。
        widget.enable_content_height(max_rows=3)

        insert_index = layout.indexOf(list_widget)
        if insert_index != -1:
            layout.insertWidget(insert_index, widget)
        else:
            layout.addWidget(widget)

        layout.removeWidget(list_widget)
        list_widget.setParent(self)
        list_widget.hide()

        self._staging_thumbnail_widget = widget

    def _update_staging_count_label(self) -> None:
        """ステージング数ラベルを更新する。

        現在のステージング画像数 / 最大数 を表示。
        """
        count = self._staging_state.count()
        self.ui.labelStagingCount.setText(f"{count} / {self.MAX_STAGING_IMAGES} 枚")

    def add_image_ids(self, image_ids: list[int]) -> None:
        """指定した画像 ID リストをステージングに追加する (SSoT へ委譲)。

        最大 MAX_STAGING_IMAGES 枚の上限と重複排除を適用。表示更新とシグナル再
        emit は SSoT の staged_images_changed 経由で行われる。

        Args:
            image_ids: 追加する画像 ID リスト
        """
        self._staging_state.add_image_ids(image_ids)

    def add_selected_images(self) -> None:
        """DatasetStateManager.selected_image_ids をステージングに追加する (SSoT へ委譲)。"""
        self._staging_state.add_selected_images()

    def clear(self) -> None:
        """ステージングリストを全削除する (SSoT へ委譲)。"""
        self._staging_state.clear()

    def remove_image_ids(self, image_ids: list[int]) -> None:
        """指定した画像 ID のみをステージングから除外する (SSoT へ委譲、Issue #571)。

        Args:
            image_ids: 除外する画像 ID リスト。
        """
        self._staging_state.remove_image_ids(image_ids)

    def get_image_ids(self) -> list[int]:
        """ステージング中の画像 ID リストを返す (SSoT へ委譲)。"""
        return self._staging_state.get_image_ids()

    def count(self) -> int:
        """ステージング中の画像数を返す (SSoT へ委譲)。"""
        return self._staging_state.count()

    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]":
        """ステージング中の画像メタデータを返す (SSoT へ委譲)。

        Returns:
            {image_id: (filename, stored_path)} の OrderedDict（追加順）
        """
        return self._staging_state.get_staged_items()

    def _refresh_staging_list_ui(self) -> None:
        """ステージングリスト UI を再描画する。

        OrderedDict の内容をサムネイルウィジェットに反映。
        stored_image_path は相対パスの場合があるため、resolve_stored_path で解決する。
        """
        from lorairo.database.db_core import resolve_stored_path

        staging_paths: list[tuple[str, int]] = []

        for image_id, (_, stored_path) in self._staging_state.get_staged_items().items():
            path = stored_path
            if not path and self._dataset_state_manager:
                metadata = self._dataset_state_manager.get_image_by_id(image_id)
                if metadata:
                    path = metadata.get("stored_image_path", "") or ""

            # 相対パスを絶対パスに解決
            if path:
                path = str(resolve_stored_path(path))

            staging_paths.append((path, image_id))

        if self._staging_thumbnail_widget:
            self._staging_thumbnail_widget.load_thumbnails_from_paths(staging_paths)

        self._update_staging_count_label()
        # 枚数変化 = 行数変化。拡大方向も含めて再配分する (#1097)。
        self._fit_enclosing_splitter_pane(redistribute=True)

    def showEvent(self, event: QShowEvent) -> None:
        """表示時に splitter ペイン高さをコンテンツ準拠へ合わせ直す (#1097)。

        初期化時の refresh は splitter へ parent される前に走るため、空状態の
        クランプが効かない。表示時に祖先 splitter が確定してから再クランプする。
        """
        super().showEvent(event)
        self._fit_enclosing_splitter_pane(redistribute=True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """幅変化時にクランプを再計算する (#1097 Codex P2-1)。

        推奨高さはサムネ列数 = ビューポート幅依存なので、ウィンドウ/横スプリッタの
        幅が変わると行数が変わり cap が stale になる。幅が変わったときだけ再計算する
        (高さのみの変化 = ユーザーの縦ハンドル操作は尊重し、再配分で潰さない)。
        """
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            # サムネ viewport 幅の反映後に再計算する (この時点では列数が stale)。
            self._fit_timer.start(0)

    def _fit_enclosing_splitter_pane(self, *, redistribute: bool = False) -> None:
        """縦 QSplitter 内のステージングペイン高さをコンテンツ準拠に合わせる (#1097)。

        ``enable_content_height`` はサムネ枠自身の sizeHint を縮めるが、パネルの
        実高さは縦 QSplitter (splitterBatchTagMain) の配分で決まり、QSplitter は子の
        sizeHint 変化を自動反映しない。そこで:

        - ペイン widget に ``maximumHeight`` を張り、コンテンツ超の拡大 (= 空白) を抑止。
        - ``redistribute=True`` のとき ``setSizes`` で推奨高さへ明示再配分し、行数増で
          ペインが実際に広がるようにする (Codex P2-3)。

        cap はペイン自身の ``sizeHint`` から取る。実ツリーではペインは StagingWidget
        ではなく BatchTagAddWidget (staging は横 splitter に入れ子) であり、ペインの
        レイアウトマージンや兄弟 (tag 入力) の高さを含めないとサムネが切れるため
        (Codex P2-2)。

        手動リサイズとの共存: 縮小方向は max クランプ内で許可、拡大方向は行数/幅変化
        時のみ setSizes。高さのみの変化 (縦ハンドル操作) では再配分しない。縦 splitter
        の祖先が無い文脈では no-op。
        """
        if self._fitting:
            return
        splitter, pane = self._find_vertical_splitter_pane()
        if splitter is None or pane is None:
            return
        self._fitting = True
        try:
            # サムネ枚数/幅変化直後は入れ子 layout が未 activation で sizeHint が stale。
            # サムネ枠からペインまでの各 layout を内側から activate して最新化する。
            self._activate_layouts_up_to(pane)
            # ペイン自身の推奨高さ = staging コンテンツ + ペインのマージン/兄弟高さ。
            desired = max(pane.sizeHint().height(), pane.minimumSizeHint().height())
            pane.setMaximumHeight(desired)
            if redistribute:
                self._redistribute_splitter(splitter, pane, desired)
        finally:
            self._fitting = False

    def _activate_layouts_up_to(self, ancestor: QWidget) -> None:
        """サムネ枠から ancestor までの sizeHint を最新化する。

        幅変化直後はサムネ枠の再レイアウトが debounce 待ちで、親 layout が旧 sizeHint
        (旧行数) をキャッシュしている。各 widget に ``updateGeometry`` でキャッシュを
        無効化し、``layout.activate`` で再計算させてから読む。
        """
        widget: QWidget | None = self._staging_thumbnail_widget
        while widget is not None:
            widget.updateGeometry()
            layout = widget.layout()
            if layout is not None:
                layout.activate()
            if widget is ancestor:
                break
            widget = widget.parentWidget()

    def _redistribute_splitter(self, splitter: QSplitter, pane: QWidget, desired: int) -> None:
        """縦 splitter でペインへ ``desired`` を割り当て、余剰を兄弟へ比例配分する (#1097)。"""
        sizes = splitter.sizes()
        index = splitter.indexOf(pane)
        if index < 0 or not sizes:
            return
        total = sum(sizes)
        if total <= 0:
            return
        others = [i for i in range(len(sizes)) if i != index]
        # 兄弟ペインを最小サイズ未満に潰さないよう desired を上限側で制限する。
        min_others = 0
        for i in others:
            widget = splitter.widget(i)
            if widget is not None:
                min_others += max(widget.minimumSizeHint().height(), 0)
        target = min(desired, max(0, total - min_others))
        if abs(sizes[index] - target) <= 2:
            return  # 既に目標付近なら何もしない (手動リサイズを尊重)
        remaining = max(0, total - target)
        old_others_total = sum(sizes[i] for i in others) or 1
        new_sizes = list(sizes)
        new_sizes[index] = target
        for i in others:
            new_sizes[i] = round(remaining * sizes[i] / old_others_total)
        splitter.setSizes(new_sizes)

    def _find_vertical_splitter_pane(self) -> tuple[QSplitter | None, QWidget | None]:
        """自身を内包する最も近い縦 QSplitter と、その直下のペイン widget を返す。"""
        child: QWidget = self
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QSplitter) and parent.orientation() == Qt.Orientation.Vertical:
                return parent, child
            child = parent
            parent = parent.parentWidget()
        return None, None

    @Slot()
    def _on_clear_staging_clicked(self) -> None:
        """「クリア」ボタンクリックハンドラ。

        ステージングリストを全削除する。
        """
        self.clear()
