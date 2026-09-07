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
from typing import TYPE_CHECKING

import shiboken6
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget
from sqlalchemy.exc import SQLAlchemyError

from ...database.db_core import get_current_project_root
from ...database.db_manager import ImageDatabaseManager
from ...domain.crop_request import CropCreateRequest
from ...filesystem import FileSystemManager
from ...services.crop_service import CropSourceInfo, create_crop_image, get_crop_source_info
from ...utils.language_keys import dedupe_languages_by_family
from ...utils.log import logger
from ..widgets.crop_dialog import CropDialog
from ..workers.manager import WorkerManager
from ..workers.tag_metadata_worker import TagMetadataResult, TagMetadataWorker

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader

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
        merged_reader: MergedTagReader | None = None,
        parent: QObject | None = None,
    ) -> None:
        """ランチャーを初期化する。

        Args:
            db_manager: 親画像情報の取得とクロップ画像の登録に使う DB マネージャー。
            fsm: 切り出しファイルの保存先を握る FileSystemManager。未初期化なら
                ダイアログを開く時点で現在のプロジェクトルートで初期化する。
            merged_reader: タグ翻訳取得用の MergedTagReader (#1355)。None なら
                翻訳表示を無効にしてダイアログだけ開く。
            parent: 親 QObject。
        """
        super().__init__(parent)
        self._db_manager = db_manager
        self._fsm = fsm
        self._merged_reader = merged_reader
        # open() は非ブロッキングのため、参照を保持しないと GC でダイアログが消える。
        self._open_dialogs: list[CropDialog] = []
        # タグ翻訳解決 worker (#1355)。worker/QThread の所有は WorkerManager が持つ。
        self._tag_metadata_manager: WorkerManager | None = None
        self._tag_metadata_generation = 0
        # worker_id -> (ダイアログ, tag_id -> 原文タグ)。結果到着時の逆引きに使う。
        self._tag_metadata_targets: dict[str, tuple[CropDialog, dict[int, str]]] = {}
        logger.debug("CropDialogLauncher initialized")

    def set_merged_reader(self, reader: MergedTagReader | None) -> None:
        """タグ翻訳取得用の MergedTagReader を差し替える (#1355)。

        Args:
            reader: MergedTagReader。None で翻訳表示を無効にする。
        """
        self._merged_reader = reader

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
        # 翻訳解決は tag DB 待ちになり得るため、ダイアログ表示後に非同期で始める (#1355)。
        self._start_tag_metadata_worker(dialog, source, image_id)
        logger.info(f"クロップダイアログを開きました: parent_image_id={image_id}")
        return dialog

    def _start_tag_metadata_worker(self, dialog: CropDialog, source: CropSourceInfo, image_id: int) -> None:
        """候補タグの翻訳を非同期解決する worker を起動する (#1355)。

        tag DB が使えない (reader 未注入) 場合や tag_id を持つ候補タグが無い場合は
        何もしない (翻訳なしで原文表示のまま)。

        Args:
            dialog: 結果を反映するダイアログ。
            source: 候補タグと tag_id を持つクロップ元情報。
            image_id: 親画像 ID (worker の結果照合用)。
        """
        if self._merged_reader is None:
            logger.debug("MergedTagReader 未注入 - クロップダイアログのタグ翻訳をスキップ")
            return
        # tag_id -> 原文タグ (候補の表示順を保つ)。worker には行形式に直して渡す。
        tag_by_id = {
            source.candidate_tag_ids[tag]: tag
            for tag in source.candidate_tags
            if tag in source.candidate_tag_ids
        }
        tags_list: list[dict[str, str | int]] = [
            {"tag": tag, "tag_id": tag_id} for tag_id, tag in tag_by_id.items()
        ]
        if not tags_list:
            logger.debug("tag_id を持つ候補タグが無いため、クロップダイアログのタグ翻訳をスキップ")
            return

        if self._tag_metadata_manager is None:
            self._tag_metadata_manager = WorkerManager(self)
        self._tag_metadata_generation += 1
        worker_id = f"crop_tag_metadata_{self._tag_metadata_generation}"
        self._tag_metadata_targets[worker_id] = (dialog, tag_by_id)

        worker = TagMetadataWorker(
            self._merged_reader,
            image_id=image_id,
            tags_list=tags_list,
            generation=self._tag_metadata_generation,
        )
        worker.finished.connect(lambda result: self._on_tag_metadata_finished(worker_id, result))
        worker.error_occurred.connect(lambda message: self._on_tag_metadata_error(worker_id, message))
        worker.canceled.connect(lambda: self._tag_metadata_targets.pop(worker_id, None))
        self._tag_metadata_manager.start_worker(worker_id, worker)

    def _on_tag_metadata_finished(self, worker_id: str, result: object) -> None:
        """解決済み翻訳をダイアログへ反映する (閉じたダイアログの結果は捨てる)。

        Args:
            worker_id: 起動時に割り当てた worker ID。
            result: :class:`TagMetadataResult` (worker の finished は object 型で来る)。
        """
        target = self._tag_metadata_targets.pop(worker_id, None)
        if target is None or not isinstance(result, TagMetadataResult):
            return
        dialog, tag_by_id = target
        if dialog not in self._open_dialogs or not shiboken6.isValid(dialog):
            # 解決完了より先に閉じられた: 破棄済みウィジェットに触れない
            logger.debug(f"クロップダイアログが閉じているため翻訳を破棄: worker_id={worker_id}")
            return

        translations: dict[str, dict[str, str]] = {}
        languages: list[str] = []
        for tag_id, by_language in result.translations.items():
            tag = tag_by_id.get(tag_id)
            if tag is None:
                continue
            resolved = {language: text for language, text in by_language.items() if text}
            if not resolved:
                continue
            translations[tag] = resolved
            languages.extend(resolved)
        # 実際に訳が付いた言語だけを候補にする (訳の無い言語を選ばせても原文に落ちるだけ)。
        available_languages = dedupe_languages_by_family(languages)
        dialog.set_tag_translations(translations, available_languages)
        logger.debug(
            f"クロップダイアログへタグ翻訳を反映: tags={len(translations)}, "
            f"languages={len(available_languages)}"
        )

    def _on_tag_metadata_error(self, worker_id: str, message: str) -> None:
        """翻訳解決の失敗を記録する (翻訳なしで原文表示のまま続行する)。"""
        self._tag_metadata_targets.pop(worker_id, None)
        logger.warning(f"クロップダイアログのタグ翻訳解決に失敗 (原文のまま表示): {message}")

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
        # 未完了の翻訳 worker が破棄済みダイアログを掴み続けないよう対象から外す (#1355)
        stale = [key for key, (target, _) in self._tag_metadata_targets.items() if target is dialog]
        for worker_id in stale:
            del self._tag_metadata_targets[worker_id]
        dialog.deleteLater()
