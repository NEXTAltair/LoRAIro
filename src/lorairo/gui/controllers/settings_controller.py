# src/lorairo/gui/controllers/settings_controller.py
"""設定ダイアログ表示制御Controller

MainWindowの`open_settings`メソッドから分離。
設定ダイアログの表示とライフサイクル管理を担当。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QWidget

from ...utils.log import logger

if TYPE_CHECKING:
    from ...services.configuration_service import ConfigurationService


class SettingsController:
    """設定ダイアログ表示制御Controller

    Args:
        config_service: 設定管理サービス
        parent: 親ウィンドウ（MainWindow）
    """

    def __init__(
        self,
        config_service: ConfigurationService | None,
        parent: QWidget | None = None,
    ) -> None:
        self.config_service = config_service
        self.parent = parent

    def _validate_services(self) -> bool:
        """必須サービスの検証

        Returns:
            bool: 全サービスが有効な場合True
        """
        if not self.config_service:
            logger.warning("ConfigurationServiceが初期化されていません")
            if self.parent:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self.parent,
                    "サービス未初期化",
                    "ConfigurationServiceが初期化されていないため、設定を開けません。",
                )
            return False

        return True

    def open_settings_dialog(self) -> None:
        """設定ダイアログを開く

        ConfigurationServiceを使用して設定ダイアログを表示します。
        """
        logger.info("設定ダイアログを開きます")

        # Step 1: サービス検証
        if not self._validate_services():
            return

        try:
            # ConfigurationWindow実装を使用
            from ..windows.configuration_window import ConfigurationWindow

            dialog = ConfigurationWindow(parent=self.parent)
            dialog.setModal(True)
            result = dialog.exec()

            if result == QDialog.DialogCode.Accepted:
                logger.info("設定が保存されました")
            else:
                logger.info("設定ダイアログがキャンセルされました")

        except ImportError:
            logger.warning("ConfigurationWindowが見つかりません - 代替実装を使用します")
            self._show_simple_settings_dialog()
        except Exception as e:
            logger.error(f"設定ダイアログの表示に失敗しました: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self.parent, "エラー", f"設定ダイアログの表示中にエラーが発生しました:\n\n{e}"
            )

    def _show_simple_settings_dialog(self) -> None:
        """シンプルな設定ダイアログを表示（フォールバック）

        ConfigurationWindowが利用できない場合の代替実装。
        """
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(
            self.parent,
            "設定",
            "設定画面は開発中です。\n現在は config/lorairo.toml ファイルを直接編集してください。",
        )
        logger.info("シンプルな設定ダイアログを表示しました")
