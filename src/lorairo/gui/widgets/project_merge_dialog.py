"""複数プロジェクトを画像・タグ・データセットの版履歴ごと統合するダイアログ (Issue #1660, ADR 0113)。

入口はファイルメニューの「プロジェクトを統合…」。流れは CLI の `lorairo-cli project merge` と同じ:

1. 統合元 (複数) と統合先 (既存のプロジェクト、または新しく作るプロジェクトの名前) を選ぶ。
2. 計画を worker で作り、取り込む画像の数・ハッシュ一致でまとめる画像の数・版の一覧・衝突を表示する。
3. 衝突ごとに名前の対応 (データセット名・版名の変更、版の履歴をまとめる指定) を指定する。
   指定を変えるたびに計画を作り直す。
4. 衝突が 0 件になったら「確定」で統合を worker で実行し、結果を表示する。

worker の終端は `WorkerManager` の queued な終端 signal (GUI スレッドで発行される) で受ける。
worker の signal を lambda で受けて GUI 側の signal を emit すると、lambda が worker スレッドで
実行されて GIL と signalSlotLock の ABBA デッドロックになり得る (#1492 / #1497)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...public_api.types import ProjectInfo
from ...services.project_management_service import ProjectManagementService
from ...services.project_merge_service import (
    MergeConflict,
    MergeMapping,
    MergePlan,
    PlannedDataset,
    PlannedVersion,
    SourceDatasetRef,
)
from ...services.project_transfer_service import SourceProject
from ...utils.log import logger
from .. import theme
from ..message_box import show_critical, show_information
from ..workers.manager import WorkerManager
from ..workers.project_merge_workers import (
    MergeApplyOutcome,
    MergeTarget,
    ProjectMergeApplyWorker,
    ProjectMergeListWorker,
    ProjectMergePlanWorker,
    validate_new_project_name,
)
from .ds_button import DsButton
from .ds_summary_stat import DsSummaryStat, ToneLiteral

_DATASET_HEADERS = ["統合元のデータセット", "統合先のデータセット", "版の数"]
_VERSION_HEADERS = ["統合元の版", "統合先のデータセット", "統合先の版", "parent", "状態", "画像"]
_COL_DATASET = 1
_COL_VERSION = 2
_CONFLICT_HEADERS = ["種類", "データセット", "版", "統合元", "説明"]
_CONFLICT_KIND_LABELS = {
    "dataset_name": "同名のデータセット",
    "dataset_exists": "統合先に同名のデータセット",
    "version_name": "同名の版",
    "multiple_working_versions": "作業中の版が複数",
    "cyclic_history": "版の親子関係が循環",
}
_TARGET_LABEL = "(統合先)"

_LIST_WORKER_PREFIX = "project_merge_list_"
_PLAN_WORKER_PREFIX = "project_merge_plan_"
_APPLY_WORKER_PREFIX = "project_merge_apply_"


def _parent_text(version: PlannedVersion) -> str:
    """版の parent の表示 (`プロジェクト:データセット/版`)。"""
    parent = version.parent
    if parent is None:
        return "-"
    owner = parent.source_project if parent.source_project is not None else _TARGET_LABEL
    joined = " (まとめる指定)" if version.joined_parent else ""
    return f"{owner}:{parent.dataset}/{parent.version}{joined}"


def _source_label(text: str) -> str:
    """衝突の統合元の表示 (統合先の既存のものは `(統合先)`)。"""
    return _TARGET_LABEL if text == "(target)" else text


@dataclass(frozen=True)
class ProjectMergeOutcome:
    """確定した統合 1 回分の、表示の更新に使う結果。

    Attributes:
        target_root: 統合先のプロジェクトのディレクトリ (resolve 済み)。
        image_ids: 統合先で取り込んだ画像と、ハッシュ一致でまとめた先の既存の画像の ID (昇順、重複なし)。
    """

    target_root: Path
    image_ids: tuple[int, ...]


class ProjectMergeDialog(QDialog):
    """統合元・統合先の選択、計画の表示、名前の対応の指定、統合の確定を行うダイアログ。"""

    # 統合が成功するたびに GUI スレッドで発行する (payload: ProjectMergeOutcome)。
    # ダイアログを開いたまま何回統合しても、受け手は 1 回ごとに表示を更新できる
    merge_succeeded = Signal(object)

    def __init__(
        self,
        project_service: ProjectManagementService,
        *,
        current_project_root: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを初期化し、プロジェクトの一覧の取得を始める。

        Args:
            project_service: プロジェクトの一覧・作成・削除に使う service。
            current_project_root: いま開いているプロジェクトのディレクトリ (統合先の既定値)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("プロジェクトを統合")
        self.setModal(True)
        self.resize(1040, 820)

        self._project_service = project_service
        self._current_project_root = current_project_root.resolve() if current_project_root else None
        self._projects: list[ProjectInfo] = []
        self._plan: MergePlan | None = None
        # 最後に計画を作れた名前の対応と、作成中の計画に使った名前の対応
        self._mapping = MergeMapping()
        self._requested_mapping = MergeMapping()
        self._plan_sources: list[SourceProject] = []
        self._plan_target: MergeTarget | None = None
        self._busy: str | None = None
        self._worker_serial = 0
        self._current_worker_id: str | None = None
        self._dataset_refs: dict[str, SourceDatasetRef] = {}
        self._stat_tiles: list[DsSummaryStat] = []

        self._worker_manager = WorkerManager(self)
        # GUI スレッドで発行される終端 signal を、このダイアログの Slot で受ける
        self._worker_manager.worker_finished.connect(self._on_worker_finished)
        self._worker_manager.worker_error.connect(self._on_worker_error)
        self._worker_manager.worker_canceled.connect(self._on_worker_canceled)

        self._build_ui()
        self._update_controls()
        self.load_projects()

    # --- 公開 API ---

    @property
    def current_plan(self) -> MergePlan | None:
        """表示中の計画 (選択を変えた後や、計画を作る前は None)。"""
        return self._plan

    @property
    def mapping(self) -> MergeMapping:
        """表示中の計画に使った名前の対応。"""
        return self._mapping

    @property
    def is_busy(self) -> bool:
        """一覧の取得・計画の作成・統合のいずれかを実行中なら True。"""
        return self._busy is not None

    def load_projects(self) -> None:
        """プロジェクトの一覧を worker で取得する。"""
        worker = ProjectMergeListWorker(self._project_service)
        self._start(_LIST_WORKER_PREFIX, "list", worker, "プロジェクトの一覧を読み込んでいます…")

    # --- UI の構築 ---

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_selection_group())
        layout.addWidget(self._build_plan_group(), 1)
        layout.addWidget(self._build_join_group())

        self.status_label = QLabel("", self)
        self.status_label.setObjectName("projectMergeStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.confirm_button = DsButton("確定", kind="primary", parent=self)
        self.confirm_button.setObjectName("projectMergeConfirm")
        self.confirm_button.clicked.connect(self._on_confirm_clicked)
        buttons.addWidget(self.confirm_button)
        self.close_button = DsButton("閉じる", kind="secondary", parent=self)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _build_selection_group(self) -> QGroupBox:
        group = QGroupBox("1. 統合元と統合先", self)
        layout = QVBoxLayout(group)
        layout.addWidget(
            QLabel(
                "統合元 (一覧の順に統合します。同じ画像は先の統合元にまとめます。統合元は変更しません)",
                group,
            )
        )
        self.source_list = QListWidget(group)
        self.source_list.setMaximumHeight(140)
        self.source_list.itemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.source_list)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("統合先:", group))
        self.existing_target_radio = QRadioButton("既存のプロジェクト", group)
        self.existing_target_radio.setChecked(True)
        self.existing_target_radio.toggled.connect(self._on_selection_changed)
        target_row.addWidget(self.existing_target_radio)
        self.target_combo = QComboBox(group)
        self.target_combo.currentIndexChanged.connect(self._on_selection_changed)
        target_row.addWidget(self.target_combo, 1)
        self.new_target_radio = QRadioButton("新しいプロジェクト", group)
        self.new_target_radio.toggled.connect(self._on_selection_changed)
        target_row.addWidget(self.new_target_radio)
        self.new_target_edit = QLineEdit(group)
        self.new_target_edit.setPlaceholderText("新しいプロジェクトの名前")
        self.new_target_edit.textChanged.connect(self._on_selection_changed)
        target_row.addWidget(self.new_target_edit, 1)
        layout.addLayout(target_row)

        plan_row = QHBoxLayout()
        self.selection_hint_label = QLabel("", group)
        self.selection_hint_label.setStyleSheet(f"color: {theme.INK_SOFT};")
        plan_row.addWidget(self.selection_hint_label, 1)
        self.plan_button = DsButton("計画を作成", kind="secondary", parent=group)
        self.plan_button.clicked.connect(self._on_plan_clicked)
        plan_row.addWidget(self.plan_button)
        layout.addLayout(plan_row)
        return group

    def _build_plan_group(self) -> QGroupBox:
        group = QGroupBox("2. 計画 (統合先のデータセット名と版名はダブルクリックで変更できます)", self)
        layout = QVBoxLayout(group)
        self._stats_row = QHBoxLayout()
        layout.addLayout(self._stats_row)
        self._set_stats(None)

        # 版を持たないデータセットも名前を変えられるよう、データセットの表を版の表と別に持つ
        self.dataset_table = QTableWidget(0, len(_DATASET_HEADERS), group)
        self.dataset_table.setHorizontalHeaderLabels(_DATASET_HEADERS)
        self.dataset_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dataset_table.verticalHeader().setVisible(False)
        self.dataset_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.dataset_table.itemChanged.connect(self._on_dataset_item_changed)
        layout.addWidget(self.dataset_table, 1)

        self.version_table = QTableWidget(0, len(_VERSION_HEADERS), group)
        self.version_table.setHorizontalHeaderLabels(_VERSION_HEADERS)
        self.version_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.version_table.verticalHeader().setVisible(False)
        self.version_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.version_table.itemChanged.connect(self._on_version_item_changed)
        layout.addWidget(self.version_table, 2)

        layout.addWidget(QLabel("衝突 (すべて解消すると確定できます)", group))
        self.conflict_table = QTableWidget(0, len(_CONFLICT_HEADERS), group)
        self.conflict_table.setHorizontalHeaderLabels(_CONFLICT_HEADERS)
        self.conflict_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.conflict_table.verticalHeader().setVisible(False)
        header = self.conflict_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        layout.addWidget(self.conflict_table, 1)
        return group

    def _build_join_group(self) -> QGroupBox:
        group = QGroupBox("3. 同じデータセットの版を 1 つの履歴にまとめる", self)
        layout = QHBoxLayout(group)

        left = QVBoxLayout()
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("統合先のデータセット名:", group))
        self.join_name_edit = QLineEdit(group)
        name_row.addWidget(self.join_name_edit, 1)
        left.addLayout(name_row)
        left.addWidget(QLabel("まとめるデータセット (チェックした順ではなく、一覧の上から連ねます)", group))
        self.join_source_list = QListWidget(group)
        self.join_source_list.setMaximumHeight(110)
        left.addWidget(self.join_source_list)
        move_row = QHBoxLayout()
        self.join_up_button = QPushButton("上へ", group)
        self.join_up_button.clicked.connect(self._on_join_up_clicked)
        move_row.addWidget(self.join_up_button)
        self.join_down_button = QPushButton("下へ", group)
        self.join_down_button.clicked.connect(self._on_join_down_clicked)
        move_row.addWidget(self.join_down_button)
        move_row.addStretch(1)
        self.add_join_button = QPushButton("まとめる指定を追加", group)
        self.add_join_button.clicked.connect(self._on_add_join_clicked)
        move_row.addWidget(self.add_join_button)
        left.addLayout(move_row)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("指定済みのまとめ", group))
        self.join_list = QListWidget(group)
        self.join_list.setMaximumHeight(110)
        right.addWidget(self.join_list)
        self.remove_join_button = QPushButton("指定を外す", group)
        self.remove_join_button.clicked.connect(self._on_remove_join_clicked)
        right.addWidget(self.remove_join_button)
        layout.addLayout(right, 1)
        return group

    # --- 選択 ---

    def _selected_target(self) -> MergeTarget | None:
        if self.new_target_radio.isChecked():
            name = self.new_target_edit.text().strip()
            if not name or any(project.name == name for project in self._projects):
                return None
            try:
                validate_new_project_name(name)
            except ValueError:
                return None
            return MergeTarget(name=name, root=None)
        index = self.target_combo.currentIndex()
        if index < 0 or index >= len(self._projects):
            return None
        project = self._projects[index]
        return MergeTarget(name=project.name, root=project.path.resolve())

    def _selected_sources(self) -> list[SourceProject]:
        sources: list[SourceProject] = []
        for row in range(self.source_list.count()):
            item = self.source_list.item(row)
            enabled = bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
            if enabled and item.checkState() == Qt.CheckState.Checked:
                project = self._projects[row]
                sources.append(SourceProject(name=project.name, root=project.path))
        return sources

    def _selection_hint(self, sources: list[SourceProject], target: MergeTarget | None) -> str:
        if self.new_target_radio.isChecked():
            name = self.new_target_edit.text().strip()
            if not name:
                return "新しいプロジェクトの名前を入力してください"
            try:
                validate_new_project_name(name)
            except ValueError as e:
                return str(e)
            if target is None:
                return f"プロジェクト '{name}' は既にあります。別の名前にするか、既存のプロジェクトを選んでください"
        elif target is None:
            return "統合先のプロジェクトを選んでください"
        if not sources:
            return "統合元のプロジェクトを 1 つ以上選んでください"
        return ""

    @Slot()
    def _on_selection_changed(self) -> None:
        """統合元・統合先が変わったら、統合先を統合元から外し、計画と名前の対応を捨てる。"""
        self._sync_target_exclusion()
        self._plan = None
        self._mapping = MergeMapping()
        self._requested_mapping = MergeMapping()
        self._render_plan()
        self._update_controls()

    def _sync_target_exclusion(self) -> None:
        """統合先にしたプロジェクトを、統合元の一覧で選べなくする。"""
        target = self._selected_target()
        target_root = target.root if target is not None else None
        self.source_list.blockSignals(True)
        try:
            for row in range(self.source_list.count()):
                item = self.source_list.item(row)
                is_target = target_root is not None and self._projects[row].path.resolve() == target_root
                flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
                if is_target:
                    item.setCheckState(Qt.CheckState.Unchecked)
                    item.setToolTip("統合先のプロジェクトは統合元にできません")
                else:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                    item.setToolTip("")
                item.setFlags(flags)
        finally:
            self.source_list.blockSignals(False)

    # --- 計画 ---

    @Slot()
    def _on_plan_clicked(self) -> None:
        self._request_plan(self._mapping)

    def _request_plan(self, mapping: MergeMapping) -> None:
        sources = self._selected_sources()
        target = self._selected_target()
        if not sources or target is None or self._busy is not None:
            return
        self._plan_sources = sources
        self._plan_target = target
        self._requested_mapping = mapping
        worker = ProjectMergePlanWorker(sources, mapping, target)
        self._start(_PLAN_WORKER_PREFIX, "plan", worker, "計画を作っています (何も書き込みません)…")

    def _set_plan(self, plan: MergePlan) -> None:
        self._plan = plan
        self._mapping = self._requested_mapping
        self._render_plan()
        if plan.is_resolved:
            self._set_status("衝突はありません。「確定」で統合します。", tone=None)
        else:
            self._set_status(
                f"衝突が {len(plan.conflicts)} 件あります。名前の対応を指定してください。", tone="warn"
            )

    def _render_plan(self) -> None:
        """表示中の計画 (無ければ空) で件数・版・衝突・まとめる指定を描き直す。"""
        plan = self._plan
        self._set_stats(plan)
        self._render_datasets(plan.datasets if plan is not None else ())
        self._render_versions(plan.versions if plan is not None else ())
        self._render_conflicts(plan.conflicts if plan is not None else ())
        self._render_joins(plan)

    def _set_stats(self, plan: MergePlan | None) -> None:
        # DsSummaryStat は表示値を差し替える API を持たないため、計画ごとに作り直す
        for tile in self._stat_tiles:
            self._stats_row.removeWidget(tile)
            tile.deleteLater()
        stats: list[tuple[str, str, str, ToneLiteral | None]] = [
            ("projectMergeStatImages", "取り込む画像", "—", None),
            ("projectMergeStatDuplicates", "ハッシュ一致でまとめる画像", "—", None),
            ("projectMergeStatVersions", "版", "—", None),
            ("projectMergeStatConflicts", "衝突", "—", None),
        ]
        if plan is not None:
            conflicts = len(plan.conflicts)
            stats = [
                ("projectMergeStatImages", "取り込む画像", f"{plan.image_count:,}", None),
                (
                    "projectMergeStatDuplicates",
                    "ハッシュ一致でまとめる画像",
                    f"{len(plan.duplicates):,}",
                    "info",
                ),
                ("projectMergeStatVersions", "版", f"{len(plan.versions):,}", None),
                ("projectMergeStatConflicts", "衝突", f"{conflicts:,}", "err" if conflicts else "ok"),
            ]
        self._stat_tiles = []
        for object_name, label, value, tone in stats:
            tile = DsSummaryStat(label=label, value=value, tone=tone, parent=self)
            tile.setObjectName(object_name)
            self._stats_row.addWidget(tile)
            self._stat_tiles.append(tile)

    def _render_versions(self, versions: tuple[PlannedVersion, ...]) -> None:
        table = self.version_table
        table.blockSignals(True)
        try:
            table.setRowCount(len(versions))
            for row, version in enumerate(versions):
                values = [
                    version.source.label,
                    version.target_dataset,
                    version.target_version,
                    _parent_text(version),
                    "作業中" if version.is_working else "確定",
                    str(version.image_count),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    if column in (_COL_DATASET, _COL_VERSION):
                        flags |= Qt.ItemFlag.ItemIsEditable
                    item.setFlags(flags)
                    table.setItem(row, column, item)
        finally:
            table.blockSignals(False)

    def _render_conflicts(self, conflicts: tuple[MergeConflict, ...]) -> None:
        table = self.conflict_table
        table.setRowCount(len(conflicts))
        for row, conflict in enumerate(conflicts):
            values = [
                _CONFLICT_KIND_LABELS.get(conflict.kind, conflict.kind),
                conflict.target_dataset,
                conflict.target_version or "-",
                ", ".join(_source_label(source) for source in conflict.sources),
                conflict.message,
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))

    def _render_datasets(self, datasets: tuple[PlannedDataset, ...]) -> None:
        table = self.dataset_table
        table.blockSignals(True)
        try:
            table.setRowCount(len(datasets))
            for row, dataset in enumerate(datasets):
                values = [dataset.source.label, dataset.target_dataset, str(dataset.version_count)]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    if column == 1:
                        flags |= Qt.ItemFlag.ItemIsEditable
                    item.setFlags(flags)
                    table.setItem(row, column, item)
        finally:
            table.blockSignals(False)

    def _render_joins(self, plan: MergePlan | None) -> None:
        self.join_source_list.clear()
        self._dataset_refs = {}
        if plan is not None:
            # 版を持たないデータセットも含めて、統合元のデータセットを選択肢にする
            for dataset in plan.datasets:
                ref = dataset.source
                if ref.label in self._dataset_refs:
                    continue
                self._dataset_refs[ref.label] = ref
                item = QListWidgetItem(ref.label, self.join_source_list)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
        self.join_list.clear()
        for name, refs in self._mapping.joins.items():
            item = QListWidgetItem(f"{name} ← " + " → ".join(ref.label for ref in refs), self.join_list)
            item.setData(Qt.ItemDataRole.UserRole, name)

    # --- 名前の対応の指定 ---

    @Slot(QTableWidgetItem)
    def _on_dataset_item_changed(self, item: QTableWidgetItem) -> None:
        """統合先のデータセット名の変更を名前の対応にして、計画を作り直す。"""
        plan = self._plan
        if plan is None or self._busy is not None or item.row() >= len(plan.datasets):
            return
        dataset = plan.datasets[item.row()]
        text = item.text().strip()
        if item.column() != 1 or not text or text == dataset.target_dataset:
            # 空・変更なしは元の表示に戻す
            self._render_datasets(plan.datasets)
            return
        self._request_plan(self._mapping.updated(MergeMapping(dataset_names={dataset.source: text})))

    @Slot(QTableWidgetItem)
    def _on_version_item_changed(self, item: QTableWidgetItem) -> None:
        """統合先のデータセット名・版名の変更を名前の対応にして、計画を作り直す。"""
        plan = self._plan
        if plan is None or self._busy is not None or item.row() >= len(plan.versions):
            return
        version = plan.versions[item.row()]
        text = item.text().strip()
        mapping: MergeMapping | None = None
        if item.column() == _COL_DATASET and text and text != version.target_dataset:
            ref = SourceDatasetRef(version.source.project, version.source.dataset)
            mapping = self._mapping.updated(MergeMapping(dataset_names={ref: text}))
        elif item.column() == _COL_VERSION and text and text != version.target_version:
            mapping = self._mapping.updated(MergeMapping(version_names={version.source: text}))
        if mapping is None:
            # 空・変更なしは元の表示に戻す
            self._render_versions(plan.versions)
            return
        self._request_plan(mapping)

    def _move_join_source(self, offset: int) -> None:
        row = self.join_source_list.currentRow()
        new_row = row + offset
        if row < 0 or not 0 <= new_row < self.join_source_list.count():
            return
        item = self.join_source_list.takeItem(row)
        self.join_source_list.insertItem(new_row, item)
        self.join_source_list.setCurrentRow(new_row)

    @Slot()
    def _on_join_up_clicked(self) -> None:
        self._move_join_source(-1)

    @Slot()
    def _on_join_down_clicked(self) -> None:
        self._move_join_source(1)

    @Slot()
    def _on_add_join_clicked(self) -> None:
        """チェックしたデータセットを、一覧の順に 1 つの履歴にまとめる指定を足す。"""
        name = self.join_name_edit.text().strip()
        refs = [
            self._dataset_refs[item.text()]
            for item in (self.join_source_list.item(row) for row in range(self.join_source_list.count()))
            if item.checkState() == Qt.CheckState.Checked and item.text() in self._dataset_refs
        ]
        if not name or not refs:
            self._set_status(
                "まとめる先のデータセット名と、まとめるデータセットを指定してください", tone="warn"
            )
            return
        joins = {**self._mapping.joins, name: refs}
        self._request_plan(
            MergeMapping(
                dataset_names=dict(self._mapping.dataset_names),
                version_names=dict(self._mapping.version_names),
                joins=joins,
            )
        )

    @Slot()
    def _on_remove_join_clicked(self) -> None:
        item = self.join_list.currentItem()
        if item is None:
            return
        name = str(item.data(Qt.ItemDataRole.UserRole))
        joins = {key: refs for key, refs in self._mapping.joins.items() if key != name}
        self._request_plan(
            MergeMapping(
                dataset_names=dict(self._mapping.dataset_names),
                version_names=dict(self._mapping.version_names),
                joins=joins,
            )
        )

    # --- 確定 ---

    @Slot()
    def _on_confirm_clicked(self) -> None:
        plan = self._plan
        if plan is None or not plan.is_resolved or self._busy is not None or self._plan_target is None:
            return
        worker = ProjectMergeApplyWorker(
            self._plan_sources, self._mapping, self._plan_target, self._project_service
        )
        self._start(_APPLY_WORKER_PREFIX, "apply", worker, "統合しています…")

    def _on_applied(self, outcome: MergeApplyOutcome) -> None:
        result = outcome.result
        message = (
            f"{len(result.plan.source_projects)} 個のプロジェクトを '{result.plan.target_project}' へ統合しました: "
            f"画像 {result.plan.image_count:,} 枚 (ハッシュ一致でまとめた画像 {len(result.plan.duplicates):,} 枚)、"
            f"版 {len(result.version_ids):,} 個"
        )
        logger.info(message)
        # 統合済みの計画は再び確定できない (統合先に同名のデータセットができている) ので捨てる
        self._plan = None
        self._mapping = MergeMapping()
        self._requested_mapping = MergeMapping()
        self._render_plan()
        self._set_status(message, tone="ok")
        # まとめた画像は既存の画像 ID を指す (ID が変わらないので、受け手が明示的に読み直す)
        self.merge_succeeded.emit(
            ProjectMergeOutcome(
                target_root=outcome.target_root.resolve(),
                image_ids=tuple(sorted(set(result.image_ids.values()))),
            )
        )
        show_information(self, "プロジェクトを統合しました", message)
        if self._plan_target is not None and self._plan_target.is_new:
            # 作ったプロジェクトを一覧に出す
            self.load_projects()

    # --- worker ---

    def _start(
        self,
        prefix: str,
        task: str,
        worker: ProjectMergeListWorker | ProjectMergePlanWorker | ProjectMergeApplyWorker,
        status: str,
    ) -> None:
        self._worker_serial += 1
        worker_id = f"{prefix}{self._worker_serial}"
        self._current_worker_id = worker_id
        self._busy = task
        self._set_status(status, tone=None)
        self._update_controls()
        if not self._worker_manager.start_worker(worker_id, worker):
            self._busy = None
            self._current_worker_id = None
            self._update_controls()

    def _finish(self, worker_id: str) -> str | None:
        """自分が起動した最新の worker の終端なら、その種類を返して実行中を解除する。"""
        if worker_id != self._current_worker_id:
            return None
        task = self._busy
        self._busy = None
        self._current_worker_id = None
        return task

    @Slot(str, object)
    def _on_worker_finished(self, worker_id: str, result: object) -> None:
        task = self._finish(worker_id)
        if task == "list" and isinstance(result, list):
            self._set_projects([project for project in result if isinstance(project, ProjectInfo)])
            self._set_status("", tone=None)
        elif task == "plan" and isinstance(result, MergePlan):
            self._set_plan(result)
        elif task == "apply" and isinstance(result, MergeApplyOutcome):
            self._on_applied(result)
        self._update_controls()

    @Slot(str, str)
    def _on_worker_error(self, worker_id: str, message: str) -> None:
        task = self._finish(worker_id)
        if task is None:
            return
        if task == "plan":
            # 名前の対応の指定が通らなかったら、最後に計画を作れた対応の表示に戻す
            self._requested_mapping = self._mapping
            self._render_plan()
            self._set_status(f"計画を作れませんでした: {message}", tone="err")
        elif task == "apply":
            self._set_status(f"統合に失敗しました。統合先は変更していません: {message}", tone="err")
            show_critical(
                self, "プロジェクトを統合できませんでした", f"統合先は変更していません。\n{message}"
            )
        else:
            self._set_status(f"プロジェクトの一覧を読み込めませんでした: {message}", tone="err")
        self._update_controls()

    @Slot(str)
    def _on_worker_canceled(self, worker_id: str) -> None:
        if self._finish(worker_id) is not None:
            self._set_status("中止しました", tone=None)
            self._update_controls()

    def _set_projects(self, projects: list[ProjectInfo]) -> None:
        previous = self._selected_target()
        self._projects = projects
        widgets = (self.source_list, self.target_combo)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.source_list.clear()
            self.target_combo.clear()
            default_index = -1
            for index, project in enumerate(projects):
                item = QListWidgetItem(f"{project.name}  ({project.path})", self.source_list)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.target_combo.addItem(project.name)
                root = project.path.resolve()
                if previous is not None and previous.root == root:
                    default_index = index
                elif default_index < 0 and root == self._current_project_root:
                    default_index = index
            self.target_combo.setCurrentIndex(default_index if default_index >= 0 else 0)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._on_selection_changed()

    # --- 表示の状態 ---

    def _set_status(self, text: str, *, tone: ToneLiteral | None) -> None:
        colors = {"ok": theme.OK, "warn": theme.WARN, "err": theme.ERR, "info": theme.INFO}
        color = colors.get(tone, theme.INK) if tone is not None else theme.INK
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def _update_controls(self) -> None:
        idle = self._busy is None
        sources = self._selected_sources()
        target = self._selected_target()
        hint = self._selection_hint(sources, target)
        self.selection_hint_label.setText(hint)
        self.source_list.setEnabled(idle)
        self.existing_target_radio.setEnabled(idle)
        self.new_target_radio.setEnabled(idle)
        self.target_combo.setEnabled(idle and self.existing_target_radio.isChecked())
        self.new_target_edit.setEnabled(idle and self.new_target_radio.isChecked())
        self.plan_button.setEnabled(idle and not hint)
        has_plan = self._plan is not None
        editable = idle and has_plan
        triggers = (
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
            if editable
            else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.version_table.setEditTriggers(triggers)
        self.dataset_table.setEditTriggers(triggers)
        for widget in (
            self.join_name_edit,
            self.join_source_list,
            self.join_up_button,
            self.join_down_button,
            self.add_join_button,
            self.join_list,
            self.remove_join_button,
        ):
            widget.setEnabled(editable)
        resolved = self._plan is not None and self._plan.is_resolved
        self.confirm_button.setEnabled(idle and resolved)
        self.close_button.setEnabled(idle)

    # --- 閉じる ---

    def reject(self) -> None:
        """処理中は閉じない。閉じるときは残っている worker を止める。"""
        if self._busy is not None:
            return
        self._worker_manager.cancel_all_workers()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """処理中はウィンドウの閉じるボタンでも閉じない。"""
        if self._busy is not None:
            event.ignore()
            return
        self._worker_manager.cancel_all_workers()
        super().closeEvent(event)
