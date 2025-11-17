# tests/unit/gui/widgets/test_selected_image_details_widget.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer

from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, ImageDetails
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget


class TestSelectedImageDetailsWidget:
    """SelectedImageDetailsWidget単体テスト（Enhanced Event-Driven Pattern対応）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用SelectedImageDetailsWidget"""
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def sample_image_details(self):
        """テスト用ImageDetailsサンプル"""
        annotation_data = AnnotationData(
            tags=[
                {
                    "tag": "1girl",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.95,
                    "is_edited_manually": False,
                },
                {
                    "tag": "long hair",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.90,
                    "is_edited_manually": False,
                },
                {
                    "tag": "blue eyes",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.88,
                    "is_edited_manually": False,
                },
            ],
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
            caption="A beautiful anime girl with long hair",
            tags="1girl, long hair, blue eyes",
            annotation_data=annotation_data,
        )

    def test_initialization(self, widget):
        """初期化テスト（Enhanced Event-Driven Pattern）"""
        # Enhanced Event-Driven Patternでの初期化確認
        assert widget.current_details is None
        assert widget.current_image_id is None

        # UIコンポーネントの存在確認
        assert hasattr(widget.ui, "groupBoxImageInfo")
        assert hasattr(widget.ui, "groupBoxAnnotationSummary")

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

    def test_annotation_data_loaded_slot(self, widget):
        """アノテーションデータ読み込み完了スロットテスト"""
        with patch("lorairo.gui.widgets.selected_image_details_widget.logger") as mock_logger:
            widget._on_annotation_data_loaded()

            # ログが出力される
            mock_logger.debug.assert_called_with("Annotation data loaded in AnnotationDataDisplayWidget")

    def test_enable_disable_widget(self, widget):
        """ウィジェット有効/無効化テスト"""
        # 無効化
        widget.setEnabled(False)
        assert not widget.isEnabled()

        # 有効化
        widget.setEnabled(True)
        assert widget.isEnabled()

    def test_on_image_data_received(self, widget):
        """Enhanced Event-Driven Pattern: 画像データ受信テスト"""
        # テスト用画像メタデータ
        image_data = {
            "id": 456,
            "file_path": "/test/path/test_image.jpg",
            "width": 1920,
            "height": 1080,
            "file_size": 2048000,
            "created_at": "2024-03-15T10:30:00",
            "rating": "PG",
            "score": 750,
        }

        # メソッド呼び出し
        widget._on_image_data_received(image_data)

        # 状態確認
        assert widget.current_image_id == 456
        assert widget.current_details.file_name == "test_image.jpg"
        assert widget.current_details.image_size == "1920 x 1080"
        assert widget.current_details.rating_value == "PG"
        assert widget.current_details.score_value == 750

    def test_on_image_data_received_empty(self, widget):
        """Enhanced Event-Driven Pattern: 空データ受信テスト"""
        # 初期状態設定
        widget.current_image_id = 123
        widget.current_details = ImageDetails(file_name="previous.jpg")

        # 空データ受信
        widget._on_image_data_received({})

        # 表示がクリアされる
        assert widget.current_image_id is None
        assert widget.current_details is None
