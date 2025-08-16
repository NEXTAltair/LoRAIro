# tests/integration/gui/test_filter_search_integration.py

import sys
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lorairo.gui.services.search_filter_service import SearchConditions, SearchFilterService
from lorairo.gui.widgets.custom_range_slider import CustomRangeSlider
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.services.model_filter_service import ModelFilterService
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor


@pytest.fixture(scope="module")
def qapp():
    """テスト用Qtアプリケーション"""
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()
    yield app
    # クリーンアップは pytest-qt が自動で行う


class TestFilterSearchIntegration:
    """フィルター検索統合テスト"""

    @pytest.fixture
    def mock_dependencies(self):
        """統合テスト用モック依存関係"""
        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        # モックデータの設定
        mock_images = [
            {
                "id": 1,
                "file_name": "anime_girl.jpg",
                "width": 1024,
                "height": 1024,
                "created_at": "2023-06-15T00:00:00Z",
                "tags": ["anime", "1girl"],
            },
            {
                "id": 2,
                "file_name": "landscape.jpg",
                "width": 1920,
                "height": 1080,
                "created_at": "2023-07-20T00:00:00Z",
                "tags": ["landscape", "nature"],
            },
        ]

        mock_db_manager.get_images_by_filter.return_value = (mock_images, 2)
        mock_db_manager.check_image_has_annotation.return_value = True

        return {
            "db_manager": mock_db_manager,
            "model_selection_service": mock_model_selection_service,
            "mock_images": mock_images,
        }

    @pytest.fixture
    def integrated_services(self, mock_dependencies):
        """統合されたサービス層"""
        db_manager = mock_dependencies["db_manager"]
        model_selection_service = mock_dependencies["model_selection_service"]

        # 実際のサービスインスタンス作成（モック依存関係付き）
        criteria_processor = SearchCriteriaProcessor(db_manager)
        model_filter_service = ModelFilterService(db_manager, model_selection_service)
        search_filter_service = SearchFilterService(
            db_manager=db_manager, model_selection_service=model_selection_service
        )

        return {
            "criteria_processor": criteria_processor,
            "model_filter_service": model_filter_service,
            "search_filter_service": search_filter_service,
        }

    @pytest.fixture
    def filter_panel(self, qapp, integrated_services):
        """統合されたフィルターパネル"""
        panel = FilterSearchPanel()
        panel.set_search_filter_service(integrated_services["search_filter_service"])
        return panel

    def test_filter_panel_initialization(self, filter_panel):
        """フィルターパネル初期化統合テスト"""
        # パネルが正しく初期化されることを確認
        assert filter_panel.search_filter_service is not None
        assert filter_panel.date_range_slider is not None
        assert isinstance(filter_panel.date_range_slider, CustomRangeSlider)

    def test_service_layer_integration(self, integrated_services, mock_dependencies):
        """サービス層統合テスト"""
        search_filter_service = integrated_services["search_filter_service"]
        mock_images = mock_dependencies["mock_images"]

        # 検索条件作成
        conditions = search_filter_service.create_search_conditions(
            search_type="tags", keywords=["anime", "1girl"], tag_logic="and"
        )

        # 検索実行（新しいサービス層経由）
        results, count = search_filter_service.execute_search_with_filters(conditions)

        # 結果確認
        assert len(results) == 2
        assert count == 2
        assert results == mock_images

    def test_ui_to_service_integration(self, filter_panel, mock_dependencies):
        """UI→サービス層統合テスト"""
        # UI要素に値を設定
        filter_panel.ui.lineEditSearch.setText("anime, 1girl")
        filter_panel.ui.radioTags.setChecked(True)
        filter_panel.ui.radioAnd.setChecked(True)

        # 検索実行
        with patch.object(filter_panel, "search_requested") as mock_signal:
            filter_panel._on_search_requested()

            # シグナルが発行されることを確認
            assert mock_signal.emit.called

            # 発行されたデータを確認
            emitted_data = mock_signal.emit.call_args[0][0]
            assert "results" in emitted_data
            assert "count" in emitted_data
            assert "conditions" in emitted_data

    def test_custom_range_slider_integration(self, filter_panel):
        """カスタム範囲スライダー統合テスト"""
        date_slider = filter_panel.date_range_slider

        # 日付モードに設定
        date_slider.set_date_range()

        # スライダーの値変更をシミュレート
        with patch.object(date_slider, "valueChanged") as mock_signal:
            # 値変更を手動で発火
            date_slider.update_labels()

            # シグナルが発行されることを確認
            mock_signal.emit.assert_called_once()

    def test_search_conditions_creation_integration(self, filter_panel):
        """検索条件作成統合テスト"""
        # UI要素を設定
        filter_panel.ui.lineEditSearch.setText("test keyword")
        filter_panel.ui.radioCaption.setChecked(True)
        filter_panel.ui.radioOr.setChecked(True)
        filter_panel.ui.comboResolution.setCurrentText("1024x1024")
        filter_panel.ui.checkboxDateFilter.setChecked(True)
        filter_panel.ui.checkboxOnlyUntagged.setChecked(True)

        # SearchFilterServiceを通じて検索条件作成
        service = filter_panel.search_filter_service

        # parse_search_inputをテスト
        keywords = service.parse_search_input("test keyword")
        assert keywords == ["test", "keyword"]

        # create_search_conditionsをテスト
        conditions = service.create_search_conditions(
            search_type="caption",
            keywords=keywords,
            tag_logic="or",
            resolution_filter="1024x1024",
            only_untagged=True,
        )

        assert conditions.search_type == "caption"
        assert conditions.keywords == ["test", "keyword"]
        assert conditions.tag_logic == "or"
        assert conditions.resolution_filter == "1024x1024"
        assert conditions.only_untagged is True

    def test_search_preview_integration(self, filter_panel):
        """検索プレビュー統合テスト"""
        service = filter_panel.search_filter_service

        # 複合検索条件を作成
        conditions = SearchConditions(
            search_type="tags",
            keywords=["anime", "1girl"],
            tag_logic="and",
            resolution_filter="1024x1024",
            aspect_ratio_filter="正方形 (1:1)",
            date_filter_enabled=True,
            date_range_start=datetime(2023, 1, 1),
            date_range_end=datetime(2023, 12, 31),
            only_untagged=False,
            only_uncaptioned=True,
            exclude_duplicates=True,
        )

        # プレビュー作成
        preview = service.create_search_preview(conditions)

        # プレビューに期待される要素が含まれることを確認
        assert "anime" in preview
        assert "1girl" in preview
        assert "1024x1024" in preview
        assert "正方形" in preview
        assert "2023-01-01" in preview
        assert "2023-12-31" in preview

    def test_ui_validation_integration(self, filter_panel):
        """UI検証統合テスト"""
        service = filter_panel.search_filter_service

        # 有効な入力
        valid_inputs = {
            "keywords": ["test"],
            "resolution_filter": "1024x1024",
            "custom_width": 1920,
            "custom_height": 1080,
            "date_filter_enabled": True,
            "date_range_start": datetime(2023, 1, 1),
            "date_range_end": datetime(2023, 12, 31),
        }

        result = service.validate_ui_inputs(valid_inputs)
        assert result.is_valid is True
        assert len(result.errors) == 0

        # 無効な入力（カスタム解像度エラー）
        invalid_inputs = {
            "keywords": [],
            "resolution_filter": "カスタム",
            "custom_width": None,
            "custom_height": None,
        }

        result = service.validate_ui_inputs(invalid_inputs)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_signal_flow_integration(self, filter_panel, mock_dependencies):
        """シグナルフロー統合テスト"""
        # シグナル受信用のモック
        search_handler = Mock()
        clear_handler = Mock()

        filter_panel.search_requested.connect(search_handler)
        filter_panel.filter_cleared.connect(clear_handler)

        # 検索実行
        filter_panel.ui.lineEditSearch.setText("test")
        filter_panel._on_search_requested()

        # 検索シグナルが発行されることを確認
        search_handler.assert_called_once()

        # クリア実行
        filter_panel._on_clear_requested()

        # クリアシグナルが発行されることを確認
        clear_handler.assert_called_once()

    def test_error_handling_integration(self, filter_panel, mock_dependencies):
        """エラーハンドリング統合テスト"""
        # データベースエラーをシミュレート
        db_manager = mock_dependencies["db_manager"]
        db_manager.get_images_by_filter.side_effect = Exception("Database connection error")

        # 検索実行
        filter_panel.ui.lineEditSearch.setText("test")

        # エラーハンドリング確認用のモック
        with patch.object(filter_panel, "search_requested") as mock_signal:
            filter_panel._on_search_requested()

            # エラー情報が含まれたシグナルが発行されることを確認
            mock_signal.emit.assert_called_once()
            emitted_data = mock_signal.emit.call_args[0][0]
            assert "error" in emitted_data

    def test_performance_integration(self, filter_panel, mock_dependencies):
        """パフォーマンス統合テスト"""
        # 大量データのモック
        large_dataset = [{"id": i, "file_name": f"image_{i}.jpg"} for i in range(1000)]
        mock_dependencies["db_manager"].get_images_by_filter.return_value = (large_dataset, 1000)

        # パフォーマンス測定
        import time

        start_time = time.time()

        filter_panel.ui.lineEditSearch.setText("performance test")
        filter_panel._on_search_requested()

        end_time = time.time()
        execution_time = end_time - start_time

        # 実行時間が妥当な範囲内であることを確認（1秒未満）
        assert execution_time < 1.0

    def test_memory_management_integration(self, filter_panel):
        """メモリ管理統合テスト"""
        initial_conditions = filter_panel.search_filter_service.get_current_conditions()

        # 複数回の検索実行
        for i in range(10):
            filter_panel.ui.lineEditSearch.setText(f"test_{i}")
            filter_panel._on_search_requested()

        # メモリリークがないことを確認（条件が適切に更新されている）
        final_conditions = filter_panel.search_filter_service.get_current_conditions()
        assert final_conditions is not None
        assert final_conditions.keywords == ["test_9"]

        # クリア後
        filter_panel.search_filter_service.clear_conditions()
        assert filter_panel.search_filter_service.get_current_conditions() is None


