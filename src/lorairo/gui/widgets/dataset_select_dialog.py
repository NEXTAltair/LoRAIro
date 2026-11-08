"""データセット選択ダイアログ。

画像ディレクトリに加えて、Kohya GUI の設定 JSON (複数可) を選べる。
「Kohya データセットとして取り込む」をオンにすると Kohya データセットの取り込み、オフなら
従来の画像登録として扱う (設定 JSON は任意。Issue #1453)。
Kohya 取り込みでは、`<数字>_<名前>` フォルダごとに取捨・繰り返し回数・トリガーワードを確認して
確定する。トリガーワード候補は横に表示するだけで、採用ボタンを押したときだけ入力欄に入る (Issue #1452)。
従来の画像登録では、画像を直接含むサブフォルダごとに共通タグを入力できる (Issue #1409)。
"""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.dataset_import_service import FolderOverride, FolderScanSummary, summarize_folder
from ...services.folder_common_tags import list_image_subfolders, parse_common_tags
from ...services.kohya_scanner import scan_kohya_directory
from ...utils.log import logger

# サブフォルダ共通タグ表の列
_FOLDER_COLUMN = 0
_COUNT_COLUMN = 1
_TAGS_COLUMN = 2

# Kohya フォルダ表の列
_K_INCLUDE_COLUMN = 0
_K_FOLDER_COLUMN = 1
_K_REPEATS_COLUMN = 2
_K_IMAGES_COLUMN = 3
_K_NO_TEXT_COLUMN = 4
_K_TRIGGER_COLUMN = 5
_K_CANDIDATE_COLUMN = 6
_K_ADOPT_COLUMN = 7
_K_HEADERS = ("取り込む", "フォルダ", "繰り返し", "画像数", "テキスト無し", "トリガーワード", "候補", "")
_MAX_REPEATS = 9999


@dataclass(frozen=True)
class DatasetSelection:
    """データセット選択ダイアログの選択結果。

    Attributes:
        directory: 画像ディレクトリ。
        config_files: 選択された設定 JSON (Kohya 取り込み時のみ。0 個でもよい)。
        dataset_name: データセット名 (Kohya 取り込み時のみ意味を持つ)。
        version_name: 版名。空なら service が候補を作る (Kohya 取り込み時のみ)。
        folder_tags: サブフォルダ (directory からの相対パス) → 共通タグ。
            従来の画像登録時のみ意味を持ち、タグを入力したサブフォルダだけを含む。
        kohya_import: Kohya データセットとして取り込むか (ダイアログのチェックボックス)。
        folder_overrides: Kohya フォルダごとの確定値 (取捨・繰り返し回数・トリガーワード)。
            フォルダ表が選択ディレクトリのものでない場合は `None` (スキャン結果のまま取り込む)。
    """

    directory: Path
    config_files: tuple[Path, ...] = ()
    dataset_name: str = ""
    version_name: str = ""
    folder_tags: dict[Path, tuple[str, ...]] = field(default_factory=dict)
    kohya_import: bool = False
    folder_overrides: tuple[FolderOverride, ...] | None = None

    @property
    def is_kohya_import(self) -> bool:
        """Kohya 取り込みとして扱うか。設定 JSON の有無とは独立に、チェックボックスで決まる。"""
        return self.kohya_import


