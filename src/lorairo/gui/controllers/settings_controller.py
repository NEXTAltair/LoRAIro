# src/lorairo/gui/controllers/settings_controller.py
"""設定ダイアログ表示制御Controller

MainWindowの`open_settings`メソッドから分離。
設定ダイアログの表示とライフサイクル管理を担当。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QWidget

from ...utils.log import logger
from ..message_box import show_critical, show_warning

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
                show_warning(
                    self.parent,
                    "サービス未初期化",
                    "ConfigurationServiceが初期化されていないため、設定を開けません。",
                )
            return False

        return True

    def open_settings_dialog(self, highlight_provider: str | None = None) -> bool:
        """設定ダイアログを開く

        ConfigurationServiceを使用して設定ダイアログを表示します。

        Args:
            highlight_provider: 指定すると該当 provider の API キー欄を
                ハイライト・フォーカスした状態で開く (Issue #755: モデルピッカーの
                ``○ needs key`` チップからの往復導線)。

        Returns:
            bool: ユーザーが OK で確定し設定が保存された場合 True、
                Cancel・例外で確定しなかった場合 False。
                Issue #249: 呼び出し元 (MainWindow) が True 時に依存ウィジェット
                (ModelSelectionWidget 等) を reload するための戻り値。
        """
        logger.info("設定ダイアログを開きます")

        # Step 1: サービス検証
        if not self._validate_services():
            return False

        try:
            # ConfigurationWindow実装を使用
            from ..window.configuration_window import ConfigurationWindow

            assert self.config_service is not None  # _validate_services()で検証済み
            dialog = ConfigurationWindow(config_service=self.config_service, parent=self.parent)
            dialog.setModal(True)
            if highlight_provider:
                dialog.focus_api_key_field(highlight_provider)
            result = dialog.exec()

            if result == QDialog.DialogCode.Accepted:
                logger.info("設定が保存されました")
                return True
            logger.info("設定ダイアログがキャンセルされました")
            return False

        except Exception as e:
            logger.opt(exception=True).error(f"設定ダイアログの表示に失敗しました: {e}")

            show_critical(self.parent, "エラー", f"設定ダイアログの表示中にエラーが発生しました:\n\n{e}")
            return False