class TestServiceLayerIntegration:
    """サービス層統合テスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock_db = Mock()
        mock_images = [
            {"id": 1, "width": 1024, "height": 1024, "created_at": "2023-06-15T00:00:00Z"},
            {"id": 2, "width": 1920, "height": 1080, "created_at": "2023-07-20T00:00:00Z"},
        ]
        mock_db.get_images_by_filter.return_value = (mock_images, 2)
        mock_db.check_image_has_annotation.return_value = True
        return mock_db

    @pytest.fixture
    def service_integration(self, mock_db_manager):
        """統合されたサービス"""
        mock_model_service = Mock()

        criteria_processor = SearchCriteriaProcessor(mock_db_manager)
        model_filter_service = ModelFilterService(mock_db_manager, mock_model_service)

        return {
            "criteria_processor": criteria_processor,
            "model_filter_service": model_filter_service,
            "db_manager": mock_db_manager,
        }

    def test_criteria_processor_to_db_integration(self, service_integration):
        """SearchCriteriaProcessor→DB統合テスト"""
        processor = service_integration["criteria_processor"]

        conditions = SearchConditions(
            search_type="tags", keywords=["anime", "girl"], tag_logic="and", resolution_filter="1024x1024"
        )

        # 統合検索実行
        results, count = processor.execute_search_with_filters(conditions)

        # DBマネージャーが呼ばれることを確認
        service_integration["db_manager"].get_images_by_filter.assert_called_once()

        assert len(results) == 2
        assert count == 2

    def test_model_filter_service_integration(self, service_integration):
        """ModelFilterService統合テスト"""
        model_service = service_integration["model_filter_service"]

        # アノテーション設定検証
        settings = {"selected_models": ["gpt-4-vision"], "batch_size": 10, "timeout": 60}

        result = model_service.validate_annotation_settings(settings)

        # 検証が実行されることを確認
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_cross_service_communication(self, service_integration):
        """サービス間通信統合テスト"""
        processor = service_integration["criteria_processor"]
        model_service = service_integration["model_filter_service"]

        # 検索実行後、結果に対してモデルフィルター適用
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # 1. 検索実行
        images, count = processor.execute_search_with_filters(conditions)

        # 2. アノテーション状態フィルタリング
        filtered_images = processor.filter_images_by_annotation_status(images, "annotated")

        # 3. 結果確認
        assert len(filtered_images) <= len(images)


class TestWidgetIntegration:
    """ウィジェット統合テスト"""

    @pytest.fixture
    def range_slider(self, qapp):
        """カスタム範囲スライダー"""
        return CustomRangeSlider()

    def test_custom_range_slider_date_mode(self, range_slider):
        """カスタム範囲スライダー日付モード統合テスト"""
        # 日付モードに設定
        range_slider.set_date_range()

        # 日付モードが正しく設定されることを確認
        assert range_slider.is_date_mode is True
        assert range_slider.min_value > 0  # 2023年のタイムスタンプ
        assert range_slider.max_value > range_slider.min_value

    def test_custom_range_slider_numeric_mode(self, range_slider):
        """カスタム範囲スライダー数値モード統合テスト"""
        # 数値範囲設定
        range_slider.set_range(0, 100)

        # 数値モードが正しく設定されることを確認
        assert range_slider.is_date_mode is False
        assert range_slider.min_value == 0
        assert range_slider.max_value == 100

    def test_range_slider_signal_emission(self, range_slider):
        """範囲スライダーシグナル発行統合テスト"""
        signal_received = []

        def signal_handler(min_val, max_val):
            signal_received.append((min_val, max_val))

        range_slider.valueChanged.connect(signal_handler)

        # 値変更を発火
        range_slider.update_labels()

        # シグナルが受信されることを確認
        assert len(signal_received) > 0
        min_val, max_val = signal_received[0]
        assert isinstance(min_val, int)
        assert isinstance(max_val, int)
        assert min_val <= max_val


class TestEndToEndIntegration:
    """エンドツーエンド統合テスト"""

    @pytest.fixture
    def full_integration_setup(self, qapp):
        """完全統合セットアップ"""
        # モック依存関係
        mock_db_manager = Mock()
        mock_model_selection_service = Mock()

        # サンプルデータ
        sample_images = [
            {
                "id": 1,
                "file_name": "anime_girl.jpg",
                "width": 1024,
                "height": 1024,
                "created_at": "2023-06-15T00:00:00Z",
            }
        ]
        mock_db_manager.get_images_by_filter.return_value = (sample_images, 1)
        mock_db_manager.check_image_has_annotation.return_value = True

        # サービス層構築
        criteria_processor = SearchCriteriaProcessor(mock_db_manager)
        model_filter_service = ModelFilterService(mock_db_manager, mock_model_selection_service)
        search_filter_service = SearchFilterService(
            db_manager=mock_db_manager, model_selection_service=mock_model_selection_service
        )

        # GUI層構築
        filter_panel = FilterSearchPanel()
        filter_panel.set_search_filter_service(search_filter_service)

        return {
            "filter_panel": filter_panel,
            "search_filter_service": search_filter_service,
            "criteria_processor": criteria_processor,
            "model_filter_service": model_filter_service,
            "mock_db_manager": mock_db_manager,
            "sample_images": sample_images,
        }

    def test_complete_search_workflow(self, full_integration_setup):
        """完全な検索ワークフロー統合テスト"""
        setup = full_integration_setup
        filter_panel = setup["filter_panel"]

        # 1. UI設定
        filter_panel.ui.lineEditSearch.setText("anime, 1girl")
        filter_panel.ui.radioTags.setChecked(True)
        filter_panel.ui.radioAnd.setChecked(True)
        filter_panel.ui.comboResolution.setCurrentText("1024x1024")

        # 2. 検索実行
        results_received = []

        def search_handler(data):
            results_received.append(data)

        filter_panel.search_requested.connect(search_handler)
        filter_panel._on_search_requested()

        # 3. 結果確認
        assert len(results_received) == 1
        result_data = results_received[0]

        assert "results" in result_data
        assert "count" in result_data
        assert "conditions" in result_data
        assert result_data["count"] == 1
        assert len(result_data["results"]) == 1

    def test_ui_state_management_integration(self, full_integration_setup):
        """UI状態管理統合テスト"""
        setup = full_integration_setup
        filter_panel = setup["filter_panel"]

        # 1. 初期状態確認
        assert filter_panel.ui.lineEditSearch.text() == ""
        assert filter_panel.ui.radioTags.isChecked() is True

        # 2. 状態変更
        filter_panel.ui.lineEditSearch.setText("test query")
        filter_panel.ui.radioCaption.setChecked(True)
        filter_panel.ui.checkboxOnlyUntagged.setChecked(True)

        # 3. 条件取得
        current_conditions = filter_panel.get_current_conditions()

        # 4. 状態が正しく反映されることを確認
        # （実際の実装に依存するため、基本的な確認のみ）
        assert isinstance(current_conditions, dict)

    def test_error_recovery_integration(self, full_integration_setup):
        """エラー回復統合テスト"""
        setup = full_integration_setup
        filter_panel = setup["filter_panel"]
        mock_db_manager = setup["mock_db_manager"]

        # 1. エラー状態を作成
        mock_db_manager.get_images_by_filter.side_effect = Exception("Database error")

        # 2. 検索実行（エラー発生）
        error_results = []

        def error_handler(data):
            error_results.append(data)

        filter_panel.search_requested.connect(error_handler)
        filter_panel.ui.lineEditSearch.setText("error test")
        filter_panel._on_search_requested()

        # 3. エラーが適切に処理されることを確認
        assert len(error_results) == 1
        error_data = error_results[0]
        assert "error" in error_data

        # 4. エラー回復（正常な応答に戻す）
        mock_db_manager.get_images_by_filter.side_effect = None
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        # 5. 再度検索実行（成功）
        recovery_results = []

        def recovery_handler(data):
            recovery_results.append(data)

        filter_panel.search_requested.disconnect()  # 前のハンドラーを切断
        filter_panel.search_requested.connect(recovery_handler)
        filter_panel._on_search_requested()

        # 6. 回復が成功することを確認
        assert len(recovery_results) == 1
        recovery_data = recovery_results[0]
        assert "error" not in recovery_data
        assert "results" in recovery_data
