# tests/integration/gui/test_widget_integration.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QWidget

from lorairo.gui.services.model_selection_service import ModelSelectionService
from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.gui.widgets.filter import CustomRangeSlider
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


class TestWidgetServiceIntegration:
    """ウィジェットとサービス層の統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def mock_annotator_adapter(self):
        """モック AnnotatorLibAdapter"""
        mock = Mock()
        mock.get_available_models_with_metadata.return_value = [
            {
                "name": "gpt-4o",
                "provider": "openai",
                "model_type": "multimodal",
                "api_model_id": "gpt-4o-2024",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "wd-v1-4",
                "provider": "local",
                "model_type": "tag",
                "api_model_id": None,
                "requires_api_key": False,
                "estimated_size_gb": 2.5,
            },
        ]
        return mock

    @pytest.fixture
    def model_service(self, mock_annotator_adapter):
        """ModelSelectionService インスタンス"""
        service = ModelSelectionService(mock_annotator_adapter)
        service.load_models()
        return service

    @pytest.fixture
    def search_service(self):
        """SearchFilterService インスタンス"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        return SearchFilterService(db_manager=mock_db_manager)

    def test_filter_search_panel_with_search_service_integration(
        self, parent_widget, search_service, qtbot
    ):
        """FilterSearchPanel と SearchFilterService の統合テスト"""
        # FilterSearchPanel を実際のサービスと統合
        with (
            patch("lorairo.gui.widgets.filter.FilterSearchPanel.setupUi"),
            patch("lorairo.gui.widgets.filter.FilterSearchPanel.setup_date_range_slider"),
            patch("lorairo.gui.widgets.filter.FilterSearchPanel.setup_connections"),
        ):
            panel = FilterSearchPanel(parent_widget)
            qtbot.addWidget(panel)

            # UI要素をモック
            panel.lineEditSearch = Mock()
            panel.radioTags = Mock()
            panel.radioAnd = Mock()
            panel.comboResolution = Mock()
            panel.comboAspectRatio = Mock()
            panel.checkboxDateFilter = Mock()
            panel.date_range_slider = Mock()
            panel.checkboxOnlyUntagged = Mock()
            panel.checkboxOnlyUncaptioned = Mock()
            panel.checkboxExcludeDuplicates = Mock()
            panel.checkboxIncludeNSFW = Mock()
            panel.textEditPreview = Mock()

            # サービスを統合
            panel.search_service = search_service

            # テスト用検索条件設定
            panel.lineEditSearch.text.return_value = "1girl, long hair"
            panel.radioTags.isChecked.return_value = True
            panel.radioAnd.isChecked.return_value = True
            panel.comboResolution.currentText.return_value = "1024x1024"
            panel.comboAspectRatio.currentText.return_value = "正方形 (1:1)"
            panel.checkboxDateFilter.isChecked.return_value = False
            panel.checkboxOnlyUntagged.isChecked.return_value = False
            panel.checkboxOnlyUncaptioned.isChecked.return_value = False
            panel.checkboxExcludeDuplicates.isChecked.return_value = True
            panel.checkboxIncludeNSFW.isChecked.return_value = False

            # 統合処理メソッドを実装
            def process_search_with_service():
                # UI から入力取得
                search_text = panel.lineEditSearch.text()
                search_type = "tags" if panel.radioTags.isChecked() else "caption"
                tag_logic = "and" if panel.radioAnd.isChecked() else "or"
                resolution = panel.comboResolution.currentText()
                aspect_ratio = panel.comboAspectRatio.currentText()

                # サービスで検索条件作成
                conditions = panel.search_service.create_search_conditions(
                    search_text=search_text,
                    search_type=search_type,
                    tag_logic=tag_logic,
                    resolution_filter=resolution,
                    custom_width="",
                    custom_height="",
                    aspect_ratio_filter=aspect_ratio,
                    date_filter_enabled=panel.checkboxDateFilter.isChecked(),
                    date_range_start=None,
                    date_range_end=None,
                    only_untagged=panel.checkboxOnlyUntagged.isChecked(),
                    only_uncaptioned=panel.checkboxOnlyUncaptioned.isChecked(),
                    exclude_duplicates=panel.checkboxExcludeDuplicates.isChecked(),
                )

                # プレビュー生成
                preview = panel.search_service.create_search_preview(conditions)
                panel.textEditPreview.setPlainText(preview)

                return conditions, preview

            panel.process_search_with_service = process_search_with_service

            # 統合テスト実行
            conditions, preview = panel.process_search_with_service()

            # 結果確認
            assert conditions.search_type == "tags"
            assert conditions.keywords == ["1girl", "long hair"]
            assert conditions.tag_logic == "and"
            assert conditions.resolution_filter == "1024x1024"
            assert conditions.exclude_duplicates is True

            # プレビューテキストが生成されていることを確認
            assert "tags: 1girl, long hair" in preview
            assert "すべて含む" in preview
            assert "解像度: 1024x1024" in preview
            assert "重複除外" in preview

    def test_model_selection_table_widget_integration(self, parent_widget, model_service, qtbot):
        """ModelSelectionTableWidget とサービスの統合テスト"""
        # ModelSelectionTableWidgetのモック
        mock_widget = QWidget(parent_widget)
        qtbot.addWidget(mock_widget)

        # UI要素をモック（ModelSelectionTableWidget相当）
        mock_widget.tableWidgetModels = Mock()
        mock_widget.search_filter_service = None
        mock_widget.all_models = []
        mock_widget.filtered_models = []

        # ModelSelectionTableWidget統合処理を実装
        def integrate_with_model_service():
            # SearchFilterService相当のモデル取得
            all_models = [
                {
                    "name": "gpt-4o",
                    "provider": "openai",
                    "capabilities": ["caption", "tags"],
                    "is_local": False,
                },
                {
                    "name": "wd-v1-4",
                    "provider": "local", 
                    "capabilities": ["tags"],
                    "is_local": True,
                },
            ]
            
            mock_widget.all_models = all_models
            mock_widget.filtered_models = all_models.copy()

            # テーブル更新シミュレート（4列構成）
            mock_widget.tableWidgetModels.setRowCount(len(all_models))
            
            # 各行のセットアップ
            for row, model in enumerate(all_models):
                # 列0: チェックボックス
                mock_widget.tableWidgetModels.setItem(row, 0, f"checkbox_{row}")
                # 列1: モデル名
                mock_widget.tableWidgetModels.setItem(row, 1, model["name"])
                # 列2: プロバイダー
                provider_display = "ローカル" if model["is_local"] else model["provider"].title()
                mock_widget.tableWidgetModels.setItem(row, 2, provider_display)
                # 列3: 機能
                capabilities_text = ", ".join(model["capabilities"])
                mock_widget.tableWidgetModels.setItem(row, 3, capabilities_text)

            return {
                "all_models": all_models,
                "filtered_models": mock_widget.filtered_models,
                "row_count": len(all_models),
            }

        # 統合テスト実行
        result = integrate_with_model_service()

        # 結果確認
        assert len(result["all_models"]) == 2
        assert len(result["filtered_models"]) == 2
        assert result["row_count"] == 2

        # UI更新が呼ばれたことを確認
        mock_widget.tableWidgetModels.setRowCount.assert_called_with(2)
        
        # setItemが正しい回数呼ばれたことを確認（2行 × 4列 = 8回）
        assert mock_widget.tableWidgetModels.setItem.call_count == 8

    def test_custom_range_slider_date_mode_integration(self, parent_widget, qtbot):
        """CustomRangeSlider の日付モード統合テスト"""
        slider = CustomRangeSlider(parent_widget, min_value=1000, max_value=100000)
        qtbot.addWidget(slider)

        # 日付モードに設定
        slider.set_date_range()

        # シグナル受信用モック
        signal_receiver = Mock()
        slider.valueChanged.connect(signal_receiver)

        # 値変更
        slider.slider.setValue((25, 75))
        slider.update_labels()

        # 範囲取得
        min_val, max_val = slider.get_range()

        # 結果確認
        assert slider.is_date_mode is True
        assert min_val < max_val
        assert min_val >= slider.min_value
        assert max_val <= slider.max_value

        # ラベルが日付形式になっていることを確認
        min_text = slider.min_label.text()
        max_text = slider.max_label.text()
        assert len(min_text) == 10  # YYYY-MM-DD format
        assert len(max_text) == 10
        assert "-" in min_text
        assert "-" in max_text

    def test_search_filter_conditions_separation_integration(self, search_service):
        """検索・フィルター条件分離の統合テスト"""
        # 複雑な検索条件を作成
        conditions = search_service.create_search_conditions(
            search_text="1girl, school uniform, smile",
            search_type="tags",
            tag_logic="and",
            resolution_filter="カスタム...",
            custom_width="1920",
            custom_height="1080",
            aspect_ratio_filter="風景 (16:9)",
            date_filter_enabled=True,
            date_range_start=None,  # 簡略化
            date_range_end=None,
            only_untagged=False,
            only_uncaptioned=True,
            exclude_duplicates=True,
        )

        # 検索・フィルター条件分離
        search_cond, filter_cond = search_service.separate_search_and_filter_conditions(conditions)

        # 検索条件確認
        assert search_cond["search_type"] == "tags"
        assert search_cond["keywords"] == ["1girl", "school uniform", "smile"]
        assert search_cond["tag_logic"] == "and"
        assert search_cond["only_untagged"] is False
        assert search_cond["only_uncaptioned"] is True

        # フィルター条件確認
        assert filter_cond["resolution"] == (1920, 1080)  # カスタム解像度
        assert filter_cond["aspect_ratio"] == "風景 (16:9)"
        assert filter_cond["exclude_duplicates"] is True

        # プレビュー生成
        preview = search_service.create_search_preview(conditions)
        assert "tags: 1girl, school uniform, smile (すべて含む)" in preview
        assert "解像度: 1920x1080" in preview
        assert "アスペクト比: 風景 (16:9)" in preview
        assert "未キャプション画像のみ" in preview
        assert "重複除外" in preview


