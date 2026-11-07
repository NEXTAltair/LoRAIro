"""データセット選択ダイアログ。

画像ディレクトリに加えて、Kohya GUI の設定 JSON (複数可) を選べる。
JSON を 1 つ以上選んだ場合は Kohya データセットの取り込み、0 個なら従来の画像登録として扱う。
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class DatasetSelection:
    """データセット選択ダイアログの選択結果。

    Attributes:
        directory: 画像ディレクトリ。
        config_files: 選択された設定 JSON。空なら従来の画像登録。
        dataset_name: データセット名 (Kohya 取り込み時のみ意味を持つ)。
        version_name: 版名。空なら service が候補を作る (Kohya 取り込み時のみ)。
    """

    directory: Path
    config_files: tuple[Path, ...] = ()
    dataset_name: str = ""
    version_name: str = ""

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

    def _update_state(self, *_args: object) -> None:
        """入力状態に応じて各欄・OK ボタンの有効/無効を更新する。"""
        has_configs = self.config_list.count() > 0
        self.dataset_name_edit.setEnabled(has_configs)
        self.version_name_edit.setEnabled(has_configs)
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
        return DatasetSelection(
            directory=Path(directory_text),
            config_files=config_files,
            dataset_name=self.dataset_name_edit.text().strip() if config_files else "",
            version_name=self.version_name_edit.text().strip() if config_files else "",
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
