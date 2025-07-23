#!/usr/bin/env python3
# scripts/test_new_gui.py

"""
新しいGUI (MainWorkspaceWindow) の動作テスト用スクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from PySide6.QtWidgets import QApplication

from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow
from lorairo.utils.log import logger, initialize_logging
from lorairo.utils.config import get_config


def main():
    """メイン実行関数"""
    print("=" * 60)
    print("LoRAIro 新GUI動作テスト")
    print("=" * 60)

    # ログ設定
    config_data = get_config()
    log_config = config_data.get("log", {})
    initialize_logging(log_config)

    logger.info("新GUI動作テスト開始")

    # Qt Application作成
    app = QApplication(sys.argv)
    app.setApplicationName("LoRAIro")
    app.setApplicationVersion("2.0.0-dev")

    try:
        # メインウィンドウ作成
        logger.info("MainWorkspaceWindow作成中...")
        main_window = MainWorkspaceWindow()

        # ウィンドウ表示
        main_window.show()

        # ウィンドウ状態をログ出力
        window_state = main_window.get_window_state_summary()
        logger.info(f"ウィンドウ初期状態: {window_state}")

        print("\n✅ 新GUIの起動に成功しました！")
        print("\n📋 動作確認項目:")
        print("  1. ワークフローナビゲーターが表示されている")
        print("  2. データセット選択ボタンが動作する")
        print("  3. フィルター・検索パネルが表示されている")
        print("  4. サムネイルグリッドエリアが表示されている")
        print("  5. プレビュー・詳細パネルが表示されている")
        print("  6. メニューバーのアクションが動作する")
        print("  7. サムネイルサイズスライダーが動作する")
        print("  8. レイアウトモードボタンが動作する")
        print("\n🔍 テスト手順:")
        print("  - 'データセット選択'ボタンでディレクトリを選択")
        print("  - ワークフローナビゲーターのステップ確認")
        print("  - 各パネルの表示切り替え確認")
        print("  - メニューバーの各アクション確認")
        print("\n⚠️  注意: 一部機能は実装中のため動作しない場合があります")

        # GUI実行
        exit_code = app.exec()

        logger.info(f"アプリケーション終了 (終了コード: {exit_code})")
        return exit_code

    except Exception as e:
        logger.error(f"GUI起動エラー: {e}", exc_info=True)
        print(f"\n❌ エラーが発生しました: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
