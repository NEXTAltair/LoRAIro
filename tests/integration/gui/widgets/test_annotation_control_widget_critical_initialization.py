"""AnnotationControlWidget致命的初期化エラーテスト

テスト対象:
- ModelSelectionTableWidget設定失敗時のCriticalInitializationError発生
- SearchFilterService未設定時のエラー
- シグナル接続失敗時のエラー

テスト戦略:
- 統合テスト: モックのみ使用（test_strategy_policy_change_2025_11_06準拠）
- CriticalInitializationError例外の検証
- ヘッドレス環境対応: QT_QPA_PLATFORM=offscreen で実行可能
"""

from unittest.mock import MagicMock, Mock

import pytest

from lorairo.gui.widgets.annotation_control_widget import (
    AnnotationControlWidget,
    CriticalInitializationError,
)


@pytest.mark.integration
@pytest.mark.gui
class TestAnnotationControlWidgetCriticalInitialization:
    """AnnotationControlWidget致命的初期化エラーテスト"""

    def test_model_selection_table_signal_connection_failure(self, qtbot, monkeypatch):
        """ModelSelectionTableWidgetシグナル接続失敗時のCriticalInitializationError発生テスト

        検証項目:
        - CriticalInitializationErrorが発生すること
        - component_nameが"ModelSelectionTableWidget"であること
        - original_errorが適切に保持されること
        """

        # setupUi()をモック（modelSelectionTableを不完全な状態で作成）
        def mock_setupui(ui_self, widget_instance):
            # model_selection_changedシグナルが存在しないmockを作成
            mock_table = Mock(spec=[])  # 空のspecでシグナル不存在
            widget_instance.modelSelectionTable = mock_table

            # 他の必須属性
            widget_instance.checkBoxCaption = Mock()
            widget_instance.checkBoxTagger = Mock()
            widget_instance.checkBoxScorer = Mock()
            widget_instance.checkBoxWebAPI = Mock()
            widget_instance.checkBoxLocal = Mock()
            widget_instance.checkBoxLowResolution = Mock()
            widget_instance.checkBoxBatchMode = Mock()
            widget_instance.pushButtonStart = Mock()

        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui,
        )

        # AnnotationControlWidget初期化を試みる（CriticalInitializationError発生）
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = AnnotationControlWidget()
            qtbot.addWidget(widget)

        # 検証1: component_nameが正しいこと
        assert exc_info.value.component_name == "ModelSelectionTableWidget"

        # 検証2: original_errorが保持されていること
        assert exc_info.value.original_error is not None

        # 検証3: エラーメッセージに"model_selection_changed"が含まれること
        assert "model_selection_changed" in str(
            exc_info.value.original_error
        ).lower() or "AttributeError" in str(type(exc_info.value.original_error))

    def test_search_filter_service_not_set_on_load_models(self, qtbot, monkeypatch):
        """SearchFilterService未設定時のload_models()失敗テスト

        検証項目:
        - set_search_filter_service()呼び出し時にload_models()が実行される
        - SearchFilterService未設定時にRuntimeErrorが発生すること
        """

        # setupUi()をモック（正常なmodelSelectionTableを作成）
        def mock_setupui(ui_self, widget_instance):
            mock_table = MagicMock()
            # load_models()でRuntimeErrorを投げるように設定
            mock_table.load_models.side_effect = RuntimeError(
                "SearchFilterService not available for model loading"
            )
            widget_instance.modelSelectionTable = mock_table

            # 他の必須属性
            widget_instance.checkBoxCaption = Mock()
            widget_instance.checkBoxTagger = Mock()
            widget_instance.checkBoxScorer = Mock()
            widget_instance.checkBoxWebAPI = Mock()
            widget_instance.checkBoxLocal = Mock()
            widget_instance.checkBoxLowResolution = Mock()
            widget_instance.checkBoxBatchMode = Mock()
            widget_instance.pushButtonStart = Mock()

        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui,
        )

        # AnnotationControlWidget初期化（成功）
        widget = AnnotationControlWidget()
        qtbot.addWidget(widget)

        # SearchFilterService設定時にload_models()が呼ばれ、RuntimeError発生
        mock_service = Mock()

        # set_search_filter_service()内でload_models()が呼ばれる
        # load_models()はRuntimeErrorを投げる設定
        with pytest.raises(RuntimeError) as exc_info:
            widget.set_search_filter_service(mock_service)

        # 検証: エラーメッセージが正しいこと
        assert "SearchFilterService not available" in str(exc_info.value)

    def test_unexpected_error_during_initialization(self, qtbot, monkeypatch):
        """予期しないエラー発生時のCriticalInitializationError変換テスト

        検証項目:
        - 任意の例外がCriticalInitializationErrorに変換されること
        - component_nameが"AnnotationControlWidget"であること
        """

        # setupUi()で予期しない例外を投げる
        def mock_setupui_with_unexpected_error(*args, **kwargs):
            raise ValueError("Unexpected error during setupUi")

        monkeypatch.setattr(
            "lorairo.gui.designer.AnnotationControlWidget_ui.Ui_AnnotationControlWidget.setupUi",
            mock_setupui_with_unexpected_error,
        )

        # AnnotationControlWidget初期化を試みる（CriticalInitializationError発生）
        with pytest.raises(CriticalInitializationError) as exc_info:
            widget = AnnotationControlWidget()
            qtbot.addWidget(widget)

        # 検証1: component_nameが正しいこと
        assert exc_info.value.component_name == "AnnotationControlWidget"

        # 検証2: original_errorがValueErrorであること
        assert isinstance(exc_info.value.original_error, ValueError)

        # 検証3: エラーメッセージが保持されていること
        assert "Unexpected error" in str(exc_info.value.original_error)
