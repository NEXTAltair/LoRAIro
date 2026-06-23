"""MainWindow に残る設定反映 glue の配線テスト (#868 後)。

パイプライン構成ビュー・モデル選択 SSoT・stage ピッカー往復・preset 配線・
送信前プリフライト・推論台帳・run bar の各テストは #868 で AnnotateTabWidget へ
移送した (``tests/unit/gui/tab/test_annotate_tab.py``)。本ファイルには MainWindow に
残った横断 glue (設定保存後のモデルウィジェット再読込) の検証のみを残す。
"""

from unittest.mock import Mock

import pytest


@pytest.mark.unit
class TestReloadModelWidgetAfterSettings:
    """設定保存後の ServiceContainer 再読込 + モデルウィジェット更新の検証 (#757)。"""

    def test_resets_container_config_service_and_updates_widget(self, monkeypatch):
        """container 側 config_service を破棄してアノテタブのモデル表示を更新する。

        MainWindow.config_service と ServiceContainer.config_service は別インスタンス
        のため、保存後に container 側を破棄しないと widget が stale なキー状況を見る。
        #868 でモデル選択ウィジェットは AnnotateTabWidget.batch_model_selection 経由になった。
        """
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        class _StubContainer:
            def __init__(self) -> None:
                self.config_deleted = False

            @property
            def config_service(self) -> Mock:
                return Mock()

            @config_service.deleter
            def config_service(self) -> None:
                self.config_deleted = True

        container = _StubContainer()
        monkeypatch.setattr(main_window_module, "get_service_container", lambda: container)
        mock_window = Mock()

        MainWindow._reload_model_widget_after_settings(mock_window)

        assert container.config_deleted is True
        mock_window.annotate_tab.batch_model_selection.update_model_display.assert_called_once_with()

    def test_skips_widget_update_when_annotate_tab_missing(self, monkeypatch):
        """annotate_tab が None でも container 破棄まで実施し例外を出さない。"""
        from lorairo.gui.window import main_window as main_window_module
        from lorairo.gui.window.main_window import MainWindow

        class _StubContainer:
            def __init__(self) -> None:
                self.config_deleted = False

            @property
            def config_service(self) -> Mock:
                return Mock()

            @config_service.deleter
            def config_service(self) -> None:
                self.config_deleted = True

        container = _StubContainer()
        monkeypatch.setattr(main_window_module, "get_service_container", lambda: container)
        mock_window = Mock()
        mock_window.annotate_tab = None

        # annotate_tab 未構築でも例外なく早期 return する
        MainWindow._reload_model_widget_after_settings(mock_window)

        assert container.config_deleted is True
