# tests/manual/test_main_window_manual.py
"""MainWindow手動テスト用スクリプト

Usage:
    cd /workspaces/LoRAIro-mainwindow
    uv run python tests/manual/test_main_window_manual.py
"""

import os
import platform
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from PySide6.QtWidgets import QApplication

from lorairo.gui.window.main_window import MainWindow
from lorairo.utils.config import get_config
from lorairo.utils.log import initialize_logging


def setup_test_environment() -> None:
    """テスト用Qt環境設定"""
    system = platform.system()
    if system == "Windows":
        os.environ["QT_QPA_PLATFORM"] = "windows"
        print("Windows環境: ネイティブウィンドウモード")
    elif system == "Linux":
        # devcontainer環境ではoffscreenモード
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
            print("Linux環境: offscreenモード（devcontainer想定）")
        else:
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            print("Linux環境: X11モード")
    elif system == "Darwin":
        os.environ["QT_QPA_PLATFORM"] = "cocoa"
        print("macOS環境: Cocoaモード")


if __name__ == "__main__":
    # 環境設定
    setup_test_environment()

    # 設定読み込み
    try:
        config = get_config()
        initialize_logging(config.get("log", {}))
        print("設定とログ初期化完了")
    except Exception as e:
        print(f"設定読み込みエラー (継続): {e}")
        config = {}

    # QApplication作成
    app = QApplication(sys.argv)
    app.setApplicationName("MainWindow-Test")

    try:
        # MainWindow作成
        print("MainWindow作成中...")
        window = MainWindow()

        # ウィンドウ表示の確実化
        print("ウィンドウ表示中...")
        window.show()
        window.raise_()
        window.activateWindow()
        app.processEvents()

        # 環境情報出力
        print(f"ウィンドウ表示状態: visible={window.isVisible()}")
        print(f"ウィンドウサイズ: {window.size()}")
        print(f"ウィンドウタイトル: {window.windowTitle()}")

        if window.isVisible():
            print("✅ ウィンドウ表示成功")
        else:
            print("❌ ウィンドウ表示失敗")

        print("イベントループ開始...")
        # イベントループ開始
        sys.exit(app.exec())

    except Exception as e:
        print(f"エラー: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
