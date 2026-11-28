"""選んだ画像からデータセットの版を作るダイアログ (Issue #1661, ADR 0112)。

入口は検索タブの「選んだ画像から版を作る…」ボタン。別プロジェクトからコピーした画像を含め、
現在のプロジェクトの画像を 1 フォルダの版にする。「計画を確認」で何も書かずに計画 (画像ごとの
学習テキストと由来) を表示し、計画と同じ入力のまま「版を作成」を押したときだけ書き込む。
計画と作成は worker スレッドで行う。CLI の `dataset build-version` と同じ
`DatasetVersionBuildService` を使う。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.dataset_version_build_service import (
    BuildVersionPlan,
    BuildVersionRequest,
    BuildVersionResult,
    DatasetVersionBuildService,
)
from ...utils.log import logger
from ..message_box import show_information, show_warning
from ..workers.cross_project_workers import DatasetVersionBuildWorker, DatasetVersionProposeWorker
from ..workers.manager import WorkerManager
from .ds_button import DsButton
from .ds_summary_stat import DsSummaryStat
from .image_origin_widget import ImageOriginEntry, format_origins

_PLAN_HEADERS = ["画像 ID", "ファイル名", "学習テキスト (.txt)", "由来"]


class DatasetVersionBuildDialog(QDialog):
    """選んだ画像から版を作る。

    Signals:
        version_built (int): 作った版の ID。
    """

    version_built = Signal(int)

    # worker スレッドから GUI スレッドへ結果を渡す (受け手はダイアログ = GUI スレッド)
    _plan_ready = Signal(object)
    _build_finished = Signal(object)
    _task_failed = Signal(str, str)

    def __init__(
        self,
        service: DatasetVersionBuildService,
        image_ids: Sequence[int],
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを初期化する。

        Args:
            service: 版の作成 service (現在のプロジェクトの DB を束縛したもの)。
            image_ids: 版に入れる画像 ID (この順に並べる)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("選んだ画像から版を作る")
        self.resize(820, 560)
        self._service = service
        self._image_ids = list(dict.fromkeys(image_ids))
        self._plan: BuildVersionPlan | None = None
        self._busy = False
        self._worker_manager = WorkerManager(self)
        self._build_ui()
        self._plan_ready.connect(self._on_plan_ready)
        self._build_finished.connect(self._on_build_finished)
        self._task_failed.connect(self._on_task_failed)

    # --- UI ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(f"選んだ {len(self._image_ids)} 枚の画像で、1 フォルダの版を作ります。", self)
        )

        form = QFormLayout()
        self.dataset_edit = QLineEdit(self)
        self.dataset_edit.setPlaceholderText("無ければ作ります")
        self.version_edit = QLineEdit(self)
        self.folder_edit = QLineEdit(self)
        self.folder_edit.setPlaceholderText("<繰り返し数>_<名前> (例: 10_mychar)")
        self.trigger_edit = QLineEdit(self)
        self.trigger_edit.setPlaceholderText("任意。学習テキストの先頭に置きます")
        form.addRow("データセット名", self.dataset_edit)
        form.addRow("版の名前", self.version_edit)
        form.addRow("フォルダ名", self.folder_edit)
        form.addRow("トリガーワード", self.trigger_edit)
        root.addLayout(form)
        for edit in (self.dataset_edit, self.version_edit, self.folder_edit, self.trigger_edit):
            edit.textChanged.connect(self._update_buttons)

        stats = QHBoxLayout()
        self.image_stat = DsSummaryStat("画像", "-", "版に入れる枚数", None, self)
        self.repeat_stat = DsSummaryStat("繰り返し", "-", "フォルダ名から", None, self)
        self.origin_stat = DsSummaryStat("別プロジェクト由来", "-", "コピーした画像", "info", self)
        for stat in (self.image_stat, self.repeat_stat, self.origin_stat):
            stats.addWidget(stat)
        root.addLayout(stats)

        self.plan_table = QTableWidget(0, len(_PLAN_HEADERS), self)
        self.plan_table.setObjectName("datasetVersionPlanTable")
        self.plan_table.setHorizontalHeaderLabels(_PLAN_HEADERS)
        self.plan_table.verticalHeader().setVisible(False)
        self.plan_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.plan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.plan_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.plan_table, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("入力してから「計画を確認」を押してください", self)
        bottom.addWidget(self.status_label, 1)
        self.propose_button = DsButton("計画を確認", kind="secondary", parent=self)
        self.propose_button.clicked.connect(self.start_propose)
        self.build_button = DsButton("版を作成", kind="primary", parent=self)
        self.build_button.clicked.connect(self.start_build)
        self.close_button = DsButton("閉じる", kind="secondary", parent=self)
        self.close_button.clicked.connect(self.reject)
        for button in (self.propose_button, self.build_button, self.close_button):
            bottom.addWidget(button)
        root.addLayout(bottom)
        self._update_buttons()

    def current_request(self) -> BuildVersionRequest | None:
        """入力から版の指定を作る。必須の欄が空なら None。"""
        dataset = self.dataset_edit.text().strip()
        version = self.version_edit.text().strip()
        folder = self.folder_edit.text().strip()
        if not (dataset and version and folder and self._image_ids):
            return None
        trigger = self.trigger_edit.text().strip()
        return BuildVersionRequest(
            dataset_name=dataset,
            version_name=version,
            dir_name=folder,
            image_ids=tuple(self._image_ids),
            trigger_word=trigger or None,
        )

    def _plan_is_current(self) -> bool:
        """表示中の計画が、今の入力と同じ指定で作ったものか。"""
        return self._plan is not None and self._plan.request == self.current_request()

    @Slot()
    def _update_buttons(self) -> None:
        has_request = self.current_request() is not None
        self.propose_button.setEnabled(not self._busy and has_request)
        self.build_button.setEnabled(not self._busy and self._plan_is_current())
        self.close_button.setEnabled(not self._busy)

    def _set_busy(self, busy: bool, status_text: str | None = None) -> None:
        self._busy = busy
        if status_text is not None:
            self.status_label.setText(status_text)
        self._update_buttons()

    # --- 計画 ---

    @Slot()
    def start_propose(self) -> None:
        """入力の指定で計画を作る (何も書かない)。"""
        request = self.current_request()
        if self._busy or request is None:
            return
        self._set_busy(True, "計画を作成中...")
        worker = DatasetVersionProposeWorker(self._service, request)
        # 以下の lambda は worker スレッドで走るが Signal を emit するだけ (スレッド安全)
        worker.finished.connect(lambda result: self._plan_ready.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("propose", str(message)))
        self._worker_manager.start_worker("dataset_version_propose", worker)

    @Slot(object)
    def _on_plan_ready(self, plan: object) -> None:
        if not isinstance(plan, BuildVersionPlan):
            self._set_busy(False)
            return
        self._plan = plan
        self.plan_table.setRowCount(len(plan.images))
        for row, image in enumerate(plan.images):
            origins = [ImageOriginEntry(o.source_project_name, o.source_image_id) for o in image.origins]
            values = [str(image.image_id), image.file_stem, image.text or "-", format_origins(origins)]
            for column, value in enumerate(values):
                self.plan_table.setItem(row, column, QTableWidgetItem(value))
        copied = sum(1 for image in plan.images if image.origins)
        self.image_stat.set_value(str(len(plan.images)))
        self.repeat_stat.set_value(str(plan.num_repeats))
        self.origin_stat.set_value(str(copied))
        self._set_busy(False, "計画です (何も書き込んでいません)。「版を作成」で作ります")

    @property
    def plan(self) -> BuildVersionPlan | None:
        """表示中の計画。"""
        return self._plan

    # --- 作成 ---

    @Slot()
    def start_build(self) -> None:
        """計画と同じ指定で版を作る。"""
        if self._busy or not self._plan_is_current() or self._plan is None:
            return
        request = self._plan.request
        self._set_busy(True, "版を作成中...")
        worker = DatasetVersionBuildWorker(self._service, request)
        worker.finished.connect(lambda result: self._build_finished.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("build", str(message)))
        self._worker_manager.start_worker("dataset_version_build", worker)

    @Slot(object)
    def _on_build_finished(self, result: object) -> None:
        self._set_busy(False)
        if not isinstance(result, BuildVersionResult):
            return
        request = result.plan.request
        self.status_label.setText(f"版を作成しました (版 ID {result.version_id})")
        logger.info(
            f"版を作成 (GUI): dataset='{request.dataset_name}', version='{request.version_name}', "
            f"version_id={result.version_id}, images={len(result.plan.images)}"
        )
        self.version_built.emit(result.version_id)
        show_information(
            self,
            "版を作成しました",
            f"データセット: {request.dataset_name}\n版: {request.version_name} (ID {result.version_id})\n"
            f"フォルダ: {request.dir_name}\n画像: {len(result.plan.images)} 枚",
        )
        self.accept()

    # --- 失敗・終了 ---

    @Slot(str, str)
    def _on_task_failed(self, task: str, message: str) -> None:
        self._set_busy(False)
        title = "計画を作れません" if task == "propose" else "版を作れませんでした"
        self.status_label.setText(title)
        show_warning(self, title, message)

    def reject(self) -> None:
        """処理中は閉じない。"""
        if self._busy:
            return
        self._worker_manager.cancel_all_workers()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """処理中はウィンドウを閉じない。"""
        if self._busy:
            event.ignore()
            return
        self._worker_manager.cancel_all_workers()
        super().closeEvent(event)
