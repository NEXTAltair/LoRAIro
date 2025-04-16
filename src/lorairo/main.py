import sys

from PySide6.QtWidgets import QApplication

from .gui.window.main_window import MainWindow


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
