"""他のプロジェクトから画像を探し、現在のプロジェクトへコピーするダイアログ (Issue #1661, ADR 0112)。

入口は検索タブの「他のプロジェクトから探す…」ボタン。検索タブの現在のフィルタ条件で、選んだ
プロジェクトを読み取り専用で検索し、結果に出所 (プロジェクト名) と既にある由来を出す。
選んだ画像は、まず dry-run の計画 (複製 / 由来を足す / 記録済み の件数) を確認ダイアログで見せてから、
確定したときだけ現在のプロジェクトへコピーする。検索・計画・コピーは worker スレッドで行う
(`cross_project_workers`)。コピー元のプロジェクトは変更しない。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from ...database.filter_criteria import ImageFilterCriteria
from ...public_api.types import ProjectInfo
from ...services.project_management_service import ProjectManagementService
from ...services.project_transfer_service import (
    CrossProjectImageHit,
    ProjectSearchResult,
    ProjectTransferService,
    SourceProject,
)
from ...utils.log import logger
from ..message_box import show_information, show_warning
from ..workers.cross_project_workers import (
    TOO_MANY_RESULTS_REASON,
    CrossProjectCopyOutcome,
    CrossProjectCopyWorker,
    CrossProjectSearchWorker,
    ProjectListWorker,
)
from ..workers.manager import WorkerManager
from .ds_button import DsButton
from .ds_card import DsCard
from .ds_summary_stat import DsSummaryStat
from .image_origin_widget import ImageOriginEntry, format_origins

_RESULT_HEADERS = ["プロジェクト", "画像 ID", "ファイル名", "サイズ", "由来"]
_REASON_TEXT = {
    "schema_upgrade_required": "DB の更新が必要 (project prepare で更新してください)",
    TOO_MANY_RESULTS_REASON: "一致件数が多すぎるため取得していません (条件を絞ってください)",
}


class CrossProjectCopyConfirmDialog(QDialog):
    """コピーの計画 (dry-run の結果) を見せて、実行するかを確かめるダイアログ。"""

    def __init__(self, outcome: CrossProjectCopyOutcome, target_name: str, parent: QWidget | None = None):
        """計画の件数をタイルで並べる。

        Args:
            outcome: dry-run の結果。
            target_name: 取り込み先 (現在のプロジェクト) の名前。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("現在のプロジェクトへコピー")
        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(f"選んだ画像を「{target_name}」へコピーします。何も書き込む前の計画です。", self)
        )

        stats = QHBoxLayout()
        self.copy_stat = DsSummaryStat("複製する", str(outcome.count("copy")), "新しい画像として", "accent")
        self.link_stat = DsSummaryStat(
            "由来を足す", str(outcome.count("link")), "同じ画像が既にある", "info"
        )
        self.already_stat = DsSummaryStat(
            "記録済み", str(outcome.count("already_linked")), "足りない注釈だけ足す", None
        )
        for stat in (self.copy_stat, self.link_stat, self.already_stat):
            stats.addWidget(stat)
        root.addLayout(stats)

        lines = [
            f"{result.source_project_name}: {len(result.items)} 枚 "
            f"(複製 {result.count('copy')} / 由来 {result.count('link')} / "
            f"記録済み {result.count('already_linked')})"
            for result in outcome.results
        ]
        lines.extend(
            f"{failure.project_name}: 計画を作れません ({failure.message})" for failure in outcome.failures
        )
        detail = QLabel("\n".join(lines), self)
        detail.setWordWrap(True)
        root.addWidget(detail)
        root.addWidget(QLabel("コピー元のプロジェクトは変更しません。", self))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = DsButton("キャンセル", kind="secondary", parent=self)
        cancel.clicked.connect(self.reject)
        self.confirm_button = DsButton("コピーする", kind="primary", parent=self)
        self.confirm_button.setEnabled(bool(outcome.results) and any(r.items for r in outcome.results))
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm_button)
        root.addLayout(buttons)


def confirm_copy_plan(parent: QWidget | None, outcome: CrossProjectCopyOutcome, target_name: str) -> bool:
    """コピーの計画を確認ダイアログで見せ、実行してよいかを返す (テストはこの関数を差し替える)。"""
    dialog = CrossProjectCopyConfirmDialog(outcome, target_name, parent)
    return dialog.exec() == QDialog.DialogCode.Accepted


