"""DatasetExportWidget 単体テスト

ServiceContainer をモックして依存を分離。
QFileDialog は conftest.py の auto_mock_qfiledialog で自動モック済み。
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.widgets.dataset_export_widget import DatasetExportWidget


@pytest.fixture
def mock_service_container():
    container = Mock()
    container.dataset_export_service = Mock()
    container.dataset_export_service.validate_export_requirements.return_value = {
        "total_images": 0,
        "valid_images": 0,
        "missing_processed": 0,
        "missing_metadata": 0,
        "issues": [],
    }
    return container


@pytest.fixture
def widget_no_images(qtbot, mock_service_container):
    w = DatasetExportWidget(
        service_container=mock_service_container,
        initial_image_ids=[],
    )
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_with_images(qtbot, mock_service_container):
    w = DatasetExportWidget(
        service_container=mock_service_container,
        initial_image_ids=[1, 2, 3],
    )
    qtbot.addWidget(w)
    return w


class TestDatasetExportWidgetInit:
    def test_initialization_no_images(self, widget_no_images):
        assert widget_no_images is not None
        assert widget_no_images.image_ids == []

    def test_initialization_with_images(self, widget_with_images):
        assert widget_with_images.image_ids == [1, 2, 3]

    def test_is_modal_dialog(self, widget_with_images):
        assert widget_with_images.isModal()

    def test_window_title(self, widget_with_images):
        assert widget_with_images.windowTitle() == "データセットエクスポート"

    def test_has_export_signals(self, widget_with_images):
        assert hasattr(widget_with_images, "export_started")
        assert hasattr(widget_with_images, "export_completed")
        assert hasattr(widget_with_images, "export_error")


class TestDatasetExportWidgetNoImages:
    def test_validate_button_disabled_when_no_images(self, widget_no_images):
        assert not widget_no_images.ui.validateButton.isEnabled()

    def test_export_button_disabled_initially(self, widget_no_images):
        assert not widget_no_images.ui.exportButton.isEnabled()


class TestDatasetExportWidgetWithImages:
    def test_validate_button_enabled_with_images(self, widget_with_images):
        assert widget_with_images.ui.validateButton.isEnabled()

    def test_set_image_ids_updates_state(self, widget_no_images):
        widget_no_images.set_image_ids([10, 20])
        assert widget_no_images.image_ids == [10, 20]

    def test_validate_clears_previous_results_on_settings_change(self, widget_with_images):
        widget_with_images.validation_results = {"valid_images": 5}
        widget_with_images._on_settings_changed()
        assert widget_with_images.validation_results is None

    def test_get_selected_resolution_returns_int(self, widget_with_images):
        resolution = widget_with_images._get_selected_resolution()
        assert isinstance(resolution, int)
        assert resolution in (512, 768, 1024, 1536)

    def test_get_selected_format_returns_string(self, widget_with_images):
        fmt = widget_with_images._get_selected_format()
        assert fmt in ("txt_separate", "txt_merged", "json")


class TestDatasetExportWidgetValidation:
    def test_validate_shows_results(self, widget_with_images, mock_service_container):
        mock_service_container.dataset_export_service.validate_export_requirements.return_value = {
            "total_images": 3,
            "valid_images": 3,
            "missing_processed": 0,
            "missing_metadata": 0,
            "issues": [],
        }
        widget_with_images._on_validate_clicked()
        mock_service_container.dataset_export_service.validate_export_requirements.assert_called_once()
        assert widget_with_images.ui.exportButton.isEnabled()

    def test_validate_with_no_valid_images_disables_export(
        self, widget_with_images, mock_service_container
    ):
        """検証結果が 0 件のとき Export ボタンは無効"""
        mock_service_container.dataset_export_service.validate_export_requirements.return_value = {
            "total_images": 3,
            "valid_images": 0,
            "missing_processed": 3,
            "missing_metadata": 0,
            "issues": ["image1: missing processed"],
        }
        widget_with_images._on_validate_clicked()
        assert not widget_with_images.ui.exportButton.isEnabled()

    def test_validate_when_no_images_shows_warning(self, widget_no_images):
        """画像なしで検証ボタンを押すと警告を表示して service を呼ばない"""
        # validate ボタンは無効なので _on_validate_clicked を直接呼ぶ
        # image_ids が空のときに直接呼ぶと _show_warning が走る
        widget_no_images.image_ids = []
        widget_no_images._on_validate_clicked()
        # service が呼ばれていないことを確認
        widget_no_images.export_service.validate_export_requirements.assert_not_called()

    def test_on_settings_changed_with_no_previous_results(self, widget_with_images):
        """validation_results が None のとき _on_settings_changed は何もしない"""
        widget_with_images.validation_results = None
        widget_with_images._on_settings_changed()
        # 例外なし


class TestDatasetExportWidgetExport:
    def test_on_export_clicked_without_validation_shows_warning(self, widget_with_images):
        """検証前にエクスポートしようとすると警告を表示"""
        widget_with_images.validation_results = None
        widget_with_images._on_export_clicked()
        # _show_warning が呼ばれ、例外なし

    def test_on_export_clicked_with_zero_valid_images_shows_warning(self, widget_with_images):
        """valid_images=0 のとき警告を表示"""
        widget_with_images.validation_results = {"valid_images": 0}
        widget_with_images._on_export_clicked()
        # 警告が表示され、例外なし

    def test_on_cancel_clicked_with_no_thread(self, widget_with_images):
        """スレッドがない状態でキャンセルボタンを押しても例外なし"""
        widget_with_images.export_thread = None
        widget_with_images._on_cancel_clicked()
        # 例外なし

    def test_on_export_finished_updates_ui(self, widget_with_images):
        """エクスポート完了時に UI が更新される"""
        widget_with_images._on_export_finished("/tmp/export_result")
        assert widget_with_images.ui.exportProgressBar.value() == 100
        assert widget_with_images.ui.exportButton.isEnabled()
        assert not widget_with_images.ui.cancelButton.isEnabled()

    def test_on_export_error_handles_gracefully(self, widget_with_images):
        """エクスポートエラー時に例外なく処理される"""
        widget_with_images._on_export_error("エクスポート失敗")
        # エラー処理後は cancel ボタン無効
        assert not widget_with_images.ui.cancelButton.isEnabled()

    def test_get_output_directory_uses_picker_selected_path(
        self, widget_with_images, monkeypatch, tmp_path
    ):
        """インラインピッカーで選択済みのパスがそのまま使われ、QFileDialog にフォールバックしない (#613)"""
        monkeypatch.setattr(
            widget_with_images.ui.exportDirectoryPicker,
            "get_selected_path",
            lambda: str(tmp_path),
        )
        result = widget_with_images._get_output_directory()
        assert result == tmp_path

    def test_get_output_directory_fallback_when_picker_empty(self, widget_with_images, monkeypatch):
        """ピッカー未選択 (空文字) のときのみ QFileDialog にフォールバックする (auto_mock で "" → None)"""
        monkeypatch.setattr(
            widget_with_images.ui.exportDirectoryPicker,
            "get_selected_path",
            lambda: "",
        )
        result = widget_with_images._get_output_directory()
        assert result is None

    def test_cleanup_worker_when_thread_is_running(self, widget_with_images):
        """スレッドが実行中のとき _cleanup_worker が適切に処理"""
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        widget_with_images.export_thread = mock_thread
        widget_with_images.export_worker = Mock()

        widget_with_images._cleanup_worker()

        mock_thread.quit.assert_called_once()
        mock_thread.wait.assert_called_once()
        assert widget_with_images.export_thread is None
        assert widget_with_images.export_worker is None

    def test_cleanup_worker_when_thread_not_running(self, widget_with_images):
        """スレッドが停止済みのとき _cleanup_worker は quit を呼ばない"""
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        widget_with_images.export_thread = mock_thread
        widget_with_images.export_worker = Mock()

        widget_with_images._cleanup_worker()

        mock_thread.quit.assert_not_called()
        assert widget_with_images.export_thread is None

    def test_display_validation_results_with_issues(self, widget_with_images):
        """issues が含まれる検証結果を正しく表示する"""
        results = {
            "total_images": 5,
            "valid_images": 3,
            "missing_processed": 1,
            "missing_metadata": 1,
            "issues": [f"問題 {i}" for i in range(15)],  # 10件超
        }
        widget_with_images._display_validation_results(results)
        text = widget_with_images.ui.validationDetailsText.toPlainText()
        assert "3件" in text
        # 10件までに制限され、残り件数を表示
        assert "他" in text

    def test_on_export_progress_updates_progress_bar(self, widget_with_images):
        """_on_export_progress でプログレスバーと status ラベルが更新される"""
        widget_with_images._on_export_progress(50, "エクスポート中...")
        assert widget_with_images.ui.exportProgressBar.value() == 50
        assert widget_with_images.ui.statusLabel.text() == "エクスポート中..."


class TestDatasetExportWidgetFormats:
    def test_get_selected_format_txt_separate(self, widget_with_images):
        """TXT separate ラジオボタン選択時"""
        widget_with_images.ui.radioTxtSeparate.setChecked(True)
        assert widget_with_images._get_selected_format() == "txt_separate"

    def test_get_selected_format_txt_merged(self, widget_with_images):
        """TXT merged ラジオボタン選択時"""
        widget_with_images.ui.radioTxtMerged.setChecked(True)
        assert widget_with_images._get_selected_format() == "txt_merged"

    def test_get_selected_format_json(self, widget_with_images):
        """JSON ラジオボタン選択時"""
        widget_with_images.ui.radioJson.setChecked(True)
        assert widget_with_images._get_selected_format() == "json"


class TestDatasetExportWidgetFoundation:
    """Foundation (#610) で整地した seam の検証。S4/S5 はこの枠を埋める。"""

    def test_latest_only_checkbox_removed(self, widget_with_images):
        """死にコントロール latestOnlyCheckBox は撤去済み"""
        assert not hasattr(widget_with_images.ui, "latestOnlyCheckBox")

    def test_changed_since_widgets_exist(self, widget_with_images):
        """changed-since フィルタ枠 (S4 #614) が .ui に存在する"""
        assert hasattr(widget_with_images.ui, "changedSinceCheckBox")
        assert hasattr(widget_with_images.ui, "changedSinceDateTimeEdit")

    def test_resolution_help_label_exists(self, widget_with_images):
        """解像度補助ラベル枠 (S5 #615) が .ui に存在する"""
        assert hasattr(widget_with_images.ui, "resolutionHelpLabel")

    def test_changed_since_checkbox_enabled(self, widget_with_images):
        """S4 #614: changed-since チェックボックスは有効化されている"""
        assert widget_with_images.ui.changedSinceCheckBox.isEnabled()

    def test_changed_since_datetime_disabled_by_default(self, widget_with_images):
        """changed-since 日時入力は既定で無効（トグル ON で有効化）"""
        assert not widget_with_images.ui.changedSinceDateTimeEdit.isEnabled()

    def test_changed_since_toggle_enables_datetime(self, widget_with_images):
        """トグル ON で日時入力が有効化される"""
        widget_with_images.ui.changedSinceCheckBox.setChecked(True)
        assert widget_with_images.ui.changedSinceDateTimeEdit.isEnabled()
        widget_with_images.ui.changedSinceCheckBox.setChecked(False)
        assert not widget_with_images.ui.changedSinceDateTimeEdit.isEnabled()

    def test_effective_image_ids_unfiltered_when_toggle_off(self, widget_with_images):
        """トグル OFF 時は self.image_ids がそのまま実対象になる (#614)"""
        widget_with_images.ui.changedSinceCheckBox.setChecked(False)
        assert widget_with_images._get_effective_image_ids() == widget_with_images.image_ids

    def test_effective_image_ids_filtered_when_toggle_on(self, widget_with_images, monkeypatch):
        """トグル ON 時は service.filter_changed_since の結果が実対象になる (#614)"""
        monkeypatch.setattr(
            widget_with_images.export_service,
            "filter_changed_since",
            lambda image_ids, since: list(image_ids)[:1],
        )
        widget_with_images.ui.changedSinceCheckBox.setChecked(True)
        effective = widget_with_images._get_effective_image_ids()
        assert effective == list(widget_with_images.image_ids)[:1]


class TestDatasetExportWidgetResolution:
    """S5 #615: 解像度の意味明確化と対象/対象外件数の表示。"""

    def test_resolution_tooltip_clarifies_filter_semantics(self, widget_with_images):
        """解像度コンボ/補助ラベルに「変換でなく前処理済み版の有無」のツールチップが付く"""
        combo_tip = widget_with_images.ui.comboBoxResolution.toolTip()
        label_tip = widget_with_images.ui.resolutionHelpLabel.toolTip()
        assert "変換するのではなく" in combo_tip
        assert "前処理済み版" in combo_tip
        assert combo_tip == label_tip

    def test_validation_details_show_resolution_in_out_counts(self, widget_with_images):
        """検証結果に解像度別の対象/対象外件数が表示される"""
        widget_with_images.ui.comboBoxResolution.setCurrentText("768px")
        results = {
            "total_images": 5,
            "valid_images": 3,
            "missing_processed": 2,
            "missing_metadata": 0,
            "issues": [],
        }
        widget_with_images._display_validation_results(results)
        text = widget_with_images.ui.validationDetailsText.toPlainText()
        assert "768px" in text
        assert "対象 3件" in text
        assert "対象外（この解像度の前処理済み版なし）2件" in text
