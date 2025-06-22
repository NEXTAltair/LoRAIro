import sys

from PySide6.QtWidgets import QApplication

from .gui.window.main_window import MainWindow
from .utils.config import get_config
from .utils.log import initialize_logging


def main() -> None:
    config = get_config()
    initialize_logging(config["log"])
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
