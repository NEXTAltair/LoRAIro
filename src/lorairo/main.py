import argparse
import sys

from PySide6.QtWidgets import QApplication

from .gui.window.main_workspace_window import MainWorkspaceWindow
from .utils.config import get_config
from .utils.log import initialize_logging, logger


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

    # 設定読み込み
    config = get_config()

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
