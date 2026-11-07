"""データセット選択ダイアログ。

画像ディレクトリに加えて、Kohya GUI の設定 JSON (複数可) を選べる。
JSON を 1 つ以上選んだ場合は Kohya データセットの取り込み、0 個なら従来の画像登録として扱う。
従来の画像登録では、画像を直接含むサブフォルダごとに共通タグを入力できる (Issue #1409)。
"""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services.folder_common_tags import list_image_subfolders, parse_common_tags

# サブフォルダ共通タグ表の列
_FOLDER_COLUMN = 0
_COUNT_COLUMN = 1
_TAGS_COLUMN = 2


@dataclass(frozen=True)
class DatasetSelection:
    """データセット選択ダイアログの選択結果。

    Attributes:
        directory: 画像ディレクトリ。
        config_files: 選択された設定 JSON。空なら従来の画像登録。
        dataset_name: データセット名 (Kohya 取り込み時のみ意味を持つ)。
        version_name: 版名。空なら service が候補を作る (Kohya 取り込み時のみ)。
        folder_tags: サブフォルダ (directory からの相対パス) → 共通タグ。
            従来の画像登録時のみ意味を持ち、タグを入力したサブフォルダだけを含む。
    """

    directory: Path
    config_files: tuple[Path, ...] = ()
    dataset_name: str = ""
    version_name: str = ""
    folder_tags: dict[Path, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_kohya_import(self) -> bool:
        """設定 JSON が 1 つ以上選ばれ、Kohya 取り込みとして扱うか。"""
        return len(self.config_files) > 0


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

        # 設定 JSON 一覧
        layout.addWidget(QLabel("Kohya 設定 JSON (任意。選ぶと Kohya データセットとして取り込みます)"))
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

    def refresh_subfolders(self) -> None:
        """入力中のディレクトリを走査し、サブフォルダ共通タグ表を作り直す。

        同じディレクトリなら作り直さず、入力済みのタグを保つ。
        """
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
        has_configs = self.config_list.count() > 0
        self.dataset_name_edit.setEnabled(has_configs)
        self.version_name_edit.setEnabled(has_configs)
        # 共通タグは普段の画像のタグ (Tag) に付く。Kohya 取り込みとは独立 (Issue #1409)
        self.folder_tags_label.setEnabled(not has_configs)
        self.folder_table.setEnabled(not has_configs)
        self.folder_table.setVisible(self.folder_table.rowCount() > 0)
        self.folder_empty_label.setVisible(self.folder_table.rowCount() == 0)
        self.remove_config_button.setEnabled(len(self.config_list.selectedItems()) > 0)
        has_directory = bool(self.directory_edit.text().strip())
        # Kohya 取り込みではデータセット名が必須
        name_ok = not has_configs or bool(self.dataset_name_edit.text().strip())
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(has_directory and name_ok)

    # --- 結果 ---

    def selection(self) -> DatasetSelection | None:
        """現在の入力から選択結果を作る。

        Returns:
            選択結果。ディレクトリ未入力なら None。
        """
        directory_text = self.directory_edit.text().strip()
        if not directory_text:
            return None
        config_files = tuple(Path(self.config_list.item(i).text()) for i in range(self.config_list.count()))
        directory = Path(directory_text)
        # 表が別ディレクトリのものなら共通タグは渡さない (入力欄だけ書き換えて OK した場合)
        folder_tags = (
            self._collect_folder_tags() if not config_files and directory == self._scanned_directory else {}
        )
        return DatasetSelection(
            directory=directory,
            config_files=config_files,
            dataset_name=self.dataset_name_edit.text().strip() if config_files else "",
            version_name=self.version_name_edit.text().strip() if config_files else "",
            folder_tags=folder_tags,
        )

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
