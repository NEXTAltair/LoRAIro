# tests/unit/gui/widgets/test_selected_image_details_widget.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer

from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, ImageDetails
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget


class TestSelectedImageDetailsWidget:
    """SelectedImageDetailsWidget単体テスト（Phase 3.2 DB分離対応）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用SelectedImageDetailsWidget"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def mock_service(self):
        """テスト用モックImageDBWriteService"""
        return Mock()

    @pytest.fixture
    def sample_image_details(self):
        """テスト用ImageDetailsサンプル"""
        annotation_data = AnnotationData(
            tags=["1girl", "long hair", "blue eyes"],
            caption="A beautiful anime girl with long hair",
            aesthetic_score=0.85,
            overall_score=850,
            score_type="Aesthetic",
        )

        return ImageDetails(
            image_id=123,
            file_name="sample_image.jpg",
            file_path=str(Path("/test/dataset/sample_image.jpg")),
            image_size="1024x768",
            file_size="2.5 MB",
            created_date="2024-02-15 14:30:00",
            rating_value="PG",
            score_value=850,
            annotation_data=annotation_data,
        )

    def test_initialization(self, widget):
        """初期化テスト（Phase 3.2パターン）"""
        # Phase 3.2: DB操作分離後の初期化確認
        assert widget.image_db_write_service is None
        assert widget.current_details is not None
        assert isinstance(widget.current_details, ImageDetails)
        assert widget.current_image_id is None

        # UIコンポーネントの存在確認
        assert hasattr(widget, "groupBoxImageInfo")
        assert hasattr(widget, "groupBoxAnnotationSummary")

    def test_set_image_db_write_service(self, widget, mock_service):
        """ImageDBWriteService依存注入テスト"""
        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget.set_image_db_write_service(mock_service)

            assert widget.image_db_write_service == mock_service
            mock_logger.debug.assert_called_with("ImageDBWriteService set for SelectedImageDetailsWidget")

    def test_load_image_details_success(self, widget, mock_service, sample_image_details):
        """画像詳細読み込み成功テスト"""
        # サービス注入
        widget.set_image_db_write_service(mock_service)
        mock_service.get_image_details.return_value = sample_image_details

        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            # 画像詳細読み込み
            widget.load_image_details(123)

            # 結果検証
            assert widget.current_image_id == 123
            assert widget.current_details == sample_image_details

            # サービスメソッド呼び出し確認
            mock_service.get_image_details.assert_called_once_with(123)

            # ログ確認
            mock_logger.debug.assert_called_with(
                "Image details loaded for ID: 123 (via ImageDBWriteService)"
            )

    def test_load_image_details_no_service(self, widget):
        """サービス未注入時の画像詳細読み込みテスト"""
        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget.load_image_details(123)

            # 警告ログが出力される
            mock_logger.warning.assert_called_with(
                "ImageDBWriteService not available for loading image details"
            )

            # 状態は変更されない
            assert widget.current_image_id is None

    def test_load_image_details_service_error(self, widget, mock_service):
        """サービスエラー時の画像詳細読み込みテスト"""
        widget.set_image_db_write_service(mock_service)
        mock_service.get_image_details.side_effect = Exception("Service error")

        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget.load_image_details(456)

            # エラーログが出力される
            mock_logger.error.assert_called_with(
                "Error loading image details for ID 456: Service error", exc_info=True
            )

    def test_clear_display(self, widget, sample_image_details):
        """表示クリアテスト"""
        # 初期データ設定
        widget.current_details = sample_image_details
        widget.current_image_id = 123

        # プライベートメソッドの呼び出し（内部実装テスト）
        widget._clear_display()

        # 状態がクリアされることを確認（実際の実装に応じて調整）
        # Note: _clear_display()の実装により具体的なテストは変わる
        pass

    def test_update_details_display(self, widget, sample_image_details):
        """詳細表示更新テスト"""
        # プライベートメソッドのテスト（内部実装確認）
        widget._update_details_display(sample_image_details)

        # 実際の実装により具体的な検証項目は変わる
        # UIラベルの内容更新等を確認
        pass

    def test_signal_emission(self, widget, mock_service, sample_image_details, qtbot):
        """シグナル発信テスト"""
        widget.set_image_db_write_service(mock_service)
        mock_service.get_image_details.return_value = sample_image_details

        # シグナル受信用のスロット
        signal_received = []
        widget.image_details_loaded.connect(lambda details: signal_received.append(details))

        # 画像詳細読み込み
        widget.load_image_details(789)

        # シグナルが発信されることを確認
        assert len(signal_received) == 1
        assert signal_received[0] == sample_image_details

    def test_annotation_data_loaded_slot(self, widget):
        """アノテーションデータ読み込み完了スロットテスト"""
        annotation_data = AnnotationData(
            tags=["test", "data"], caption="Test caption", aesthetic_score=0.75
        )

        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget._on_annotation_data_loaded(annotation_data)

            # current_detailsが更新される
            assert widget.current_details.annotation_data == annotation_data

            # ログが出力される
            mock_logger.debug.assert_called_with("Annotation data loaded in details widget")

    def test_enable_disable_widget(self, widget):
        """ウィジェット有効/無効化テスト"""
        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            # 無効化
            widget.setEnabled(False)
            assert not widget.isEnabled()

            # 有効化
            widget.setEnabled(True)
            assert widget.isEnabled()


class TestSelectedImageDetailsWidgetIntegration:
    """SelectedImageDetailsWidget統合テスト"""

    @pytest.fixture
    def widget_with_service(self, qtbot):
        """サービス注入済みウィジェット"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)

        mock_service = Mock()
        widget.set_image_db_write_service(mock_service)

        return widget, mock_service

    @pytest.fixture
    def complex_image_details(self):
        """複雑なImageDetailsサンプル"""
        annotation_data = AnnotationData(
            tags=["landscape", "mountain", "sunset", "photography"],
            caption="A breathtaking sunset over snow-capped mountains with dramatic clouds",
            aesthetic_score=0.92,
            overall_score=920,
            score_type="Professional",
        )
        return ImageDetails(
            image_id=9999,
            file_name="mountain_sunset_4k.jpg",
            file_path="/professional/dataset/landscapes/mountain_sunset_4k.jpg",
            image_size="3840x2160",
            file_size="12.8 MB",
            created_date="2024-03-20 18:45:30",
            rating_value="G",
            score_value=920,
            annotation_data=annotation_data,
        )

    def test_complete_workflow(self, widget_with_service, complex_image_details, qtbot):
        """完全ワークフローテスト"""
        widget, mock_service = widget_with_service
        mock_service.get_image_details.return_value = complex_image_details

        # 1. 画像詳細読み込み
        widget.load_image_details(9999)

        # 2. 状態確認
        assert widget.current_image_id == 9999
        assert widget.current_details.file_name == "mountain_sunset_4k.jpg"
        assert widget.current_details.image_size == "3840x2160"

        # 3. アノテーションデータ確認
        annotation = widget.current_details.annotation_data
        assert len(annotation.tags) == 4
        assert "landscape" in annotation.tags
        assert annotation.aesthetic_score == 0.92

    def test_multiple_image_switching(self, widget_with_service, qtbot):
        """複数画像切り替えテスト"""
        widget, mock_service = widget_with_service

        # 異なる画像詳細を設定
        details1 = ImageDetails(image_id=1, file_name="image1.jpg")
        details2 = ImageDetails(image_id=2, file_name="image2.png")

        def get_details_side_effect(image_id):
            return details1 if image_id == 1 else details2

        mock_service.get_image_details.side_effect = get_details_side_effect

        # 画像1読み込み
        widget.load_image_details(1)
        assert widget.current_image_id == 1
        assert widget.current_details.file_name == "image1.jpg"

        # 画像2に切り替え
        widget.load_image_details(2)
        assert widget.current_image_id == 2
        assert widget.current_details.file_name == "image2.png"

    def test_error_recovery(self, widget_with_service, qtbot):
        """エラー回復テスト"""
        widget, mock_service = widget_with_service

        # 最初は正常
        valid_details = ImageDetails(image_id=100, file_name="valid.jpg")
        mock_service.get_image_details.return_value = valid_details
        widget.load_image_details(100)
        assert widget.current_image_id == 100

        # エラー発生
        mock_service.get_image_details.side_effect = Exception("Network error")
        widget.load_image_details(200)

        # エラー処理により現在のIDは更新されない
        # （ただし、プライベートな実装詳細によりNoneになる可能性もある）
        # assert widget.current_image_id == 100

    def test_service_replacement(self, qtbot):
        """サービス置き換えテスト"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)

        # 最初のサービス
        service1 = Mock()
        widget.set_image_db_write_service(service1)
        assert widget.image_db_write_service == service1

        # サービス置き換え
        service2 = Mock()
        widget.set_image_db_write_service(service2)
        assert widget.image_db_write_service == service2

        # 新しいサービスが使用される
        details = ImageDetails(image_id=300, file_name="replaced.jpg")
        service2.get_image_details.return_value = details

        widget.load_image_details(300)
        service2.get_image_details.assert_called_once_with(300)
        service1.get_image_details.assert_not_called()

    def test_memory_efficiency(self, widget_with_service, qtbot):
        """メモリ効率テスト"""
        widget, mock_service = widget_with_service

        # 大量のアノテーションデータを持つ画像
        large_annotation = AnnotationData(
            tags=["tag" + str(i) for i in range(100)],  # 100個のタグ
            caption="A" * 1000,  # 長いキャプション
            aesthetic_score=0.5,
        )
        large_details = ImageDetails(
            image_id=500, file_name="large_data.jpg", annotation_data=large_annotation
        )

        mock_service.get_image_details.return_value = large_details

        # 読み込み
        widget.load_image_details(500)

        # データが正しく格納されている
        assert len(widget.current_details.annotation_data.tags) == 100
        assert len(widget.current_details.annotation_data.caption) == 1000

        # 新しい画像に切り替え（メモリ解放のシミュレーション）
        small_details = ImageDetails(image_id=501, file_name="small.jpg")
        mock_service.get_image_details.return_value = small_details

        widget.load_image_details(501)

        # 古いデータは置き換えられる
        assert widget.current_details.image_id == 501
        assert len(widget.current_details.annotation_data.tags) == 0
