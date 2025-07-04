import sys

from PySide6.QtWidgets import QApplication

from gui.window.main_window import MainWindow


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    from pathlib import Path

    # プロジェクトのルートディレクトリをモジュール検索パスに追加
    project_root = Path(__file__).parent
    sys.path.append(str(project_root))

    main()
