"""Kohya データセットの版を一覧し、Kohya-ss 形式で書き出すダイアログ (Issue #1456)。

入口はエクスポートタブの「Kohya 版を書き出す…」ボタン。版の一覧・版の詳細の取得と書き出しは
worker スレッドで行い、GUI をブロックしない (`kohya_version_workers`)。
書き出しは CLI の `lorairo-cli dataset export` と同じ `KohyaDatasetExportService` を使う。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...database.repository.dataset import (
    DatasetRepository,
    TagCopyResult,
    TagRevokeResult,
    TrainingConfigSnapshot,
    VersionSummary,
)
from ...services.kohya_dataset_export_service import KohyaExportResult
from ...utils.log import logger
from ..message_box import show_information, show_warning
from ..workers.kohya_version_workers import (
    KohyaVersionCopyTagsWorker,
    KohyaVersionDetail,
    KohyaVersionDetailWorker,
    KohyaVersionExportWorker,
    KohyaVersionListWorker,
    KohyaVersionRevokeTagsWorker,
)
from ..workers.manager import WorkerManager

_VERSION_HEADERS = ["データセット", "版", "版 ID", "親の版", "フォルダ", "画像", "作成日", "状態"]
_FOLDER_HEADERS = ["フォルダ", "繰り返し回数", "画像", "トリガーワード"]


def _unmapped_keys(config: TrainingConfigSnapshot) -> list[str]:
    """学習設定の未変換のキーを返す (読めない値は空とみなす)。"""
    try:
        loaded = json.loads(config.unmapped_json)
    except json.JSONDecodeError:
        return []
    return sorted(str(key) for key in loaded) if isinstance(loaded, dict) else []


class KohyaVersionExportDialog(QDialog):
    """データセットの版の一覧と、選んだ版の Kohya-ss 形式での書き出し。"""

    # タグの反映・取り消しで DB のタグ行が変化したときに親タブへ通知する
    tags_mutated = Signal()

    # worker スレッドから GUI スレッドへ結果を渡す (受け手はダイアログ = GUI スレッド)
    _versions_loaded = Signal(object)
    _detail_loaded = Signal(int, object)
    _export_finished = Signal(object)
    _copy_tags_previewed = Signal(object)
    _copy_tags_finished = Signal(object)
    _revoke_tags_previewed = Signal(object)
    _revoke_tags_finished = Signal(object)
    _task_failed = Signal(str, str)

    def __init__(self, repository: DatasetRepository, parent: QWidget | None = None) -> None:
        """ダイアログを初期化し、版の一覧の取得を始める。

        Args:
            repository: データセット Repository。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("Kohya 版の書き出し")
        self.resize(900, 560)
        self._repository = repository
        self._worker_manager = WorkerManager(self)
        self._versions: list[VersionSummary] = []
        self._detail: KohyaVersionDetail | None = None
        self._detail_generation = 0
        self._exporting = False
        self._pending_copy_scope: tuple[int, list[str] | None] | None = None
        self._pending_revoke_scope: tuple[int | None, list[str] | None] | None = None

        self._build_ui()
        self._versions_loaded.connect(self._on_versions_loaded)
        self._detail_loaded.connect(self._on_detail_loaded)
        self._export_finished.connect(self._on_export_finished)
        self._copy_tags_previewed.connect(self._on_copy_tags_previewed)
        self._copy_tags_finished.connect(self._on_copy_tags_finished)
        self._revoke_tags_previewed.connect(self._on_revoke_tags_previewed)
        self._revoke_tags_finished.connect(self._on_revoke_tags_finished)
        self._task_failed.connect(self._on_task_failed)
        self.load_versions()

    # --- UI ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.version_table = QTableWidget(0, len(_VERSION_HEADERS))
        self.version_table.setObjectName("kohyaVersionTable")
        self.version_table.setHorizontalHeaderLabels(_VERSION_HEADERS)
        self.version_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.version_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.version_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.version_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.version_table.itemSelectionChanged.connect(self._on_version_selection_changed)
        splitter.addWidget(self.version_table)

        self.folder_table = QTableWidget(0, len(_FOLDER_HEADERS))
        self.folder_table.setObjectName("kohyaFolderTable")
        self.folder_table.setHorizontalHeaderLabels(_FOLDER_HEADERS)
        self.folder_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.folder_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        splitter.addWidget(self.folder_table)
        root.addWidget(splitter, 1)

        form = QFormLayout()
        self.tag_folder_combo = QComboBox()
        self.tag_folder_combo.setObjectName("kohyaTagFolderCombo")
        self.tag_folder_combo.addItem("全フォルダ", None)
        self.tag_folder_combo.setEnabled(False)
        form.addRow("対象フォルダ", self.tag_folder_combo)

        self.config_combo = QComboBox()
        self.config_combo.setObjectName("kohyaConfigCombo")
        self.config_combo.currentIndexChanged.connect(self._update_unmapped_warning)
        form.addRow("学習設定", self.config_combo)

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("kohyaOutputDirEdit")
        self.output_dir_edit.setPlaceholderText("存在しないか空のディレクトリ")
        self.output_dir_edit.textChanged.connect(self._update_export_enabled)
        browse_button = QPushButton("参照…")
        browse_button.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(browse_button)
        form.addRow("書き出し先", output_row)
        root.addLayout(form)

        self.unmapped_label = QLabel()
        self.unmapped_label.setObjectName("kohyaUnmappedLabel")
        self.unmapped_label.setWordWrap(True)
        self.unmapped_label.setVisible(False)
        root.addWidget(self.unmapped_label)

        self.status_label = QLabel()
        self.status_label.setObjectName("kohyaStatusLabel")
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.copy_tags_button = QPushButton("学習テキストをタグへ写す")
        self.copy_tags_button.setObjectName("kohyaCopyTagsButton")
        self.copy_tags_button.setEnabled(False)
        self.copy_tags_button.clicked.connect(self._on_copy_tags_clicked)
        self.revoke_tags_button = QPushButton("プロジェクト全体の写したタグを取り消す")
        self.revoke_tags_button.setObjectName("kohyaRevokeTagsButton")
        self.revoke_tags_button.setToolTip(
            "版が未選択のため、プロジェクト全体の Kohya データセット タグを取り消す"
        )
        self.revoke_tags_button.clicked.connect(self._on_revoke_tags_clicked)
        self.commit_working_button = QPushButton("作業版を確定")
        self.commit_working_button.setObjectName("kohyaCommitWorkingButton")
        self.commit_working_button.setEnabled(False)
        self.commit_working_button.clicked.connect(self._on_commit_working_clicked)
        self.discard_working_button = QPushButton("作業版を破棄")
        self.discard_working_button.setObjectName("kohyaDiscardWorkingButton")
        self.discard_working_button.setEnabled(False)
        self.discard_working_button.clicked.connect(self._on_discard_working_clicked)
        buttons.addWidget(self.copy_tags_button)
        buttons.addWidget(self.revoke_tags_button)
        buttons.addWidget(self.commit_working_button)
        buttons.addWidget(self.discard_working_button)
        buttons.addStretch(1)
        self.export_button = QPushButton("書き出す")
        self.export_button.setObjectName("kohyaExportButton")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export_clicked)
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.export_button)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)

    # --- 版の一覧 ---

    def load_versions(self) -> None:
        """版の一覧を背景で取得する。"""
        self.status_label.setText("版の一覧を読み込み中...")
        worker = KohyaVersionListWorker(self._repository)
        # 以下の lambda は worker スレッドで走るが Signal を emit するだけ (スレッド安全)
        worker.finished.connect(lambda result: self._versions_loaded.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("list", str(message)))
        self._worker_manager.start_worker("kohya_version_list", worker)

    @Slot(object)
    def _on_versions_loaded(self, versions: object) -> None:
        self._versions = (
            [v for v in versions if isinstance(v, VersionSummary)] if isinstance(versions, list) else []
        )
        self.version_table.setRowCount(len(self._versions))
        for row, version in enumerate(self._versions):
            created = version.created_at.strftime("%Y-%m-%d %H:%M") if version.created_at else "-"
            status_text = "編集中" if getattr(version, "is_working", False) else "確定済"
            values = [
                version.dataset_name,
                version.version_name,
                str(version.version_id),
                str(version.parent_version_id) if version.parent_version_id is not None else "-",
                str(version.folder_count),
                str(version.image_count),
                created,
                status_text,
            ]
            for column, value in enumerate(values):
                self.version_table.setItem(row, column, QTableWidgetItem(value))
        self.status_label.setText(
            f"{len(self._versions)} 件の版" if self._versions else "取り込んだデータセットの版がありません"
        )
        self._update_export_enabled()

    def selected_version(self) -> VersionSummary | None:
        """選択中の版を返す。"""
        rows = self.version_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        return self._versions[row] if 0 <= row < len(self._versions) else None

    # --- 版の詳細 ---

    @Slot()
    def _on_version_selection_changed(self) -> None:
        version = self.selected_version()
        self._detail = None
        self.folder_table.setRowCount(0)
        self.config_combo.clear()
        self.tag_folder_combo.clear()
        self.tag_folder_combo.addItem("全フォルダ", None)
        self.tag_folder_combo.setEnabled(False)
        self._update_export_enabled()
        if version is None:
            return
        self._detail_generation += 1
        generation = self._detail_generation
        self.status_label.setText(f"版 {version.version_id} を読み込み中...")
        worker = KohyaVersionDetailWorker(self._repository, version.version_id, version.dataset_id)
        worker.finished.connect(lambda result, gen=generation: self._detail_loaded.emit(gen, result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("detail", str(message)))
        self._worker_manager.start_worker(f"kohya_version_detail_{generation}", worker)

    @Slot(int, object)
    def _on_detail_loaded(self, generation: int, detail: object) -> None:
        # 選択を切り替えた後に届いた古い結果は捨てる
        if generation != self._detail_generation or not isinstance(detail, KohyaVersionDetail):
            return
        self._detail = detail
        folders = detail.snapshot.folders
        self.folder_table.setRowCount(len(folders))
        for row, folder in enumerate(folders):
            values = [
                folder.dir_name,
                str(folder.num_repeats),
                str(len(folder.images)),
                folder.trigger_word or "-",
            ]
            for column, value in enumerate(values):
                self.folder_table.setItem(row, column, QTableWidgetItem(value))

        self.tag_folder_combo.blockSignals(True)
        self.tag_folder_combo.clear()
        self.tag_folder_combo.addItem("全フォルダ", None)
        for folder in folders:
            self.tag_folder_combo.addItem(folder.dir_name, folder.dir_name)
        self.tag_folder_combo.setEnabled(not self._exporting)
        self.tag_folder_combo.blockSignals(False)

        self.config_combo.blockSignals(True)
        self.config_combo.clear()
        self.config_combo.addItem("学習設定を書き出さない", None)
        for config in detail.training_configs:
            label = f"#{config.id} {config.source_file_name}"
            if config.version_id == detail.version_id:
                label += " (この版)"
            self.config_combo.addItem(label, config.id)
        self.config_combo.blockSignals(False)
        self._update_unmapped_warning()
        selected = self.selected_version()
        is_working = bool(
            getattr(detail.snapshot, "is_working", False)
            or (selected is not None and getattr(selected, "is_working", False))
        )
        state_label = "編集中" if is_working else "確定済"
        self.status_label.setText(
            f"{detail.snapshot.dataset_name} / {detail.snapshot.version_name} ({state_label}): "
            f"{len(folders)} フォルダ、学習設定 {len(detail.training_configs)} 件"
        )
        self._update_export_enabled()

    def _selected_tag_dir_names(self) -> list[str] | None:
        folder_name = self.tag_folder_combo.currentData()
        return [str(folder_name)] if isinstance(folder_name, str) and folder_name else None

    def _selected_config(self) -> TrainingConfigSnapshot | None:
        config_id = self.config_combo.currentData()
        if self._detail is None or config_id is None:
            return None
        return next((c for c in self._detail.training_configs if c.id == config_id), None)

    @Slot()
    def _update_unmapped_warning(self) -> None:
        config = self._selected_config()
        keys = _unmapped_keys(config) if config is not None else []
        self.unmapped_label.setVisible(bool(keys))
        if keys:
            self.unmapped_label.setText(
                f"⚠ 未変換のキーが {len(keys)} 件あり、training_config.toml には入りません: "
                + ", ".join(keys)
            )

    # --- 書き出し / タグ反映・取り消し ---

    @Slot()
    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "書き出し先を選択")
        if directory:
            self.output_dir_edit.setText(directory)

    @Slot()
    def _update_export_enabled(self) -> None:
        selected = self.selected_version()
        has_selection = selected is not None
        is_working = bool(
            (selected is not None and getattr(selected, "is_working", False))
            or (self._detail is not None and getattr(self._detail.snapshot, "is_working", False))
        )
        self.export_button.setEnabled(
            not self._exporting and self._detail is not None and bool(self.output_dir_edit.text().strip())
        )
        self.copy_tags_button.setEnabled(not self._exporting and self._detail is not None)
        if has_selection:
            self.revoke_tags_button.setText("選択した版の写したタグを取り消す")
            self.revoke_tags_button.setToolTip(
                "選択中の版（および対象フォルダ）で写した Kohya データセット タグを取り消す"
            )
        else:
            self.revoke_tags_button.setText("プロジェクト全体の写したタグを取り消す")
            self.revoke_tags_button.setToolTip(
                "版が未選択のため、プロジェクト全体の Kohya データセット タグを取り消す"
            )
        self.revoke_tags_button.setEnabled(
            not self._exporting and (self._detail is not None or not has_selection)
        )
        self.commit_working_button.setEnabled(not self._exporting and is_working)
        self.discard_working_button.setEnabled(not self._exporting and is_working)
        self.tag_folder_combo.setEnabled(not self._exporting and self._detail is not None)

    @Slot()
    def _on_commit_working_clicked(self) -> None:
        version = self.selected_version()
        if version is None or not getattr(version, "is_working", False) or self._exporting:
            return
        try:
            self._repository.commit_working_version(version.version_id)
        except Exception as exc:
            self.status_label.setText("作業版の確定に失敗しました")
            show_warning(self, "作業版の確定エラー", str(exc))
            return
        rows = self.version_table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            if 0 <= row < len(self._versions):
                self._versions[row] = replace(self._versions[row], is_working=False)
                self.version_table.setItem(row, 7, QTableWidgetItem("確定済"))
        if self._detail is not None and hasattr(self._detail, "snapshot"):
            try:
                self._detail = replace(
                    self._detail,
                    snapshot=replace(self._detail.snapshot, is_working=False),
                )
            except Exception:
                pass
        self.status_label.setText(f"作業版 {version.version_name} を確定しました (確定済)")
        self._update_export_enabled()

    @Slot()
    def _on_discard_working_clicked(self) -> None:
        version = self.selected_version()
        if version is None or not getattr(version, "is_working", False) or self._exporting:
            return
        reply = QMessageBox.question(
            self,
            "作業版を破棄",
            f"作業版「{version.version_name}」を破棄しますか?\nこの操作は取り消せません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("作業版の破棄をキャンセルしました")
            return
        try:
            self._repository.discard_working_version(version.version_id)
        except Exception as exc:
            self.status_label.setText("作業版の破棄に失敗しました")
            show_warning(self, "作業版の破棄エラー", str(exc))
            return
        rows = self.version_table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            if 0 <= row < len(self._versions):
                self._versions.pop(row)
                self.version_table.removeRow(row)
        self._detail = None
        self.folder_table.setRowCount(0)
        self.status_label.setText(f"作業版 {version.version_name} を破棄しました")
        self._update_export_enabled()

    def _start_busy(self, status_text: str) -> None:
        self._exporting = True
        self._update_export_enabled()
        self.close_button.setEnabled(False)
        self.status_label.setText(status_text)

    def _end_export(self) -> None:
        self._exporting = False
        self.close_button.setEnabled(True)
        self._update_export_enabled()

    @Slot()
    def _on_copy_tags_clicked(self) -> None:
        version = self.selected_version()
        if version is None or self._detail is None or self._exporting:
            return
        dir_names = self._selected_tag_dir_names()
        self._pending_copy_scope = (version.version_id, dir_names)
        self._start_busy(f"版 {version.version_id} のタグ反映件数を確認中...")
        worker = KohyaVersionCopyTagsWorker(
            self._repository,
            version.version_id,
            dir_names=dir_names,
            dry_run=True,
        )
        worker.finished.connect(lambda result: self._copy_tags_previewed.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("copy_tags", str(message)))
        self._worker_manager.start_worker(f"kohya_copy_tags_preview_{version.version_id}", worker)

    @Slot(object)
    def _on_copy_tags_previewed(self, result: object) -> None:
        self._end_export()
        scope = self._pending_copy_scope
        self._pending_copy_scope = None
        if not isinstance(result, TagCopyResult) or scope is None:
            return
        version_id, dir_names = scope
        scope_label = dir_names[0] if dir_names else "全フォルダ"
        reply = QMessageBox.question(
            self,
            "学習テキストをタグへ写す",
            f"版の学習テキストをライブラリのタグ (Kohya データセット) へ写します。\n\n"
            f"対象フォルダ: {scope_label} ({result.folders} フォルダ)\n"
            f"対象画像数: {result.images}\n"
            f"追加予定タグ数: {result.tags_added}\n"
            f"既存スキップ数: {result.tags_skipped}\n\n"
            f"実行しますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("学習テキストのタグ反映をキャンセルしました")
            return

        self._start_busy(f"版 {version_id} の学習テキストをタグへ反映中...")
        worker = KohyaVersionCopyTagsWorker(
            self._repository,
            version_id,
            dir_names=dir_names,
            dry_run=False,
        )
        worker.finished.connect(lambda res: self._copy_tags_finished.emit(res))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("copy_tags", str(message)))
        self._worker_manager.start_worker(f"kohya_copy_tags_apply_{version_id}", worker)

    @Slot(object)
    def _on_copy_tags_finished(self, result: object) -> None:
        self._end_export()
        if not isinstance(result, TagCopyResult):
            return
        self.status_label.setText(
            f"タグ反映完了: 追加 {result.tags_added} 件 (スキップ {result.tags_skipped} 件)"
        )
        lines = [
            f"フォルダ数: {result.folders}",
            f"画像数: {result.images}",
            f"追加タグ数: {result.tags_added}",
            f"スキップ数: {result.tags_skipped}",
        ]
        logger.info(
            f"学習テキストのタグ反映完了: folders={result.folders}, images={result.images}, "
            f"added={result.tags_added}, skipped={result.tags_skipped}"
        )
        if result.tags_added > 0:
            self.tags_mutated.emit()
        show_information(self, "学習テキストのタグ反映完了", "\n".join(lines))

    @Slot()
    def _on_revoke_tags_clicked(self) -> None:
        if self._exporting:
            return
        if self._detail is not None:
            version_id: int | None = self._detail.version_id
            dir_names = self._selected_tag_dir_names()
        elif self.selected_version() is None:
            version_id = None
            dir_names = None
        else:
            return
        self._pending_revoke_scope = (version_id, dir_names)
        self._start_busy("取り消し対象のタグ件数を確認中...")
        worker = KohyaVersionRevokeTagsWorker(
            self._repository,
            version_id=version_id,
            dir_names=dir_names,
            dry_run=True,
        )
        worker.finished.connect(lambda result: self._revoke_tags_previewed.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("revoke_tags", str(message)))
        self._worker_manager.start_worker(f"kohya_revoke_tags_preview_{version_id or 'all'}", worker)

    @Slot(object)
    def _on_revoke_tags_previewed(self, result: object) -> None:
        self._end_export()
        scope = self._pending_revoke_scope
        self._pending_revoke_scope = None
        if not isinstance(result, TagRevokeResult) or scope is None:
            return
        version_id, dir_names = scope
        if version_id is not None:
            scope_label = dir_names[0] if dir_names else "全フォルダ"
            scope_line = (
                f"対象範囲: 選択した版 (版 {version_id} / {scope_label}、{result.folders} フォルダ)"
            )
            confirm_line = "選択した版の写したタグを取り消しますか?"
        else:
            scope_line = "対象範囲: プロジェクト全体 (版未選択のためプロジェクト全体の Kohya データセット タグを削除)"
            confirm_line = "プロジェクト全体の写したタグを取り消しますか?"
        reply = QMessageBox.question(
            self,
            "写したタグを取り消す",
            f"Kohya データセットのタグ行だけを削除します (手動・AI タグは残ります)。\n\n"
            f"{scope_line}\n"
            f"対象画像数: {result.images}\n"
            f"削除予定タグ数: {result.tags_removed}\n\n"
            f"{confirm_line}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("タグの取り消しをキャンセルしました")
            return

        self._start_busy("Kohya データセット タグを取り消し中...")
        worker = KohyaVersionRevokeTagsWorker(
            self._repository,
            version_id=version_id,
            dir_names=dir_names,
            dry_run=False,
        )
        worker.finished.connect(lambda res: self._revoke_tags_finished.emit(res))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("revoke_tags", str(message)))
        self._worker_manager.start_worker(f"kohya_revoke_tags_apply_{version_id or 'all'}", worker)

    @Slot(object)
    def _on_revoke_tags_finished(self, result: object) -> None:
        self._end_export()
        if not isinstance(result, TagRevokeResult):
            return
        self.status_label.setText(f"タグ取り消し完了: 削除 {result.tags_removed} 件")
        lines = [
            f"フォルダ数: {result.folders}",
            f"対象画像数: {result.images}",
            f"削除タグ数: {result.tags_removed}",
        ]
        logger.info(
            f"KOHYA_DATASET タグ取り消し完了: folders={result.folders}, images={result.images}, "
            f"removed={result.tags_removed}"
        )
        if result.tags_removed > 0:
            self.tags_mutated.emit()
        show_information(self, "写したタグの取り消し完了", "\n".join(lines))

    @Slot()
    def _on_export_clicked(self) -> None:
        version = self.selected_version()
        if version is None or self._detail is None:
            return
        output_dir = Path(self.output_dir_edit.text().strip())
        if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
            show_warning(
                self, "Kohya 版の書き出し", f"書き出し先が空のディレクトリではありません:\n{output_dir}"
            )
            return
        config = self._selected_config()
        keys = _unmapped_keys(config) if config is not None else []
        if keys:
            reply = QMessageBox.question(
                self,
                "未変換のキー",
                f"選んだ学習設定には未変換のキーが {len(keys)} 件あり、書き出す TOML には入りません。\n"
                f"{', '.join(keys)}\n\nこのまま書き出しますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._start_busy(f"版 {version.version_id} を書き出し中...")
        worker = KohyaVersionExportWorker(
            self._repository, version.version_id, output_dir, config.id if config is not None else None
        )
        worker.finished.connect(lambda result: self._export_finished.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("export", str(message)))
        self._worker_manager.start_worker(f"kohya_version_export_{version.version_id}", worker)

    @Slot(object)
    def _on_export_finished(self, result: object) -> None:
        self._end_export()
        if not isinstance(result, KohyaExportResult):
            return
        self.status_label.setText(f"書き出し完了: {result.output_dir}")
        lines = [
            f"書き出し先: {result.output_dir}",
            f"フォルダ数: {result.folder_count}",
            f"画像数: {result.image_count}",
            f"学習テキスト数: {result.text_count}",
            f"dataset_config: {result.dataset_config_path}",
        ]
        if result.training_config_path is not None:
            lines.append(f"training_config: {result.training_config_path}")
        logger.info(
            f"Kohya 版の書き出し完了: folders={result.folder_count}, images={result.image_count}, "
            f"texts={result.text_count}"
        )
        show_information(self, "Kohya 版の書き出し完了", "\n".join(lines))

    @Slot(str, str)
    def _on_task_failed(self, task: str, message: str) -> None:
        if task == "export":
            self._end_export()
            self.status_label.setText("書き出しに失敗しました")
            show_warning(self, "Kohya 版の書き出しエラー", message)
            return
        if task == "copy_tags":
            self._end_export()
            self.status_label.setText("タグ反映に失敗しました")
            show_warning(self, "学習テキストのタグ反映エラー", message)
            return
        if task == "revoke_tags":
            self._end_export()
            self.status_label.setText("タグの取り消しに失敗しました")
            show_warning(self, "写したタグの取り消しエラー", message)
            return
        self.status_label.setText("読み込みに失敗しました")
        show_warning(self, "Kohya 版の読み込みエラー", message)

    # --- 終了 ---

    def reject(self) -> None:
        """書き出し中は閉じない。"""
        if self._exporting:
            return
        self._worker_manager.cancel_all_workers()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """書き出し中はウィンドウを閉じない。"""
        if self._exporting:
            event.ignore()
            return
        self._worker_manager.cancel_all_workers()
        super().closeEvent(event)
