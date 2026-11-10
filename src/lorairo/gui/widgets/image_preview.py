from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QImage,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from ...gui.designer.ImagePreviewWidget_ui import Ui_ImagePreviewWidget
from ...utils.log import logger

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


class ImagePreviewWidget(QWidget, Ui_ImagePreviewWidget):
    """DatasetStateManager統合対応プレビューウィジェット

    Signals:
        crop_requested (int): クロップ作成ボタンが押された画像の ``images.id`` (#1346)。
    """

    # クロップ作成要求 (#1346)。表示中の画像 ID を上げるだけで、ダイアログ生成は
    # CropDialogLauncher が担う。
    crop_requested = Signal(int)

    # プレビュー表示に使う最大辺 (px)。オリジナルがこれを超える場合はデコード時に
    # 縮小し、選択のたびのフル解像度デコード CPU を抑える (#1221)。
    _PREVIEW_MAX_EDGE = 2048

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)

        # QGraphicsScene を作成
        self.graphics_scene = QGraphicsScene()
        self.preview_scene = self.graphics_scene
        self.previewGraphicsView.setScene(self.graphics_scene)

        # スムーススケーリングを有効にする
        self.previewGraphicsView.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self._current_image_path: Path | None = None
        self._current_pixmap: QPixmap | None = None
        # 現在画像 ID は current_image_data_changed (dict チャネル) だけを SSoT とする
        # (#1222 の教訓: 表示クリアの経路を1本化する)。path ベースの load_image() は触らない。
        self._current_image_id: int | None = None
        self._last_load_error: str | None = None

        # ズーム・パン・原寸表示状態 (#1554)
        self._crop_controller: Any = None
        self._zoom_factor: float = 1.0
        self._is_1to1: bool = False
        self._panning: bool = False
        self._pan_start_pos: QPoint = QPoint()
        self._full_res_enabled: bool = False

        self._setup_crop_action_bar()

        self.previewGraphicsView.installEventFilter(self)
        self.previewGraphicsView.viewport().installEventFilter(self)

        self.previewGraphicsView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.previewGraphicsView.customContextMenuRequested.connect(self._show_preview_context_menu)

        # Phase 3.3: Enhanced Event-Driven Pattern (状態管理なし)

        logger.debug("ImagePreviewWidget initialized with Enhanced Event-Driven Pattern support")

    def _is_same_image_loaded(self, image_path: Path) -> bool:
        """同一パスの有効なプレビュー画像が既に表示中か判定する (#1543)。"""
        crop_controller = getattr(self, "_crop_controller", None)
        if crop_controller is not None and bool(getattr(crop_controller, "is_active", False)):
            return False
        return (
            self._current_image_path == image_path
            and self._current_pixmap is not None
            and not self._current_pixmap.isNull()
        )

    @Slot(Path)
    def load_image(self, image_path: Path) -> None:
        """パスベースで画像を読み込む（動的パス解決対応・メモリ最適化）"""
        if self._is_same_image_loaded(image_path):
            logger.debug(f"{image_path.name} は既に表示中のため再デコードをスキップ (#1543)")
            return

        is_same_image = self._current_image_path == image_path
        # Phase 3.3: メモリ最適化 - 既存の表示をクリアしてリソース解放
        self._clear_preview()
        if not is_same_image:
            self._reset_zoom_state()

        try:
            # 画像を読み込み (プレビューは上限サイズへ縮小デコード、#1221 / #1554)
            pixmap = self._decode_preview_pixmap(image_path, full_res=self._full_res_enabled)
            if pixmap.isNull():
                logger.warning(f"画像の読み込みに失敗しました（null pixmap）: {image_path}")
                self._show_load_error(f"画像の読み込みに失敗しました: {image_path.name}")
                return

            # 画像をシーンに追加
            self.pixmap_item = self.graphics_scene.addPixmap(pixmap)
            self._current_image_path = image_path
            self._current_pixmap = pixmap

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_path.name} を プレビュー領域に表示")
        except Exception as e:
            logger.error(f"画像の読み込みに失敗しました: {image_path}, エラー: {e}")
            self._clear_preview()
            self._show_load_error(f"画像の読み込みに失敗しました: {image_path.name}")

    def _show_load_error(self, error_text: str) -> None:
        """画像読み込み失敗時のエラーメッセージをシーンに表示する (#1569)。"""
        self._last_load_error = error_text
        try:
            text_item = self.graphics_scene.addText(error_text)
            if text_item is not None:
                self.preview_scene.setSceneRect(text_item.boundingRect())
                self.previewGraphicsView.centerOn(text_item)
        except Exception as e:
            logger.debug(f"エラーテキストの追加に失敗: {e}")

    def show_decoded_image(self, image: QImage | None, image_path: Path | None = None) -> None:
        """別スレッドでデコード済みの QImage を表示する (#1399)。

        GUI スレッドでは QPixmap への変換だけを行い、ファイルのデコードはしない。
        ``image`` が None / null ならプレビューを空にする。

        Args:
            image: 表示する画像。
            image_path: 元ファイルのパス (右クリックのコピーで元画像を読み直すため)。
        """
        is_same_image = self._current_image_path is not None and self._current_image_path == image_path
        self._clear_preview()
        if not is_same_image:
            self._reset_zoom_state()
        if image is None or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self.pixmap_item = self.graphics_scene.addPixmap(pixmap)
        self._current_image_path = image_path
        self._current_pixmap = pixmap
        self.graphics_scene.setSceneRect(pixmap.rect())
        QTimer.singleShot(0, self._adjust_view_size)

    def clear_preview(self) -> None:
        """プレビューを空にする (#1399)。"""
        self._clear_preview()
        self._reset_zoom_state()

    def load_image_from_pil(self, pil_image: Image.Image, image_name: str = "Unknown") -> None:
        """PILイメージオブジェクトから直接画像を読み込む（メモリ最適化）"""
        # Phase 3.3: メモリ最適化 - 既存の表示をクリアしてリソース解放
        self._clear_preview()

        try:
            # PILイメージをQPixmapに変換
            pixmap = self._pil_to_qpixmap(pil_image)

            # PixmapがNull（変換失敗）でないことを確認
            if pixmap.isNull():
                logger.warning(f"Failed to convert PIL image to pixmap: {image_name}")
                return

            # 画像をシーンに追加
            self.pixmap_item = self.graphics_scene.addPixmap(pixmap)
            self._current_image_path = None
            self._current_pixmap = pixmap

            # シーンの矩形を画像のサイズに設定
            self.graphics_scene.setSceneRect(pixmap.rect())

            # サイズ調整処理を遅延
            QTimer.singleShot(0, self._adjust_view_size)
            logger.debug(f"{image_name} を プレビュー領域に表示（PILイメージから）")
        except Exception as e:
            logger.error(f"PILイメージの読み込みに失敗しました: {image_name}, エラー: {e}")
            self._clear_preview()

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """PILイメージをQPixmapに変換"""
        # RGBまたはRGBAモードに変換
        if pil_image.mode not in ["RGB", "RGBA"]:
            pil_image = pil_image.convert("RGB")

        # PILイメージをバイト配列に変換
        import io

        byte_array = io.BytesIO()
        pil_image.save(byte_array, format="PNG")
        byte_array.seek(0)

        # QPixmapとして読み込み
        pixmap = QPixmap()
        pixmap.loadFromData(byte_array.getvalue())
        return pixmap

    def _decode_preview_pixmap(self, image_path: Path, full_res: bool | None = None) -> QPixmap:
        """プレビュー表示用に、上限サイズへ縮小デコードした QPixmap を返す (#1221 / #1554)。

        オリジナル解像度をフルデコードせず、QImageReader.setScaledSize でデコード時点で
        縮小することで、選択のたびの CPU コストを抑える。full_res=True の場合は縮小しない。
        読み込み失敗時は null QPixmap を返す。

        Args:
            image_path: 読み込む画像ファイルのパス。
            full_res: True のとき _PREVIEW_MAX_EDGE 縮小をスキップして原寸デコードする。

        Returns:
            上限 _PREVIEW_MAX_EDGE に収まるよう縮小した QPixmap (または原寸)。失敗時は null QPixmap。
        """
        use_full_res = self._full_res_enabled if full_res is None else full_res
        reader = QImageReader(str(image_path))
        reader.setAutoTransform(True)
        size = reader.size()
        if (
            not use_full_res
            and size.isValid()
            and (size.width() > self._PREVIEW_MAX_EDGE or size.height() > self._PREVIEW_MAX_EDGE)
        ):
            bounded = size.scaled(
                self._PREVIEW_MAX_EDGE,
                self._PREVIEW_MAX_EDGE,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            reader.setScaledSize(bounded)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image)

    def _setup_crop_action_bar(self) -> None:
        """プレビュー下部に原寸トグル・クロップ作成ボタンの操作バーを追加する (#1346 / #1554)。

        .ui は変更せず code-only で 1 行追加する。エクスポート/その他の再利用箇所で
        死んだボタンを見せないため既定は非表示で、配線したタブが
        :meth:`set_crop_action_visible` で表示する。
        """
        self._crop_action_bar = QWidget(self)
        bar_layout = QHBoxLayout(self._crop_action_bar)
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(4)
        bar_layout.addStretch(1)

        self._full_res_button = QToolButton(self._crop_action_bar)
        self._full_res_button.setObjectName("previewFullResButton")
        self._full_res_button.setText("原寸")
        self._full_res_button.setToolTip("2048px縮小を解除して元解像度で読み込みます")
        self._full_res_button.setCheckable(True)
        self._full_res_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._full_res_button.toggled.connect(self._on_full_res_toggled)
        bar_layout.addWidget(self._full_res_button)

        self._crop_button = QPushButton("クロップして学習素材を作成…", self._crop_action_bar)
        self._crop_button.setObjectName("previewCropButton")
        self._crop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._crop_button.setEnabled(False)
        self._crop_button.clicked.connect(self._on_crop_button_clicked)
        bar_layout.addWidget(self._crop_button)

        self.verticalLayout.addWidget(self._crop_action_bar)
        self._crop_action_bar.setVisible(False)

    _setup_action_bar = _setup_crop_action_bar

    @Slot(bool)
    def _on_full_res_toggled(self, checked: bool) -> None:
        """原寸読み込みトグル変更時に現在画像を再デコードする (#1554)。"""
        self._full_res_enabled = checked
        if self._current_image_path is not None:
            self.load_image(self._current_image_path)

    def set_crop_action_visible(self, visible: bool) -> None:
        """クロップ作成ボタンの表示/非表示を切り替える (#1346)。

        Args:
            visible: True で操作バーを表示する。
        """
        self._crop_action_bar.setVisible(visible)

    def current_image_id(self) -> int | None:
        """プレビュー中の画像 ID。未選択なら None。"""
        return self._current_image_id

    def _set_current_image_id(self, image_id: int | None) -> None:
        """現在画像 ID を更新し、クロップボタンの活性を追従させる。"""
        self._current_image_id = image_id
        self._crop_button.setEnabled(image_id is not None)

    def _on_crop_button_clicked(self) -> None:
        """クロップ作成ボタン押下を crop_requested へ変換する。"""
        if self._current_image_id is None:
            logger.debug("Crop requested without a current image - ignored")
            return
        self.crop_requested.emit(self._current_image_id)

    def _adjust_view_size(self) -> None:
        # pixmap_item が None の場合はスキップ（sceneRect が (0,0,0,0) の状態での縮小を防ぐ）
        # ユーザーがズームまたは 1:1 表示中は fitInView で上書きしない (#1554)
        if self.pixmap_item is not None and not self._is_1to1 and self._zoom_factor == 1.0:
            self.previewGraphicsView.fitInView(
                self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
            )

    def _reset_zoom_state(self) -> None:
        """ズーム・1:1・パン状態を初期化する (#1554)。"""
        self._zoom_factor = 1.0
        self._is_1to1 = False
        self._panning = False
        self.previewGraphicsView.resetTransform()
        self._update_viewport_cursor()

    def _update_viewport_cursor(self) -> None:
        """ズーム状態に応じて viewport カーソルを更新する (#1554)。"""
        viewport = self.previewGraphicsView.viewport()
        if self._panning:
            viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._zoom_factor > 1.0 or self._is_1to1:
            viewport.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            viewport.setCursor(Qt.CursorShape.ArrowCursor)

    def _apply_zoom_step(self, step: float) -> None:
        """指定倍率でズームし [0.2, 8.0] にクランプする (#1554)。"""
        if self._crop_controller is not None or not self._has_current_image():
            return
        new_zoom = max(0.2, min(8.0, self._zoom_factor * step))
        actual_factor = new_zoom / self._zoom_factor
        if actual_factor != 1.0:
            self.previewGraphicsView.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.previewGraphicsView.scale(actual_factor, actual_factor)
            self._zoom_factor = new_zoom
        self._update_viewport_cursor()

    def zoom_in(self) -> None:
        """プレビューを拡大する (#1554)。"""
        self._apply_zoom_step(1.15)

    def zoom_out(self) -> None:
        """プレビューを縮小する (#1554)。"""
        self._apply_zoom_step(1.0 / 1.15)

    def reset_zoom(self) -> None:
        """ズームをリセットして Fit-to-View に戻す (#1554)。"""
        self._reset_zoom_state()
        self._adjust_view_size()

    def set_1to1_zoom(self) -> None:
        """1:1 ピクセル等倍表示に切り替える (#1554)。"""
        if self._crop_controller is not None or not self._has_current_image():
            return
        self.previewGraphicsView.resetTransform()
        self._is_1to1 = True
        self._zoom_factor = 1.0
        self._update_viewport_cursor()

    def toggle_1to1_zoom(self) -> None:
        """Fit-to-View と 1:1 等倍表示をトグルする (#1554)。"""
        if self._crop_controller is not None or not self._has_current_image():
            return
        if self._is_1to1:
            self.reset_zoom()
        else:
            self.set_1to1_zoom()

    def _handle_wheel_event(self, event: QWheelEvent) -> bool:
        """ホイール操作によるズーム処理 (#1554)。"""
        if not self._has_current_image():
            return False
        delta_y = event.angleDelta().y()
        if delta_y > 0:
            self.zoom_in()
        elif delta_y < 0:
            self.zoom_out()
        return True

    def _handle_mouse_event(self, event: QMouseEvent) -> bool:
        """マウス操作による等倍トグル・ドラッグパン処理 (#1554)。"""
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            if self._has_current_image():
                self.toggle_1to1_zoom()
                return True
            return False
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self._zoom_factor > 1.0 or self._is_1to1:
                self._panning = True
                self._pan_start_pos = event.pos()
                self._update_viewport_cursor()
                return True
            return False
        if event_type == QEvent.Type.MouseMove and self._panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            h_bar = self.previewGraphicsView.horizontalScrollBar()
            v_bar = self.previewGraphicsView.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            return True
        if (
            event_type == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._panning
        ):
            self._panning = False
            self._update_viewport_cursor()
            return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """プレビューのホイールズーム・ドラッグパン・ダブルクリック等倍切替を処理する (#1554)。"""
        if self._crop_controller is None and watched in (
            self.previewGraphicsView,
            self.previewGraphicsView.viewport(),
        ):
            if event.type() == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
                if self._handle_wheel_event(event):
                    return True
            elif isinstance(event, QMouseEvent) and self._handle_mouse_event(event):
                return True
        return super().eventFilter(watched, event)

    def _show_preview_context_menu(self, position: QPoint) -> None:
        """プレビュー用コンテキストメニューを表示する"""
        menu = QMenu(self.previewGraphicsView)
        menu.addAction(self._create_copy_image_action(menu))
        menu.exec(self.previewGraphicsView.mapToGlobal(position))

    def _create_copy_image_action(self, parent: QWidget) -> QAction:
        """現在画像コピー用アクションを作成する"""
        copy_action = QAction("画像をコピー", parent)
        copy_action.setEnabled(self._has_current_image())
        copy_action.triggered.connect(self.copy_current_image_to_clipboard)
        return copy_action

    def _has_current_image(self) -> bool:
        """コピー可能な画像状態があるか判定する"""
        return self._current_pixmap is not None and not self._current_pixmap.isNull()

    def copy_current_image_to_clipboard(self) -> bool:
        """現在表示中の画像をクリップボードへコピーする"""
        if not self._has_current_image():
            logger.debug("Copy preview image requested without a current image")
            return False

        pixmap = self._load_current_original_pixmap()
        if pixmap is None and self._current_pixmap is not None and not self._current_pixmap.isNull():
            pixmap = self._current_pixmap

        if pixmap is None or pixmap.isNull():
            logger.debug("Copy preview image skipped because no valid pixmap is available")
            return False

        QApplication.clipboard().setPixmap(pixmap)
        logger.debug("Current preview image copied to clipboard")
        return True

    def _load_current_original_pixmap(self) -> QPixmap | None:
        """保存パスから元画像を読み直す。失敗時は None を返す。"""
        if self._current_image_path is None or not self._current_image_path.exists():
            return None

        pixmap = QPixmap(str(self._current_image_path))
        if pixmap.isNull():
            return None
        return pixmap

    # resizeEvent をオーバーライドしてウィンドウサイズ変更時にサイズ調整
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_view_size()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._adjust_view_size()

    # === Phase 3.3: Enhanced Event-Driven Pattern ===

    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（状態管理なし）

        接続経路の詳細をログに記録し、問題診断を可能にする。
        connect()の戻り値を検証し、接続失敗を検出する。

        Args:
            state_manager: DatasetStateManagerインスタンス
        """
        logger.debug(
            f"connect_to_data_signals() 呼び出し開始 - "
            f"widget instance: {id(self)}, state_manager: {id(state_manager)}"
        )

        if not state_manager:
            logger.error("DatasetStateManager is None - 接続中止")
            return

        # シグナル接続（戻り値を確認）
        connection = state_manager.current_image_data_changed.connect(self._on_image_data_received)
        connection_valid = bool(connection)

        logger.debug(f"connect()戻り値: valid={connection_valid}, type={type(connection)}")

        if not connection_valid:
            logger.error("Qt接続失敗 - connect()が無効なConnectionを返しました")
            return

        # シグナル配線の完了は接続時1回だけ INFO で残す (logging.md)
        logger.info(f"current_image_data_changed シグナル接続完了 - from {id(state_manager)} to {id(self)}")

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict[str, Any]) -> None:
        """
        画像データ受信時のプレビュー更新（純粋表示専用）

        DatasetStateManagerから直接送信される完全な画像メタデータを受信し、
        プレビュー表示を更新します。検索機能への依存を完全に排除。
        """
        try:
            logger.debug(
                f"ImagePreviewWidget: current_image_data_changed シグナル受信 - データサイズ: {len(image_data) if image_data else 0}"
            )

            # 表示できるまでは現在画像 ID を未確定に戻し、クロップ導線を無効化する
            self._set_current_image_id(None)

            # 空データの場合はプレビューをクリア
            if not image_data:
                logger.debug("Empty image data received, clearing preview")
                self._clear_preview()
                return

            # 画像IDを取得（ログ用）
            image_id = image_data.get("id", "Unknown")
            logger.debug(f"画像データ受信: ID={image_id}")

            # ファイルパスを取得
            image_path_str = image_data.get("stored_image_path")
            if not image_path_str:
                logger.warning(f"画像パス未設定 ID:{image_id} | メタデータ: {list(image_data.keys())}")
                self._clear_preview()
                return

            # プレビュー更新（LoRAIro標準パス解決使用）
            from ...database.db_core import resolve_stored_path

            image_path = resolve_stored_path(image_path_str)
            if not image_path.exists():
                logger.warning(f"画像ファイル不存在 ID:{image_id} | パス: {image_path}")
                self._clear_preview()
                return

            if self._is_same_image_loaded(image_path):
                self._set_current_image_id(image_id if isinstance(image_id, int) else None)
                logger.debug(
                    f"プレビュー既に表示中のため再デコードをスキップ: ID={image_id}, path={image_path.name} (#1543)"
                )
                return

            self.load_image(image_path)
            if self._current_pixmap is None:
                # デコード失敗 (破損・非対応形式) はプレビュー空のままクロップも無効にする
                logger.warning(f"プレビューを生成できなかったためクロップを無効化 ID:{image_id}")
                self._set_current_image_id(None)
                return
            self._set_current_image_id(image_id if isinstance(image_id, int) else None)

            logger.debug(f"プレビュー表示成功: ID={image_id}, path={image_path.name}")

        except Exception as e:
            logger.opt(exception=True).error(
                f"プレビュー更新エラー データ:{image_data.get('id', 'Unknown')} | エラー: {e}"
            )
            self._set_current_image_id(None)
            self._clear_preview()

    def _clear_preview(self) -> None:
        """プレビューをクリア（メモリ最適化）"""
        try:
            # GraphicsSceneをクリアしてメモリを解放
            self.graphics_scene.clear()

            # PixmapItemの参照もクリア
            self.pixmap_item = None
            self._current_image_path = None
            self._current_pixmap = None
            self._last_load_error = None

            logger.debug("Preview cleared and memory optimized")

        except Exception as e:
            logger.opt(exception=True).error(f"Error clearing preview: {e}")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget = ImagePreviewWidget()
    widget.resize(800, 600)
    widget.show()
    widget.load_image(Path("tests/resources/img/1_img/file01.webp"))
    app.exec()
