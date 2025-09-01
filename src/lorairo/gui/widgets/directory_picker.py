import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QWidget

from ...gui.designer.DirectoryPicker_ui import Ui_DirectoryPickerWidget
from ...utils.log import logger


class DirectoryPickerWidget(QWidget, Ui_DirectoryPickerWidget):
    # 有効なディレクトリパスが確定した時のみ発信される検証済みシグナル
    validDirectorySelected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)  # type: ignore
        self.set_label_text("フォルダを選択")  # type: ignore

        self.DirectoryPicker.pushButtonPicker.clicked.connect(self.select_folder)
        self.DirectoryPicker.comboBoxHistory.currentIndexChanged.connect(self.on_history_item_selected)

        # Enterキーとフォーカスアウト時にバリデーション実行
        self.DirectoryPicker.lineEditPicker.returnPressed.connect(self._validate_and_emit)
        self.DirectoryPicker.lineEditPicker.editingFinished.connect(self._validate_and_emit)

    def select_folder(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if dir_path:
            self.DirectoryPicker.lineEditPicker.setText(dir_path)
            self.DirectoryPicker.update_history(dir_path)  # type: ignore
            logger.debug(f"フォルダが選択: {dir_path}")
            # ダイアログで選択されたパスは確実に有効なので即座に発信
            self.validDirectorySelected.emit(dir_path)

    def on_history_item_selected(self, index: int) -> None:
        """履歴項目が選択されたときの処理"""
        selected_path = self.DirectoryPicker.comboBoxHistory.itemData(
            index, Qt.ItemDataRole.ToolTipRole
        )  # ツールチップデータ (フルパス) を取得
        if selected_path:  # None チェック追加
            self.DirectoryPicker.lineEditPicker.setText(selected_path)
            logger.debug(f"履歴からフォルダが選択: {selected_path}")
            # 履歴のパスも基本的に有効なので発信（軽量チェック後）
            if self._quick_validation_check(selected_path):
                self.validDirectorySelected.emit(selected_path)

    def _validate_and_emit(self) -> None:
        """手動入力パスを検証し、有効な場合のみシグナルを発信"""
        current_path = self.DirectoryPicker.lineEditPicker.text().strip()

        if not current_path:
            logger.debug("空のパスのため、シグナル発信をスキップ")
            return

        if self._validate_dataset_directory(current_path):
            logger.debug(f"有効なデータセットディレクトリを確認: {current_path}")
            self.validDirectorySelected.emit(current_path)
        else:
            logger.warning(f"無効なデータセットディレクトリ: {current_path}")

    def _quick_validation_check(self, directory_path: str) -> bool:
        """履歴選択用の軽量チェック"""
        try:
            path_obj = Path(directory_path)
            return path_obj.exists() and path_obj.is_dir()
        except Exception:
            return False

    def _validate_dataset_directory(self, directory_path: str) -> bool:
        """データセットディレクトリとしての適性をシンプルに検証"""
        try:
            path_obj = Path(directory_path)

            # 基本チェック
            if not (path_obj.exists() and path_obj.is_dir()):
                logger.warning(f"ディレクトリが存在しないか読み取れません: {directory_path}")
                return False

            # 階層制限とファイルカウント
            max_depth = 3
            max_files = 10000
            image_count = 0
            total_files = 0

            # 画像拡張子リスト
            image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

            for root, dirs, files in os.walk(path_obj):
                # 階層深度チェック
                try:
                    current_depth = len(Path(root).relative_to(path_obj).parts)
                    if current_depth > max_depth:
                        dirs.clear()  # これ以上深く探索しない
                        continue
                except ValueError:
                    # relative_to が失敗した場合はスキップ
                    continue

                for file in files:
                    total_files += 1
                    if total_files > max_files:
                        logger.warning(f"ファイル数が上限を超過: {directory_path} ({max_files}+件)")
                        return False

                    # 画像ファイルチェック
                    if Path(file).suffix.lower() in image_extensions:
                        image_count += 1

            # 最終判定
            if image_count == 0:
                logger.warning(f"画像ファイルが見つかりません: {directory_path}")
                return False

            logger.debug(
                f"有効なデータセットディレクトリ: {directory_path} (画像{image_count}枚, 総ファイル{total_files}件)"
            )
            return True

        except Exception as e:
            logger.error(f"ディレクトリ検証中にエラー: {directory_path} - {e}")
            return False

    def set_label_text(self, text: str) -> None:
        self.DirectoryPicker.set_label_text(text)

    def get_selected_path(self) -> str:
        return self.DirectoryPicker.lineEditPicker.text()

    def set_path(self, path: str) -> None:
        self.DirectoryPicker.lineEditPicker.setText(path)

    def on_path_changed(self, new_path: str) -> None:
        print(f"Selected directory changed: {new_path}")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    from ...utils.log import logger

    logconf = {"level": "DEBUG", "file": "DirectoryPickerWidget.log"}
    import sys

    app = QApplication(sys.argv)
    widget = DirectoryPickerWidget()  # type: ignore
    widget.set_label_text("Select Folder")  # type: ignore
    widget.show()
    sys.exit(app.exec())
