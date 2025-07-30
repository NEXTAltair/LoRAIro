import argparse
import os
import platform
import sys
import warnings

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from .gui.window.main_workspace_window import MainWorkspaceWindow
from .utils.config import get_config
from .utils.log import initialize_logging, logger


def setup_qt_environment(config=None):
    """Qt環境の設定とフォント問題の解決"""
    qt_config = config.get("qt", {}) if config else {}

    # 警告抑制設定
    if qt_config.get("suppress_warnings", True):
        warnings.filterwarnings("ignore", message=".*propagateSizeHints.*")
        warnings.filterwarnings("ignore", message=".*QFontDatabase.*")

    # 設定ファイルからの環境変数オーバーライド
    if qt_config.get("platform"):
        os.environ["QT_QPA_PLATFORM"] = qt_config["platform"]

    if qt_config.get("font_dir"):
        os.environ["QT_QPA_FONTDIR"] = qt_config["font_dir"]

    # プラットフォーム別フォントディレクトリ設定
    system = platform.system()

    if system == "Windows":
        # Windowsシステムフォントディレクトリ
        font_dirs = [
            "C:/Windows/Fonts",
            os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"),
        ]
        # 存在するフォントディレクトリを設定
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                os.environ["QT_QPA_FONTDIR"] = font_dir
                break

        # プラットフォームプラグイン設定
        os.environ["QT_QPA_PLATFORM"] = "windows"

    elif system == "Linux":
        # Linuxシステムフォントディレクトリ
        font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "/system/fonts",  # Android
            os.path.expanduser("~/.fonts"),
        ]
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                os.environ["QT_QPA_FONTDIR"] = font_dir
                break

        # WSL/コンテナ環境でのヘッドレス対応
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

    elif system == "Darwin":  # macOS
        # macOSシステムフォントディレクトリ
        font_dirs = [
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts"),
        ]
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                os.environ["QT_QPA_FONTDIR"] = font_dir
                break


def setup_application_fonts(app: QApplication, config=None):
    """アプリケーションフォントの設定"""
    try:
        qt_config = config.get("qt", {}) if config else {}

        # 利用可能なフォント一覧を取得
        families = QFontDatabase.families()

        # 設定ファイルからの指定フォント確認
        preferred_fonts = []
        if qt_config.get("default_font"):
            preferred_fonts.append(qt_config["default_font"])

        # デフォルトフォントの優先順位（日本語対応含む）
        preferred_fonts.extend(
            [
                "Arial",
                "Helvetica",
                "Segoe UI",
                "DejaVu Sans",
                "Liberation Sans",
                "Noto Sans",
                "MS Gothic",
                "Yu Gothic",
                "Hiragino Sans",
            ]
        )

        # 利用可能なフォントから最適なものを選択
        selected_font = None
        for font_name in preferred_fonts:
            if font_name in families:
                selected_font = font_name
                break

        # フォントが見つからない場合はシステムデフォルト
        if not selected_font and families:
            selected_font = families[0]

        if selected_font:
            # フォントサイズを設定から取得
            font_size = qt_config.get("font_size", 10)

            # アプリケーション全体のデフォルトフォント設定
            font = QFont(selected_font, font_size)
            app.setFont(font)
            logger.info(f"アプリケーションフォント設定: {selected_font} ({font_size}pt)")
        else:
            logger.warning("適切なフォントが見つかりません。システムデフォルトを使用します。")

    except Exception as e:
        logger.warning(f"フォント設定でエラーが発生しました: {e}")


def parse_arguments():
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="LoRAIro - LoRA/Finetune用画像データセット管理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  lorairo                    # ワークスペースGUIで起動
  lorairo --debug           # デバッグモードで起動
  lorairo --version         # バージョン表示
        """,
    )

    parser.add_argument("--version", action="version", version="LoRAIro 2.0.0")

    parser.add_argument("--debug", action="store_true", help="デバッグモードで起動")

    return parser.parse_args()


def main() -> None:
    """メイン実行関数"""
    # コマンドライン引数解析
    args = parse_arguments()

    # 設定読み込み（Qt環境設定前に必要）
    config = get_config()

    # Qt環境設定（QApplication作成前に実行）
    setup_qt_environment(config)

    # デバッグモード設定
    if args.debug:
        config["log"]["level"] = "DEBUG"

    # ログ初期化
    initialize_logging(config["log"])

    logger.info("=" * 60)
    logger.info("LoRAIro ワークスペースGUI 起動")
    logger.info("ワークフロー中心のインターフェースを使用")
    logger.info("=" * 60)

    # Qt Application作成
    app = QApplication(sys.argv)
    app.setApplicationName("LoRAIro")
    app.setApplicationVersion("2.0.0")

    # アプリケーションフォント設定
    setup_application_fonts(app, config)

    # デバッグモード時のQt環境情報表示
    if args.debug or config.get("qt", {}).get("enable_debug", False):
        logger.debug("Qt環境情報:")
        logger.debug(f"  Qt版本: {app.applicationVersion() or 'Unknown'}")
        logger.debug(f"  プラットフォーム: {platform.system()}")
        logger.debug(f"  QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'Not set')}")
        logger.debug(f"  QT_QPA_FONTDIR: {os.environ.get('QT_QPA_FONTDIR', 'Not set')}")
        logger.debug(f"  DISPLAY: {os.environ.get('DISPLAY', 'Not set')}")
        # 利用可能フォント一覧（デバッグ時のみ）
        from PySide6.QtGui import QFontDatabase

        families = QFontDatabase.families()
        logger.debug(f"  利用可能フォント数: {len(families)}")
        if families:
            logger.debug(f"  利用可能フォント例: {families[:5]}")

    try:
        # MainWorkspaceWindow作成・表示
        logger.info("MainWorkspaceWindow を作成中...")
        window = MainWorkspaceWindow()

        logger.info("ワークスペースGUI の作成完了")
        window.show()

        # 起動成功ログ
        logger.info("LoRAIro ワークスペースGUI 起動完了")

        # GUI実行
        exit_code = app.exec()
        logger.info(f"アプリケーション終了 (終了コード: {exit_code})")

        return exit_code

    except Exception as e:
        logger.error(f"アプリケーション起動エラー: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