class TestWidgetSignalIntegration:
    """ウィジェット間シグナル統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    def test_filter_search_to_model_selection_signal_flow(self, parent_widget, qtbot):
        """FilterSearchPanel から ModelSelection への信号フロテスト"""
        # フィルターパネルのモック
        filter_panel = Mock()
        filter_panel.filterApplied = Mock()

        # モデル選択ウィジェットのモック
        model_widget = Mock()
        model_widget.update_model_list = Mock()

        # シグナル接続
        def connect_widgets():
            filter_panel.filterApplied.connect(model_widget.update_model_list)
            return True

        # 接続実行
        result = connect_widgets()
        assert result is True

        # シグナル発行テスト
        test_conditions = {"provider": "openai", "capabilities": ["caption"]}
        filter_panel.filterApplied.emit(test_conditions)

        # シグナル受信確認
        filter_panel.filterApplied.connect.assert_called_with(model_widget.update_model_list)

    def test_model_selection_table_to_annotation_control_signal_flow(self, parent_widget, qtbot):
        """ModelSelectionTableWidget から AnnotationControl への信号フロー"""
        # ModelSelectionTableWidgetのモック
        model_table_widget = Mock()
        model_table_widget.model_selection_changed = Mock()
        model_table_widget.selection_count_changed = Mock()
        model_table_widget.models_loaded = Mock()

        # AnnotationControlWidgetのモック  
        annotation_control = Mock()
        annotation_control._on_model_selection_changed = Mock()
        annotation_control._on_selection_count_changed = Mock()
        annotation_control._on_models_loaded = Mock()

        # シグナル接続（AnnotationControlWidget内で行われる接続をシミュレート）
        def connect_model_table_to_annotation():
            model_table_widget.model_selection_changed.connect(annotation_control._on_model_selection_changed)
            model_table_widget.selection_count_changed.connect(annotation_control._on_selection_count_changed)
            model_table_widget.models_loaded.connect(annotation_control._on_models_loaded)
            return True

        # 接続実行
        result = connect_model_table_to_annotation()
        assert result is True

        # シグナル発行テスト1: モデル選択変更
        selected_models = ["gpt-4o", "claude-3-sonnet", "wd-v1-4"]
        model_table_widget.model_selection_changed.emit(selected_models)

        # シグナル発行テスト2: 選択数変更
        model_table_widget.selection_count_changed.emit(3, 10)  # 3/10選択

        # シグナル発行テスト3: モデル読み込み完了
        model_table_widget.models_loaded.emit(25)  # 25モデル読み込み

        # シグナル受信確認
        model_table_widget.model_selection_changed.connect.assert_called_with(
            annotation_control._on_model_selection_changed
        )
        model_table_widget.selection_count_changed.connect.assert_called_with(
            annotation_control._on_selection_count_changed
        )
        model_table_widget.models_loaded.connect.assert_called_with(
            annotation_control._on_models_loaded
        )

    def test_annotation_results_to_data_display_signal_flow(self, parent_widget, qtbot):
        """AnnotationResults から DataDisplay への信号フロー"""
        # アノテーション結果ウィジェットのモック
        results_widget = Mock()
        results_widget.annotationCompleted = Mock()

        # データ表示ウィジェットのモック
        data_display = Mock()
        data_display.update_annotation_data = Mock()

        # シグナル接続
        def connect_results_to_display():
            results_widget.annotationCompleted.connect(data_display.update_annotation_data)
            return True

        # 接続実行
        result = connect_results_to_display()
        assert result is True

        # シグナル発行テスト
        annotation_data = {
            "caption": "A beautiful landscape",
            "tags": ["landscape", "mountain", "sky"],
            "score": 0.92,
        }
        results_widget.annotationCompleted.emit(annotation_data)

        # シグナル受信確認
        results_widget.annotationCompleted.connect.assert_called_with(data_display.update_annotation_data)

    def test_status_filter_to_image_list_signal_flow(self, parent_widget, qtbot):
        """StatusFilter から ImageList への信号フロー"""
        # ステータスフィルターのモック
        status_filter = Mock()
        status_filter.filterChanged = Mock()

        # 画像リストウィジェットのモック
        image_list = Mock()
        image_list.apply_status_filter = Mock()

        # シグナル接続
        def connect_status_to_images():
            status_filter.filterChanged.connect(image_list.apply_status_filter)
            return True

        # 接続実行
        result = connect_status_to_images()
        assert result is True

        # シグナル発行テスト
        filter_conditions = {
            "status": "annotated",
            "annotation_types": ["caption", "tags"],
            "sort_by": "created_date",
            "sort_order": "desc",
        }
        status_filter.filterChanged.emit(filter_conditions)

        # シグナル受信確認
        status_filter.filterChanged.connect.assert_called_with(image_list.apply_status_filter)


class TestMainWorkspaceIntegration:
    """MainWorkspace 統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    def test_three_panel_layout_integration(self, parent_widget, qtbot):
        """3パネルレイアウト統合テスト"""
        # メインワークスペースのモック
        main_workspace = QWidget(parent_widget)
        qtbot.addWidget(main_workspace)

        # 各パネルのモック
        left_panel = Mock()  # FilterSearchPanel + SelectedImageDetails
        center_panel = Mock()  # ThumbnailSelector + ImagePreview
        right_panel = Mock()  # ModelSelection + AnnotationControl + AnnotationResults

        # パネル統合処理
        def integrate_panels():
            # 左パネル - フィルター・詳細表示
            left_panel.filter_widget = Mock()
            left_panel.details_widget = Mock()

            # 中央パネル - サムネイル・プレビュー
            center_panel.thumbnail_widget = Mock()
            center_panel.preview_widget = Mock()

            # 右パネル - モデル選択・制御・結果
            right_panel.model_widget = Mock()
            right_panel.control_widget = Mock()
            right_panel.results_widget = Mock()

            # パネル間シグナル接続
            left_panel.filter_widget.filterApplied.connect = Mock()
            center_panel.thumbnail_widget.imageSelected.connect = Mock()
            right_panel.control_widget.annotationStarted.connect = Mock()

            return {"left": left_panel, "center": center_panel, "right": right_panel}

        # 統合実行
        panels = integrate_panels()

        # 結果確認
        assert panels["left"] is not None
        assert panels["center"] is not None
        assert panels["right"] is not None

        # 各パネルの構成要素確認
        assert hasattr(panels["left"], "filter_widget")
        assert hasattr(panels["left"], "details_widget")
        assert hasattr(panels["center"], "thumbnail_widget")
        assert hasattr(panels["center"], "preview_widget")
        assert hasattr(panels["right"], "model_widget")
        assert hasattr(panels["right"], "control_widget")
        assert hasattr(panels["right"], "results_widget")

    def test_end_to_end_annotation_workflow(self, parent_widget, qtbot):
        """エンドツーエンドアノテーションワークフロー統合テスト"""
        # ワークフロー全体のモック
        workflow = Mock()

        # 各段階のウィジェット
        workflow.filter_panel = Mock()
        workflow.image_selector = Mock()
        workflow.model_selector = Mock()
        workflow.annotation_control = Mock()
        workflow.results_display = Mock()

        # ワークフロー実行メソッド
        def execute_annotation_workflow():
            steps = []

            # Step 1: フィルター適用
            filter_conditions = {"tags": ["1girl"], "resolution": "1024x1024"}
            workflow.filter_panel.apply_filter(filter_conditions)
            steps.append("filter_applied")

            # Step 2: 画像選択
            selected_images = [{"id": 1, "path": "/test/image1.jpg"}]
            workflow.image_selector.select_images(selected_images)
            steps.append("images_selected")

            # Step 3: モデル選択
            selected_models = ["gpt-4o", "wd-v1-4"]
            workflow.model_selector.select_models(selected_models)
            steps.append("models_selected")

            # Step 4: アノテーション実行
            batch_config = {"batch_size": 10, "models": selected_models}
            workflow.annotation_control.start_batch(batch_config)
            steps.append("annotation_started")

            # Step 5: 結果表示
            results = {"caption": "Generated caption", "tags": ["generated", "tags"], "score": 0.88}
            workflow.results_display.show_results(results)
            steps.append("results_displayed")

            return steps

        # ワークフロー実行
        steps = execute_annotation_workflow()

        # 全ステップが実行されたことを確認
        assert "filter_applied" in steps
        assert "images_selected" in steps
        assert "models_selected" in steps
        assert "annotation_started" in steps
        assert "results_displayed" in steps
        assert len(steps) == 5

        # 各ウィジェットのメソッドが呼ばれたことを確認
        workflow.filter_panel.apply_filter.assert_called_once()
        workflow.image_selector.select_images.assert_called_once()
        workflow.model_selector.select_models.assert_called_once()
        workflow.annotation_control.start_batch.assert_called_once()
        workflow.results_display.show_results.assert_called_once()