class DatasetSelectDialog(QDialog):
    """画像ディレクトリと設定 JSON を選ぶモーダルダイアログ。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """ダイアログを初期化する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("データセットを選択")
        self.setMinimumWidth(520)
        self.setModal(True)
        # ディレクトリ名から自動入力した直近のデータセット名 (手入力を上書きしないため)
        self._auto_dataset_name = ""
        # サブフォルダ表を作った時点のディレクトリ (同じなら作り直さず入力を保つ)
        self._scanned_directory: Path | None = None
        # Kohya フォルダ表を作った時点のディレクトリ (同じなら作り直さず入力を保つ)
        self._kohya_scanned_directory: Path | None = None
        # Kohya フォルダのスキャンに失敗したときの表示文
        self._kohya_error_text = ""
        self._setup_ui()
        self._update_state()

    def _setup_ui(self) -> None:
        """UI を構築する。"""
        layout = QVBoxLayout(self)

        # ディレクトリ欄
        layout.addWidget(QLabel("画像ディレクトリ"))
        dir_row = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("画像ディレクトリを選択")
        self.directory_edit.textChanged.connect(self._on_directory_changed)
        # 走査はキー入力ごとでなく、入力確定時と参照ボタン選択時に行う
        self.directory_edit.editingFinished.connect(self.refresh_subfolders)
        self.browse_button = QPushButton("参照...")
        self.browse_button.clicked.connect(self._browse_directory)
        dir_row.addWidget(self.directory_edit)
        dir_row.addWidget(self.browse_button)
        layout.addLayout(dir_row)

        # Kohya 取り込みの切り替え (設定 JSON の有無とは独立。Issue #1453)
        self.kohya_check = QCheckBox("Kohya データセットとして取り込む (<数字>_<名前> フォルダ単位)")
        self.kohya_check.toggled.connect(self._on_kohya_toggled)
        layout.addWidget(self.kohya_check)

        # 設定 JSON 一覧
        self.config_label = QLabel(
            "Kohya 設定 JSON (任意。版に学習設定として保存します。追加すると Kohya 取り込みになります)"
        )
        layout.addWidget(self.config_label)
        self.config_list = QListWidget()
        self.config_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.config_list.model().rowsInserted.connect(self._update_state)
        self.config_list.model().rowsRemoved.connect(self._update_state)
        self.config_list.itemSelectionChanged.connect(self._update_state)
        layout.addWidget(self.config_list)
        config_buttons = QHBoxLayout()
        self.add_config_button = QPushButton("追加...")
        self.add_config_button.clicked.connect(self._add_configs)
        self.remove_config_button = QPushButton("削除")
        self.remove_config_button.clicked.connect(self._remove_selected_configs)
        config_buttons.addWidget(self.add_config_button)
        config_buttons.addWidget(self.remove_config_button)
        config_buttons.addStretch()
        layout.addLayout(config_buttons)

        # データセット名 / 版名
        form = QFormLayout()
        self.dataset_name_edit = QLineEdit()
        self.dataset_name_edit.textChanged.connect(self._update_state)
        self.version_name_edit = QLineEdit()
        self.version_name_edit.setPlaceholderText("空なら設定 JSON の output_name かフォルダ名から決定")
        form.addRow("データセット名", self.dataset_name_edit)
        form.addRow("版名", self.version_name_edit)
        layout.addLayout(form)

        # Kohya フォルダ表 (Kohya 取り込みのみ)
        self._setup_kohya_table(layout)

        # サブフォルダごとの共通タグ (従来の画像登録のみ)
        self.folder_tags_label = QLabel(
            "サブフォルダごとの共通タグ (任意。カンマ区切り。入力した表記のまま手動タグとして付きます)"
        )
        self.folder_tags_label.setWordWrap(True)
        layout.addWidget(self.folder_tags_label)
        self.folder_table = QTableWidget(0, 3)
        self.folder_table.setHorizontalHeaderLabels(["サブフォルダ", "画像数", "共通タグ"])
        self.folder_table.verticalHeader().setVisible(False)
        self.folder_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.folder_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.folder_table.horizontalHeader()
        header.setSectionResizeMode(_FOLDER_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COUNT_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_TAGS_COLUMN, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.folder_table)
        self.folder_empty_label = QLabel("画像を含むサブフォルダはありません")
        layout.addWidget(self.folder_empty_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _setup_kohya_table(self, layout: QVBoxLayout) -> None:
        """Kohya フォルダ表 (取捨・繰り返し回数・トリガーワード・候補) を作る。"""
        self.kohya_label = QLabel(
            "取り込むフォルダ (トリガーワード候補は確定値ではありません。採用を押すと入力欄に入ります)"
        )
        self.kohya_label.setWordWrap(True)
        layout.addWidget(self.kohya_label)
        self.kohya_table = QTableWidget(0, len(_K_HEADERS))
        self.kohya_table.setHorizontalHeaderLabels(list(_K_HEADERS))
        self.kohya_table.verticalHeader().setVisible(False)
        self.kohya_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.kohya_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.kohya_table.horizontalHeader()
        for column in range(len(_K_HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_K_TRIGGER_COLUMN, QHeaderView.ResizeMode.Stretch)
        self.kohya_table.itemChanged.connect(self._update_state)
        layout.addWidget(self.kohya_table)
        self.kohya_summary_label = QLabel("")
        self.kohya_summary_label.setWordWrap(True)
        layout.addWidget(self.kohya_summary_label)

    # --- 操作 ---

    def _browse_directory(self) -> None:
        """ディレクトリ選択ダイアログを開く。"""
        directory = QFileDialog.getExistingDirectory(
            self, "データセットディレクトリを選択してください", "", QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.directory_edit.setText(directory)
            self.refresh_subfolders()

    def _add_configs(self) -> None:
        """設定 JSON の選択ダイアログを開き、一覧へ追加する。"""
        files, _ = QFileDialog.getOpenFileNames(self, "設定 JSON を選択", "", "JSON (*.json)")
        for file in files:
            self.add_config_file(Path(file))

    def add_config_file(self, path: Path) -> None:
        """設定 JSON を一覧へ追加する (重複は無視)。

        Args:
            path: 追加する設定 JSON のパス。
        """
        text = str(path)
        existing = {self.config_list.item(i).text() for i in range(self.config_list.count())}
        if text not in existing:
            self.config_list.addItem(text)
        # 設定 JSON は Kohya 取り込みでのみ使うため、追加したら Kohya 取り込みに切り替える
        self.kohya_check.setChecked(True)

    def _remove_selected_configs(self) -> None:
        """一覧で選択中の設定 JSON を取り除く。"""
        for item in self.config_list.selectedItems():
            self.config_list.takeItem(self.config_list.row(item))

    def _on_directory_changed(self, text: str) -> None:
        """ディレクトリ変更時、データセット名が未編集ならディレクトリ名を既定にする。"""
        current = self.dataset_name_edit.text()
        if current == "" or current == self._auto_dataset_name:
            self._auto_dataset_name = Path(text).name if text.strip() else ""
            self.dataset_name_edit.setText(self._auto_dataset_name)
        self._update_state()

    def _on_kohya_toggled(self, checked: bool) -> None:
        """Kohya 取り込みに切り替えたら、フォルダ表を作る。"""
        if checked:
            self.refresh_kohya_folders()
        self._update_state()

    def _current_directory(self) -> Path | None:
        text = self.directory_edit.text().strip()
        return Path(text) if text else None

    def refresh_subfolders(self) -> None:
        """入力中のディレクトリを走査し、サブフォルダ共通タグ表 (と Kohya フォルダ表) を作り直す。

        同じディレクトリなら作り直さず、入力済みのタグを保つ。Kohya フォルダ表は Kohya 取り込みが
        オンのときだけ作る。
        """
        if self.kohya_check.isChecked():
            self.refresh_kohya_folders()
        text = self.directory_edit.text().strip()
        directory = Path(text) if text else None
        if directory == self._scanned_directory:
            return
        self._scanned_directory = directory
        subfolders = list_image_subfolders(directory) if directory is not None else []
        self.folder_table.setRowCount(len(subfolders))
        read_only = Qt.ItemFlag.ItemIsEnabled
        for row, subfolder in enumerate(subfolders):
            folder_item = QTableWidgetItem(subfolder.relative_path.as_posix())
            folder_item.setFlags(read_only)
            count_item = QTableWidgetItem(str(subfolder.image_count))
            count_item.setFlags(read_only)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.folder_table.setItem(row, _FOLDER_COLUMN, folder_item)
            self.folder_table.setItem(row, _COUNT_COLUMN, count_item)
            self.folder_table.setItem(row, _TAGS_COLUMN, QTableWidgetItem(""))
        self._update_state()

    def refresh_kohya_folders(self) -> None:
        """入力中のディレクトリを Kohya 形式としてスキャンし、フォルダ表を作り直す。

        同じディレクトリなら作り直さず、入力済みの値を保つ。トリガーワード欄は空のままにし、
        候補は「候補」列に表示するだけにする (確認なしに確定しない。ADR 0098)。
        """
        directory = self._current_directory()
        if directory == self._kohya_scanned_directory:
            return
        self._kohya_scanned_directory = directory
        summaries: list[tuple[str, int, FolderScanSummary]] = []
        error_text = ""
        if directory is not None and directory.is_dir():
            try:
                summaries = [
                    (folder.dir_name, folder.num_repeats, summarize_folder(folder))
                    for folder in scan_kohya_directory(directory)
                ]
            except OSError as e:
                logger.opt(exception=True).warning(f"Kohya フォルダのスキャンに失敗: {directory}")
                error_text = f"フォルダを読めませんでした: {type(e).__name__}"

        self.kohya_table.blockSignals(True)
        try:
            self.kohya_table.setRowCount(0)
            self.kohya_table.setRowCount(len(summaries))
            for row, (dir_name, num_repeats, summary) in enumerate(summaries):
                self._fill_kohya_row(row, dir_name, num_repeats, summary)
        finally:
            self.kohya_table.blockSignals(False)
        self._kohya_error_text = error_text
        self._update_state()

    def _fill_kohya_row(
        self, row: int, dir_name: str, num_repeats: int, summary: FolderScanSummary
    ) -> None:
        """Kohya フォルダ表の 1 行を作る。"""
        read_only = Qt.ItemFlag.ItemIsEnabled
        include_item = QTableWidgetItem("")
        include_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        include_item.setCheckState(Qt.CheckState.Checked)
        self.kohya_table.setItem(row, _K_INCLUDE_COLUMN, include_item)

        folder_item = QTableWidgetItem(dir_name)
        folder_item.setFlags(read_only)
        self.kohya_table.setItem(row, _K_FOLDER_COLUMN, folder_item)

        repeats = QSpinBox()
        repeats.setRange(1, _MAX_REPEATS)
        repeats.setValue(max(1, min(num_repeats, _MAX_REPEATS)))
        self.kohya_table.setCellWidget(row, _K_REPEATS_COLUMN, repeats)

        for column, value in (
            (_K_IMAGES_COLUMN, summary.image_count),
            (_K_NO_TEXT_COLUMN, summary.images_without_text),
        ):
            count_item = QTableWidgetItem(str(value))
            count_item.setFlags(read_only)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.kohya_table.setItem(row, column, count_item)

        # トリガーワードは空で始める (候補を初期値にしない)
        self.kohya_table.setItem(row, _K_TRIGGER_COLUMN, QTableWidgetItem(""))

        candidate = summary.trigger_candidate
        candidate_text = f"{candidate} ({summary.trigger_match_rate:.0%})" if candidate else "-"
        candidate_item = QTableWidgetItem(candidate_text)
        candidate_item.setFlags(read_only)
        self.kohya_table.setItem(row, _K_CANDIDATE_COLUMN, candidate_item)

        adopt = QPushButton("採用")
        adopt.setEnabled(candidate is not None)
        if candidate is not None:
            adopt.clicked.connect(lambda _checked=False, r=row, word=candidate: self.adopt_trigger(r, word))
        self.kohya_table.setCellWidget(row, _K_ADOPT_COLUMN, adopt)

    def adopt_trigger(self, row: int, word: str) -> None:
        """トリガーワード候補を、その行の入力欄に入れる。

        Args:
            row: Kohya フォルダ表の行。
            word: 入れるトリガーワード。
        """
        item = self.kohya_table.item(row, _K_TRIGGER_COLUMN)
        if item is not None:
            item.setText(word)

    def kohya_row(self, dir_name: str) -> int | None:
        """Kohya フォルダ表で `dir_name` の行番号を返す。無ければ None。

        Args:
            dir_name: フォルダ名 (`10_name` 形式)。
        """
        for row in range(self.kohya_table.rowCount()):
            item = self.kohya_table.item(row, _K_FOLDER_COLUMN)
            if item is not None and item.text() == dir_name:
                return row
        return None

    def _repeats_spin(self, row: int) -> QSpinBox | None:
        widget = self.kohya_table.cellWidget(row, _K_REPEATS_COLUMN)
        return widget if isinstance(widget, QSpinBox) else None

    def _collect_folder_overrides(self) -> tuple[FolderOverride, ...]:
        """Kohya フォルダ表の値を確定値として集める。"""
        overrides: list[FolderOverride] = []
        for row in range(self.kohya_table.rowCount()):
            folder_item = self.kohya_table.item(row, _K_FOLDER_COLUMN)
            include_item = self.kohya_table.item(row, _K_INCLUDE_COLUMN)
            trigger_item = self.kohya_table.item(row, _K_TRIGGER_COLUMN)
            spin = self._repeats_spin(row)
            if folder_item is None or include_item is None or spin is None:
                continue
            trigger = trigger_item.text().strip() if trigger_item is not None else ""
            overrides.append(
                FolderOverride(
                    dir_name=folder_item.text(),
                    include=include_item.checkState() == Qt.CheckState.Checked,
                    num_repeats=spin.value(),
                    trigger_word=trigger or None,
                )
            )
        return tuple(overrides)

    def _kohya_table_is_current(self) -> bool:
        """Kohya フォルダ表が、入力中のディレクトリをスキャンしたものか。"""
        directory = self._current_directory()
        return directory is not None and directory == self._kohya_scanned_directory

    def set_folder_tags_text(self, relative_path: Path, text: str) -> bool:
        """サブフォルダの共通タグ欄へ文字列を入れる。

        Args:
            relative_path: 選択ディレクトリからの相対パス。
            text: カンマ区切りのタグ文字列。

        Returns:
            該当するサブフォルダの行があれば True。
        """
        for row in range(self.folder_table.rowCount()):
            tags_item = self.folder_table.item(row, _TAGS_COLUMN)
            if tags_item is not None and Path(self._cell_text(row, _FOLDER_COLUMN)) == relative_path:
                tags_item.setText(text)
                return True
        return False

    def _cell_text(self, row: int, column: int) -> str:
        """サブフォルダ表のセル文字列を返す (セルが無ければ空文字)。"""
        item = self.folder_table.item(row, column)
        return item.text() if item is not None else ""

    def _collect_folder_tags(self) -> dict[Path, tuple[str, ...]]:
        """共通タグを入力したサブフォルダだけを集める。"""
        folder_tags: dict[Path, tuple[str, ...]] = {}
        for row in range(self.folder_table.rowCount()):
            tags = parse_common_tags(self._cell_text(row, _TAGS_COLUMN))
            if tags:
                folder_tags[Path(self._cell_text(row, _FOLDER_COLUMN))] = tags
        return folder_tags

    def _update_state(self, *_args: object) -> None:
        """入力状態に応じて各欄・OK ボタンの有効/無効を更新する。"""
        is_kohya = self.kohya_check.isChecked()
        self.config_label.setEnabled(is_kohya)
        # 追加ボタンは常に押せる (追加すると Kohya 取り込みに切り替わる)。オフの間は一覧を無効表示にし、
        # 選択結果にも含めない
        self.config_list.setEnabled(is_kohya)
        self.dataset_name_edit.setEnabled(is_kohya)
        self.version_name_edit.setEnabled(is_kohya)
        # 共通タグは普段の画像のタグ (Tag) に付く。Kohya 取り込みとは独立 (Issue #1409)
        self.folder_tags_label.setVisible(not is_kohya)
        self.folder_table.setEnabled(not is_kohya)
        self.folder_table.setVisible(not is_kohya and self.folder_table.rowCount() > 0)
        self.folder_empty_label.setVisible(not is_kohya and self.folder_table.rowCount() == 0)
        self.kohya_label.setVisible(is_kohya)
        self.kohya_table.setVisible(is_kohya and self.kohya_table.rowCount() > 0)
        self.kohya_summary_label.setVisible(is_kohya)
        self.remove_config_button.setEnabled(is_kohya and len(self.config_list.selectedItems()) > 0)
        has_directory = bool(self.directory_edit.text().strip())
        # Kohya 取り込みではデータセット名が必須
        name_ok = not is_kohya or bool(self.dataset_name_edit.text().strip())
        # フォルダ表が今のディレクトリのものなら、取り込むフォルダが 1 つ以上必要 (空の版を作らない)
        folders_ok = True
        if is_kohya and self._kohya_table_is_current():
            overrides = self._collect_folder_overrides()
            included = [override for override in overrides if override.include]
            folders_ok = len(included) > 0
            self.kohya_summary_label.setText(self._kohya_summary_text(len(overrides), len(included)))
        elif is_kohya:
            self.kohya_summary_label.setText("ディレクトリを確定するとフォルダを一覧します")
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(has_directory and name_ok and folders_ok)

    def _kohya_summary_text(self, folder_count: int, included_count: int) -> str:
        """Kohya フォルダ表の下に出す要約 (取り込むフォルダ数・学習テキストの無い画像数)。"""
        if self._kohya_error_text:
            return self._kohya_error_text
        if folder_count == 0:
            return (
                "取り込める <数字>_<名前> フォルダがありません "
                "(学習プロジェクト全体でなく、画像フォルダの親を選んでください)"
            )
        without_text = 0
        for row in range(self.kohya_table.rowCount()):
            include_item = self.kohya_table.item(row, _K_INCLUDE_COLUMN)
            count_item = self.kohya_table.item(row, _K_NO_TEXT_COLUMN)
            if include_item is not None and include_item.checkState() == Qt.CheckState.Checked:
                without_text += int(count_item.text()) if count_item is not None else 0
        text = f"{included_count} / {folder_count} フォルダを取り込みます"
        if without_text:
            text += f"。学習テキストの無い画像 {without_text} 枚もそのまま取り込みます"
        return text

    # --- 結果 ---

    def selection(self) -> DatasetSelection | None:
        """現在の入力から選択結果を作る。

        Returns:
            選択結果。ディレクトリ未入力なら None。
        """
        directory_text = self.directory_edit.text().strip()
        if not directory_text:
            return None
        directory = Path(directory_text)
        is_kohya = self.kohya_check.isChecked()
        if is_kohya:
            config_files = tuple(
                Path(self.config_list.item(i).text()) for i in range(self.config_list.count())
            )
            # 表が別ディレクトリのものなら確定値は渡さない (入力欄だけ書き換えて OK した場合)
            overrides = self._collect_folder_overrides() if self._kohya_table_is_current() else None
            return DatasetSelection(
                directory=directory,
                config_files=config_files,
                dataset_name=self.dataset_name_edit.text().strip(),
                version_name=self.version_name_edit.text().strip(),
                kohya_import=True,
                folder_overrides=overrides,
            )
        # 表が別ディレクトリのものなら共通タグは渡さない (入力欄だけ書き換えて OK した場合)
        folder_tags = self._collect_folder_tags() if directory == self._scanned_directory else {}
        return DatasetSelection(directory=directory, folder_tags=folder_tags)

    @classmethod
    def get_selection(cls, parent: QWidget | None = None) -> DatasetSelection | None:
        """ダイアログを表示し、OK なら選択結果を返す。

        Args:
            parent: 親ウィジェット。

        Returns:
            選択結果。キャンセル時は None。
        """
        dialog = cls(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selection()
        return None
