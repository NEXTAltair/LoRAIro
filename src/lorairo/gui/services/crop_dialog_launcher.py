"""クロップ作成ダイアログの起動と保存配線を集約する GUI サービス (#1346)。

画像一覧の右クリックとプレビューのボタンは ``crop_requested(image_id)`` を上げるだけで、
「親画像の情報を引く → :class:`~lorairo.gui.widgets.crop_dialog.CropDialog` を組み立てる →
保存 callback をサービス層へ繋ぐ → 保存成功を上位へ中継する」までを本クラスが持つ。
タブ / MainWindow は接着剤のままにする (ADR 0036 / Epic #867)。

保存 callback は将来ダイアログ内部の worker スレッドから呼ばれるため、Qt ウィジェット
に触れず ``lorairo.services.crop_service`` の呼び出しだけで完結させる。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget
from sqlalchemy.exc import SQLAlchemyError

from ...database.db_core import get_current_project_root
from ...database.db_manager import ImageDatabaseManager
from ...domain.crop_request import CropCreateRequest
from ...filesystem import FileSystemManager
from ...services.crop_service import create_crop_image, get_crop_source_info
from ...utils.log import logger
from ..widgets.crop_dialog import CropDialog

_OPEN_ERROR_TITLE = "クロップを開けません"


class CropDialogLauncher(QObject):
    """クロップダイアログを生成し、保存結果を上位へ中継するサービス。

    Signals:
        crop_saved (int, int): 保存成功時の (親画像 ID, 子画像 ID)。
    """

    crop_saved = Signal(int, int)

    def __init__(
        self,
        *,
        db_manager: ImageDatabaseManager,
        fsm: FileSystemManager,
        parent: QObject | None = None,
    ) -> None:
        """ランチャーを初期化する。

        Args:
            db_manager: 親画像情報の取得とクロップ画像の登録に使う DB マネージャー。
            fsm: 切り出しファイルの保存先を握る FileSystemManager。未初期化なら
                ダイアログを開く時点で現在のプロジェクトルートで初期化する。
            parent: 親 QObject。
        """
        super().__init__(parent)
        self._db_manager = db_manager
        self._fsm = fsm
        # open() は非ブロッキングのため、参照を保持しないと GC でダイアログが消える。
        self._open_dialogs: list[CropDialog] = []
        logger.debug("CropDialogLauncher initialized")

    def open_for_image(self, image_id: int, parent: QWidget | None = None) -> CropDialog | None:
        """指定画像を親としてクロップダイアログを開く。

        子画像 (孫作成) でも扱いは同じで、``image_id`` がそのまま直接の親になる。

        Args:
            image_id: クロップ元となる画像 ID。
            parent: ダイアログの親ウィジェット。

        Returns:
            開いた :class:`CropDialog`。親画像情報を取得できなかった場合は None。
        """
        try:
            self._ensure_fsm_initialized()
            source = get_crop_source_info(image_id, db_manager=self._db_manager)
        except (ValueError, OSError, SQLAlchemyError) as exc:
            logger.opt(exception=True).error(f"クロップ元画像の取得に失敗しました: image_id={image_id}")
            QMessageBox.critical(parent, _OPEN_ERROR_TITLE, f"クロップを開始できません: {exc}")
            return None

        dialog = CropDialog(
            image_path=source.image_path,
            parent_image_id=image_id,
            candidate_tags=source.candidate_tags,
            parent_rating=source.rating,
            save_callback=self._build_save_callback(),
            parent=parent,
        )
        dialog.saved.connect(lambda child_id: self._on_saved(image_id, child_id))
        dialog.finished.connect(lambda _result: self._forget_dialog(dialog))
        self._open_dialogs.append(dialog)
        dialog.open()
        logger.info(f"クロップダイアログを開きました: parent_image_id={image_id}")
        return dialog

    def _ensure_fsm_initialized(self) -> None:
        """保存先ディレクトリが未初期化なら現在のプロジェクトルートで初期化する。

        GUI の FileSystemManager はデータセット登録を実行した時にしか初期化されないため、
        登録を経ずにクロップだけ行うセッションでも ``save_original_image`` が動くようにする。

        Raises:
            OSError: プロジェクト配下のディレクトリ作成に失敗した場合。
        """
        if self._fsm.original_images_dir is not None:
            return
        project_root = get_current_project_root()
        self._fsm.initialize(project_root)
        logger.info(f"クロップ保存用に FileSystemManager を初期化: {project_root}")

    def _build_save_callback(self) -> Callable[[CropCreateRequest], int]:
        """ダイアログへ渡す保存 callback を作る (Qt には触れない)。"""

        def save(request: CropCreateRequest) -> int:
            return create_crop_image(request, db_manager=self._db_manager, fsm=self._fsm)

        return save

    def _on_saved(self, parent_image_id: int, child_image_id: int) -> None:
        """ダイアログの保存成功を上位へ中継する。"""
        logger.info(
            f"クロップ画像を作成しました: parent_image_id={parent_image_id}, "
            f"child_image_id={child_image_id}"
        )
        self.crop_saved.emit(parent_image_id, child_image_id)

    def _forget_dialog(self, dialog: CropDialog) -> None:
        """閉じたダイアログの参照を解放し、Qt 側でも破棄予約する。

        ダイアログは親ウィジェット (長寿命のタブ) に parent されているため、参照を
        外すだけでは QObject ツリーに残り元画像の pixmap を保持し続ける。
        """
        if dialog in self._open_dialogs:
            self._open_dialogs.remove(dialog)
        dialog.deleteLater()
