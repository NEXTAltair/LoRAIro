"""ModelSelectionTableWidget致命的初期化エラーテスト

テスト対象:
- SearchFilterService未設定時のload_models()失敗
- モデル取得失敗時の例外伝播

テスト戦略:
- 統合テスト: モックのみ使用（test_strategy_policy_change_2025_11_06準拠）
- RuntimeError/Exception例外の検証
- ヘッドレス環境対応: QT_QPA_PLATFORM=offscreen で実行可能
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.widgets.model_selection_table_widget import ModelSelectionTableWidget


@pytest.mark.integration
@pytest.mark.gui
class TestModelSelectionTableWidgetCriticalInitialization:
    """ModelSelectionTableWidget致命的初期化エラーテスト"""

    def test_load_models_without_search_filter_service(self, qtbot):
        """SearchFilterService未設定時のload_models()失敗テスト

        検証項目:
        - RuntimeErrorが発生すること
        - エラーメッセージに"SearchFilterService not available"が含まれること
        """
        # ModelSelectionTableWidget作成（SearchFilterService未設定）
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)

        # load_models()呼び出し（RuntimeError発生）
        with pytest.raises(RuntimeError) as exc_info:
            widget.load_models()

        # 検証: エラーメッセージが正しいこと
        assert "SearchFilterService not available" in str(exc_info.value)

    def test_load_models_service_exception_propagation(self, qtbot):
        """SearchFilterService.get_annotation_models_list()失敗時の例外伝播テスト

        検証項目:
        - SearchFilterServiceの例外が握りつぶされず伝播すること
        - 元の例外型が保持されること
        """
        # ModelSelectionTableWidget作成
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)

        # モックSearchFilterService（get_annotation_models_list()で例外）
        mock_service = Mock()
        mock_service.get_annotation_models_list.side_effect = ConnectionError("API connection failed")

        # SearchFilterService設定
        widget.set_search_filter_service(mock_service)

        # load_models()呼び出し（ConnectionError発生）
        with pytest.raises(ConnectionError) as exc_info:
            widget.load_models()

        # 検証1: 元の例外型が保持されていること
        assert isinstance(exc_info.value, ConnectionError)

        # 検証2: エラーメッセージが保持されていること
        assert "API connection failed" in str(exc_info.value)

    def test_load_models_empty_list_handling(self, qtbot):
        """モデルリストが空の場合の正常動作テスト

        検証項目:
        - 空リストでも例外が発生しないこと
        - models_loadedシグナルが0件で発火すること
        """
        # ModelSelectionTableWidget作成
        widget = ModelSelectionTableWidget()
        qtbot.addWidget(widget)

        # モックSearchFilterService（空リスト返却）
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = []

        # SearchFilterService設定
        widget.set_search_filter_service(mock_service)

        # シグナル接続（テスト用）
        models_loaded_count = []
        widget.models_loaded.connect(lambda count: models_loaded_count.append(count))

        # load_models()呼び出し（例外発生しない）
        widget.load_models()

        # 検証1: models_loadedシグナルが発火したこと
        assert len(models_loaded_count) == 1

        # 検証2: カウントが0であること
        assert models_loaded_count[0] == 0

        # 検証3: all_modelsが空リストであること
        assert widget.all_models == []
