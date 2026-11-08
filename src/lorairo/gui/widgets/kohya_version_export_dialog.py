"""Kohya データセットの版を一覧し、Kohya-ss 形式で書き出すダイアログ (Issue #1456)。

入口はエクスポートタブの「Kohya 版を書き出す…」ボタン。版の一覧・版の詳細の取得と書き出しは
worker スレッドで行い、GUI をブロックしない (`kohya_version_workers`)。
書き出しは CLI の `lorairo-cli dataset export` と同じ `KohyaDatasetExportService` を使う。
"""

from __future__ import annotations

import json
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

from ...database.repository.dataset import DatasetRepository, TrainingConfigSnapshot, VersionSummary
from ...services.kohya_dataset_export_service import KohyaExportResult
from ...utils.log import logger
from ..message_box import show_information, show_warning
from ..workers.kohya_version_workers import (
    KohyaVersionDetail,
    KohyaVersionDetailWorker,
    KohyaVersionExportWorker,
    KohyaVersionListWorker,
)
from ..workers.manager import WorkerManager

_VERSION_HEADERS = ["データセット", "版", "版 ID", "親の版", "フォルダ", "画像", "作成日"]
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

    # worker スレッドから GUI スレッドへ結果を渡す (受け手はダイアログ = GUI スレッド)
    _versions_loaded = Signal(object)
    _detail_loaded = Signal(int, object)
    _export_finished = Signal(object)
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

        self._build_ui()
        self._versions_loaded.connect(self._on_versions_loaded)
        self._detail_loaded.connect(self._on_detail_loaded)
        self._export_finished.connect(self._on_export_finished)
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
            values = [
                version.dataset_name,
                version.version_name,
                str(version.version_id),
                str(version.parent_version_id) if version.parent_version_id is not None else "-",
                str(version.folder_count),
                str(version.image_count),
                created,
            ]
            for column, value in enumerate(values):
                self.version_table.setItem(row, column, QTableWidgetItem(value))
        self.status_label.setText(
            f"{len(self._versions)} 件の版" if self._versions else "取り込んだデータセットの版がありません"
        )

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
        self.status_label.setText(
            f"{detail.snapshot.dataset_name} / {detail.snapshot.version_name}: "
            f"{len(folders)} フォルダ、学習設定 {len(detail.training_configs)} 件"
        )
        self._update_export_enabled()

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

    # --- 書き出し ---

    @Slot()
    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "書き出し先を選択")
        if directory:
            self.output_dir_edit.setText(directory)

    @Slot()
    def _update_export_enabled(self) -> None:
        self.export_button.setEnabled(
            not self._exporting and self._detail is not None and bool(self.output_dir_edit.text().strip())
        )

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
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._exporting = True
        self._update_export_enabled()
        self.close_button.setEnabled(False)
        self.status_label.setText(f"版 {version.version_id} を書き出し中...")
        worker = KohyaVersionExportWorker(
            self._repository, version.version_id, output_dir, config.id if config is not None else None
        )
        worker.finished.connect(lambda result: self._export_finished.emit(result))
        worker.error_occurred.connect(lambda message: self._task_failed.emit("export", str(message)))
        self._worker_manager.start_worker(f"kohya_version_export_{version.version_id}", worker)

    def _end_export(self) -> None:
        self._exporting = False
        self.close_button.setEnabled(True)
        self._update_export_enabled()

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