class CrossProjectSearchDialog(QDialog):
    """他のプロジェクトの検索と、選んだ画像の現在のプロジェクトへのコピー。

    Signals:
        images_copied (list): コピー (または由来の追加) をした取り込み先の画像 ID。
    """

    images_copied = Signal(list)

    # worker スレッドから GUI スレッドへ結果を渡す (受け手はダイアログ = GUI スレッド)
    _projects_loaded = Signal(object)
    _search_finished = Signal(object)
    _copy_planned = Signal(object)
    _copy_finished = Signal(object)
    _task_failed = Signal(str, str)

    def __init__(
        self,
        *,
        project_service: ProjectManagementService,
        target_root: Path,
        target_session_factory: Callable[[], Session],
        criteria_factory: Callable[[], ImageFilterCriteria],
        criteria_text: str,
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを初期化し、プロジェクトの一覧の取得を始める。

        Args:
            project_service: プロジェクト一覧の取得に使う service。
            target_root: 現在のプロジェクト (取り込み先) のディレクトリ。
            target_session_factory: 現在のプロジェクトの DB のセッションファクトリ (書き込み可)。
            criteria_factory: 検索条件を作る callable (worker で呼ぶ)。
            criteria_text: 検索条件の表示文。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("他のプロジェクトから探す")
        self.resize(900, 620)
        self._project_service = project_service
        self._target_root = target_root.resolve()
        self._target_name = self._target_root.name
        self._target_session_factory = target_session_factory
        self._criteria_factory = criteria_factory
        self._sources: dict[str, SourceProject] = {}
        self._hits: list[CrossProjectImageHit] = []
        self._pending_groups: list[tuple[SourceProject, list[int]]] = []
        self._busy = False
        self._worker_manager = WorkerManager(self)

        self._build_ui(criteria_text)
        self._projects_loaded.connect(self._on_projects_loaded)
        self._search_finished.connect(self._on_search_finished)
        self._copy_planned.connect(self._on_copy_planned)
        self._copy_finished.connect(self._on_copy_finished)
        self._task_failed.connect(self._on_task_failed)
        self.load_projects()

    # --- UI ---

    def _build_ui(self, criteria_text: str) -> None:
        root = QVBoxLayout(self)

        criteria_card = DsCard("検索条件 (検索タブの現在のフィルタ)", parent=self)
        self.criteria_label = QLabel(criteria_text, criteria_card)
        self.criteria_label.setWordWrap(True)
        criteria_card.add_widget(self.criteria_label)
        note = QLabel(
            "縦横比・重複の除外・要確認の絞り込みは、他のプロジェクトの検索では使いません。"
            " 他のプロジェクトは読み取り専用で開き、変更しません。",
            criteria_card,
        )
        note.setWordWrap(True)
        criteria_card.add_widget(note)
        root.addWidget(criteria_card)

        self.search_button = DsButton("検索", kind="primary", size="small", parent=self)
        self.search_button.setObjectName("crossProjectSearchButton")
        self.search_button.clicked.connect(self.start_search)
        project_card = DsCard("検索するプロジェクト", aside=self.search_button, parent=self)
        self.project_list = QListWidget(project_card)
        self.project_list.setObjectName("crossProjectProjectList")
        self.project_list.setMaximumHeight(140)
        self.project_list.itemChanged.connect(lambda _item: self._update_buttons())
        project_card.add_widget(self.project_list)
        root.addWidget(project_card)

        self.result_table = QTableWidget(0, len(_RESULT_HEADERS), self)
        self.result_table.setObjectName("crossProjectResultTable")
        self.result_table.setHorizontalHeaderLabels(_RESULT_HEADERS)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.itemSelectionChanged.connect(self._update_buttons)
        root.addWidget(self.result_table, 1)

        self.skipped_label = QLabel(self)
        self.skipped_label.setWordWrap(True)
        self.skipped_label.setVisible(False)
        root.addWidget(self.skipped_label)

        bottom = QHBoxLayout()
        self.status_label = QLabel(self)
        bottom.addWidget(self.status_label, 1)
        self.copy_button = DsButton("選んだ画像を現在のプロジェクトへコピー…", kind="primary", parent=self)
        self.copy_button.setObjectName("crossProjectCopyButton")
        self.copy_button.clicked.connect(self.start_copy)
        self.close_button = DsButton("閉じる", kind="secondary", parent=self)
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.close_button)
        root.addLayout(bottom)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.search_button.setEnabled(not self._busy and bool(self.checked_project_names()))
        self.copy_button.setEnabled(not self._busy and bool(self.selected_hits()))
        self.close_button.setEnabled(not self._busy)

    def _set_busy(self, busy: bool, status_text: str | None = None) -> None:
        self._busy = busy
        if status_text is not None:
            self.status_label.setText(status_text)
        self._update_buttons()

    # --- プロジェクトの一覧 ---

    def load_projects(self) -> None:
        """プロジェクトの一覧を背景で取得する。"""
        self._set_busy(True, "プロジェクトの一覧を読み込み中...")
        worker = ProjectListWorker(self._project_service)
        # 以下の lambda は worker スレッドで走るが Signal を emit するだけ (スレッド安全)
        worker.finished.connect(lambda result: self._projects_loaded.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("list", str(message)))
        self._worker_manager.start_worker("cross_project_list", worker)

    @Slot(object)
    def _on_projects_loaded(self, projects: object) -> None:
        infos = [p for p in projects if isinstance(p, ProjectInfo)] if isinstance(projects, list) else []
        self._sources = {}
        self.project_list.blockSignals(True)
        self.project_list.clear()
        for info in infos:
            root = Path(info.path).resolve()
            if root == self._target_root:
                # 現在のプロジェクトは検索対象にしない (名前は由来の記録に使う)
                self._target_name = info.name
                continue
            self._sources[info.name] = SourceProject(name=info.name, root=root)
            item = QListWidgetItem(info.name, self.project_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setToolTip(str(root))
        self.project_list.blockSignals(False)
        self._set_busy(
            False,
            f"{len(self._sources)} 件のプロジェクト" if self._sources else "ほかのプロジェクトがありません",
        )

    def checked_project_names(self) -> list[str]:
        """チェックしたプロジェクトの名前 (一覧の順)。"""
        names: list[str] = []
        for row in range(self.project_list.count()):
            item = self.project_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.text())
        return names

    def set_project_checked(self, name: str, checked: bool = True) -> None:
        """プロジェクトのチェックを切り替える。"""
        for row in range(self.project_list.count()):
            item = self.project_list.item(row)
            if item.text() == name:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    @property
    def target_name(self) -> str:
        """取り込み先 (現在のプロジェクト) の名前。"""
        return self._target_name

    # --- 検索 ---

    @Slot()
    def start_search(self) -> None:
        """チェックしたプロジェクトを現在の条件で検索する。"""
        projects = [self._sources[name] for name in self.checked_project_names() if name in self._sources]
        if self._busy or not projects:
            return
        self._set_busy(True, f"{len(projects)} 件のプロジェクトを検索中...")
        worker = CrossProjectSearchWorker(projects, self._criteria_factory)
        worker.finished.connect(lambda result: self._search_finished.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("search", str(message)))
        self._worker_manager.start_worker("cross_project_search", worker)

    @Slot(object)
    def _on_search_finished(self, results: object) -> None:
        rows = (
            [r for r in results if isinstance(r, ProjectSearchResult)] if isinstance(results, list) else []
        )
        self._hits = [hit for result in rows for hit in result.hits]
        self.result_table.blockSignals(True)
        self.result_table.clearSelection()
        self.result_table.setRowCount(len(self._hits))
        for row, hit in enumerate(self._hits):
            origins = [ImageOriginEntry(o.source_project_name, o.source_image_id) for o in hit.origins]
            values = [
                hit.project_name,
                str(hit.image_id),
                hit.filename or "-",
                f"{hit.width}x{hit.height}",
                format_origins(origins),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(str(hit.file_path))
                self.result_table.setItem(row, column, item)
        self.result_table.blockSignals(False)
        skipped = [
            f"{r.project_name}: {_REASON_TEXT.get(r.unavailable_reason, r.unavailable_reason)}"
            for r in rows
            if r.unavailable_reason is not None
        ]
        self.skipped_label.setText("検索できなかったプロジェクト\n" + "\n".join(skipped) if skipped else "")
        self.skipped_label.setVisible(bool(skipped))
        self._set_busy(False, f"{len(self._hits)} 枚が見つかりました ({len(rows)} プロジェクト)")

    def hits(self) -> list[CrossProjectImageHit]:
        """表示中の検索結果 (表の行の順)。"""
        return list(self._hits)

    def select_hits(self, rows: list[int]) -> None:
        """結果の行を選ぶ。"""
        self.result_table.clearSelection()
        model = self.result_table.selectionModel()
        for row in rows:
            index = self.result_table.model().index(row, 0)
            model.select(index, model.SelectionFlag.Select | model.SelectionFlag.Rows)

    def selected_hits(self) -> list[CrossProjectImageHit]:
        """選んだ結果 (表の行の順)。"""
        rows = sorted({index.row() for index in self.result_table.selectionModel().selectedRows()})
        return [self._hits[row] for row in rows if row < len(self._hits)]

    # --- コピー ---

    def _selected_groups(self) -> list[tuple[SourceProject, list[int]]]:
        """選んだ結果をコピー元ごとにまとめる (表の順)。"""
        grouped: dict[str, list[int]] = {}
        for hit in self.selected_hits():
            grouped.setdefault(hit.project_name, []).append(hit.image_id)
        return [(self._sources[name], ids) for name, ids in grouped.items() if name in self._sources]

    def _transfer_service(self) -> ProjectTransferService:
        return ProjectTransferService(self._target_session_factory, self._target_root, self._target_name)

    @Slot()
    def start_copy(self) -> None:
        """選んだ画像のコピーの計画 (dry-run) を作る。確認ダイアログは計画ができてから出す。"""
        groups = self._selected_groups()
        if self._busy or not groups:
            return
        self._pending_groups = groups
        self._set_busy(True, "コピーの計画を作成中...")
        worker = CrossProjectCopyWorker(self._transfer_service(), groups, dry_run=True)
        worker.finished.connect(lambda result: self._copy_planned.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("plan", str(message)))
        self._worker_manager.start_worker("cross_project_copy_plan", worker)

    @Slot(object)
    def _on_copy_planned(self, outcome: object) -> None:
        self._set_busy(False)
        if not isinstance(outcome, CrossProjectCopyOutcome):
            return
        if not confirm_copy_plan(self, outcome, self._target_name):
            self.status_label.setText("コピーをキャンセルしました")
            return
        # 計画を作れたコピー元だけを実行する
        planned = {result.source_project_name for result in outcome.results}
        groups = [(source, ids) for source, ids in self._pending_groups if source.name in planned]
        if not groups:
            return
        self._set_busy(True, "現在のプロジェクトへコピー中...")
        worker = CrossProjectCopyWorker(self._transfer_service(), groups, dry_run=False)
        worker.finished.connect(lambda result: self._copy_finished.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("copy", str(message)))
        self._worker_manager.start_worker("cross_project_copy_apply", worker)

    @Slot(object)
    def _on_copy_finished(self, outcome: object) -> None:
        self._set_busy(False)
        if not isinstance(outcome, CrossProjectCopyOutcome):
            return
        summary = (
            f"複製 {outcome.count('copy')} 枚 / 由来を追加 {outcome.count('link')} 枚 / "
            f"記録済み {outcome.count('already_linked')} 枚"
        )
        self.status_label.setText(f"コピー完了: {summary}")
        logger.info(
            f"プロジェクト横断コピー (GUI) 完了: sources={len(outcome.results)}, "
            f"failures={len(outcome.failures)}, {summary}"
        )
        target_ids = outcome.target_image_ids()
        if target_ids:
            self.images_copied.emit(target_ids)
        if outcome.failures:
            lines = [f"{failure.project_name}: {failure.message}" for failure in outcome.failures]
            show_warning(
                self,
                "一部のプロジェクトからコピーできませんでした",
                f"{summary}\n\nコピーできなかったプロジェクト:\n" + "\n".join(lines),
            )
            return
        show_information(self, "コピー完了", f"「{self._target_name}」へ取り込みました。\n{summary}")

    # --- 失敗・終了 ---

    @Slot(str, str)
    def _on_task_failed(self, task: str, message: str) -> None:
        self._set_busy(False)
        titles = {
            "list": "プロジェクトの一覧を読み込めません",
            "search": "他のプロジェクトを検索できません",
            "plan": "コピーの計画を作れません",
            "copy": "コピーに失敗しました",
        }
        self.status_label.setText(titles.get(task, "失敗しました"))
        show_warning(self, titles.get(task, "エラー"), message)

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
