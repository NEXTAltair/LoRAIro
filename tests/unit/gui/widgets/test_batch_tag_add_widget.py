"""
BatchTagAddWidget Unit Tests

Comprehensive test suite for BatchTagAddWidget component.

Test Coverage:
- Initialization and setup
- Staging list management (add/remove/clear)
- Tag normalization and validation
- Signal emission (tag_add_requested, staging_cleared, staged_images_changed)
- DatasetStateManager integration
- Edge cases and error handling

Target: 80%+ coverage
"""

import pytest

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget


class TestBatchTagAddWidgetInitialization:
    """Initialization and setup tests"""

    def test_initialization(self, qtbot):
        """Test widget initializes correctly"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        assert widget is not None
        assert hasattr(widget, "ui")
        assert widget._staged_images == {}
        assert widget._dataset_state_manager is None

    def test_ui_components_present(self, qtbot):
        """Test all UI components are created"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        assert hasattr(widget.ui, "lineEditTag")
        assert hasattr(widget.ui, "pushButtonClearStaging")
        assert hasattr(widget.ui, "pushButtonAddTag")
        assert hasattr(widget.ui, "labelStagingCount")

    def test_initial_staging_count_label(self, qtbot):
        """Test initial staging count label shows 0"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        expected_text = f"0 / {widget.MAX_STAGING_IMAGES} 枚"
        assert widget.ui.labelStagingCount.text() == expected_text


class TestDatasetStateManagerIntegration:
    """DatasetStateManager integration tests"""

    def test_set_dataset_state_manager(self, qtbot):
        """Test setting DatasetStateManager reference"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        widget.set_dataset_state_manager(state_manager)

        assert widget._dataset_state_manager == state_manager

    def test_add_selected_without_state_manager(self, qtbot):
        """Test adding selected images without DatasetStateManager"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        # Should not raise exception, just return early
        widget._on_add_selected_clicked()

        # Verify no images added
        assert len(widget._staged_images) == 0

    def test_add_selected_with_empty_selection(self, qtbot):
        """Test adding selected images when no images are selected"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        widget.set_dataset_state_manager(state_manager)
        # No images selected (selected_image_ids is empty)

        widget._on_add_selected_clicked()

        # Verify no images added
        assert len(widget._staged_images) == 0


class TestStagingListManagement:
    """Staging list management tests"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        """Create widget with DatasetStateManager"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        # Mock some images in state manager (using correct data structure)
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
            {"id": 3, "stored_image_path": "/path/to/image3.jpg"},
        ]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = [1, 2]

        widget.set_dataset_state_manager(state_manager)
        return widget, state_manager

    def test_add_selected_images_to_staging(self, qtbot, widget_with_state):
        """Test adding selected images to staging list"""
        widget, _ = widget_with_state

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget._on_add_selected_clicked()

        # Verify signal emission
        assert blocker.args == [[1, 2]]

        # Verify internal state
        assert len(widget._staged_images) == 2
        assert 1 in widget._staged_images
        assert 2 in widget._staged_images

        # Verify UI update
        assert widget.ui.labelStagingCount.text() == f"2 / {widget.MAX_STAGING_IMAGES} 枚"

    def test_add_visible_image_ids_to_staging(self, qtbot, widget_with_state):
        """可視範囲のID指定追加APIをテスト"""
        widget, _ = widget_with_state

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
            widget.add_image_ids_to_staging([2, 3])

        assert blocker.args == [[2, 3]]
        assert list(widget._staged_images.keys()) == [2, 3]

    def test_add_duplicate_images_skipped(self, qtbot, widget_with_state):
        """Test duplicate images are skipped when adding to staging"""
        widget, _ = widget_with_state

        # Add images first time
        widget._on_add_selected_clicked()
        assert len(widget._staged_images) == 2

        # Try to add same images again
        widget._on_add_selected_clicked()

        # Should still have 2 images (no duplicates)
        assert len(widget._staged_images) == 2

    def test_staging_limit_enforcement(self, qtbot):
        """Test staging list enforces 500 image limit"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        # Create 550 mock images (exceeds limit)
        mock_images = [{"id": i, "stored_image_path": f"/path/to/image{i}.jpg"} for i in range(1, 551)]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = list(range(1, 551))  # Select all 550

        widget.set_dataset_state_manager(state_manager)

        with qtbot.waitSignal(widget.staged_images_changed, timeout=1000):
            widget._on_add_selected_clicked()

        # Should only have 500 images (limit enforced)
        assert len(widget._staged_images) == widget.MAX_STAGING_IMAGES

    def test_clear_staging_list(self, qtbot, widget_with_state):
        """Test clearing staging list"""
        widget, _ = widget_with_state

        # Add images first
        widget._on_add_selected_clicked()
        assert len(widget._staged_images) == 2

        # Clear staging
        with qtbot.waitSignal(widget.staging_cleared, timeout=1000):
            with qtbot.waitSignal(widget.staged_images_changed, timeout=1000) as blocker:
                widget._on_clear_staging_clicked()

        # Verify signal emission
        assert blocker.args == [[]]

        # Verify internal state cleared
        assert len(widget._staged_images) == 0

        # Verify UI updated
        assert widget.ui.labelStagingCount.text() == f"0 / {widget.MAX_STAGING_IMAGES} 枚"


class TestTagNormalization:
    """Tag normalization and validation tests"""

    def test_normalize_tag_basic(self, qtbot):
        """Test basic tag normalization (lowercase + strip)"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        assert widget._normalize_tag("LANDSCAPE") == "landscape"
        assert widget._normalize_tag("  Nature  ") == "nature"
        assert widget._normalize_tag("  Urban SCENE  ") == "urban scene"

    def test_normalize_tag_empty(self, qtbot):
        """Test empty tag normalization"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        assert widget._normalize_tag("") == ""
        assert widget._normalize_tag("   ") == ""


class TestTagAddRequest:
    """Tag add request and signal emission tests"""

    @pytest.fixture
    def widget_with_staging(self, qtbot):
        """Create widget with images in staging"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
        ]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = [1, 2]

        widget.set_dataset_state_manager(state_manager)
        widget._on_add_selected_clicked()  # Add to staging

        return widget

    def test_tag_add_request_success(self, qtbot, widget_with_staging):
        """Test successful tag add request"""
        widget = widget_with_staging

        # Enter tag
        widget.ui.lineEditTag.setText("  LANDSCAPE  ")

        # Click add button
        with qtbot.waitSignal(widget.tag_add_requested, timeout=1000) as blocker:
            widget._on_add_tag_clicked()

        # Verify signal emission with normalized tag
        image_ids, tag = blocker.args
        assert image_ids == [1, 2]
        assert tag == "landscape"  # Normalized

        # Verify tag input cleared
        assert widget.ui.lineEditTag.text() == ""

    def test_tag_add_request_empty_staging(self, qtbot, monkeypatch):
        """Test tag add request with empty staging list shows warning"""
        from PySide6.QtWidgets import QMessageBox

        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        widget.ui.lineEditTag.setText("landscape")

        # QMessageBox.warningをモック
        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        widget._on_add_tag_clicked()

        # Tag input should not be cleared (signal not emitted)
        assert widget.ui.lineEditTag.text() == "landscape"
        # QMessageBox.warningが呼ばれた
        assert len(warning_called) == 1

    def test_tag_add_request_empty_tag(self, qtbot, widget_with_staging, monkeypatch):
        """Test tag add request with empty tag shows warning"""
        from PySide6.QtWidgets import QMessageBox

        widget = widget_with_staging

        # QMessageBox.warningをモック
        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        # Leave tag input empty
        widget.ui.lineEditTag.setText("")

        widget._on_add_tag_clicked()

        # Tag input should remain empty (signal not emitted, so not cleared)
        assert widget.ui.lineEditTag.text() == ""
        assert len(warning_called) == 1

    def test_tag_add_request_whitespace_only_tag(self, qtbot, widget_with_staging, monkeypatch):
        """Test tag add request with whitespace-only tag shows warning"""
        from PySide6.QtWidgets import QMessageBox

        widget = widget_with_staging

        # QMessageBox.warningをモック
        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        # Enter whitespace only
        widget.ui.lineEditTag.setText("   ")

        widget._on_add_tag_clicked()

        # Tag input should remain unchanged (signal not emitted, so not cleared)
        assert widget.ui.lineEditTag.text() == "   "
        assert len(warning_called) == 1


class TestStagingCountLabel:
    """Staging count label update tests"""

    def test_staging_count_updates_on_add(self, qtbot):
        """Test staging count label updates when adding images"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [{"id": 1, "stored_image_path": "/path/to/image1.jpg"}]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = [1]

        widget.set_dataset_state_manager(state_manager)

        # Initial state
        assert widget.ui.labelStagingCount.text() == f"0 / {widget.MAX_STAGING_IMAGES} 枚"

        # Add image
        widget._on_add_selected_clicked()

        # Count updated
        assert widget.ui.labelStagingCount.text() == f"1 / {widget.MAX_STAGING_IMAGES} 枚"

    def test_staging_count_updates_on_clear(self, qtbot):
        """Test staging count label updates when clearing"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [{"id": 1, "stored_image_path": "/path/to/image1.jpg"}]
        state_manager._all_images = mock_images
        state_manager._selected_image_ids = [1]

        widget.set_dataset_state_manager(state_manager)

        # Add image
        widget._on_add_selected_clicked()
        assert widget.ui.labelStagingCount.text() == f"1 / {widget.MAX_STAGING_IMAGES} 枚"

        # Clear staging
        widget._on_clear_staging_clicked()

        # Count reset
        assert widget.ui.labelStagingCount.text() == f"0 / {widget.MAX_STAGING_IMAGES} 枚"


class TestEdgeCases:
    """Edge cases and error handling tests"""

    def test_metadata_not_found_for_image(self, qtbot, caplog):
        """Test handling when image metadata is not found"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        state_manager._all_images = []  # No images in state
        state_manager._selected_image_ids = [999]  # Non-existent ID

        widget.set_dataset_state_manager(state_manager)

        widget._on_add_selected_clicked()

        # Should handle gracefully (no crash)
        assert len(widget._staged_images) == 0

    def test_multiple_add_operations_maintain_order(self, qtbot):
        """Test multiple add operations maintain insertion order"""
        widget = BatchTagAddWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        mock_images = [
            {"id": 1, "stored_image_path": "/path/to/image1.jpg"},
            {"id": 2, "stored_image_path": "/path/to/image2.jpg"},
            {"id": 3, "stored_image_path": "/path/to/image3.jpg"},
        ]
        state_manager._all_images = mock_images

        widget.set_dataset_state_manager(state_manager)

        # Add images in different batches
        state_manager._selected_image_ids = [1]
        widget._on_add_selected_clicked()

        state_manager._selected_image_ids = [3]
        widget._on_add_selected_clicked()

        state_manager._selected_image_ids = [2]
        widget._on_add_selected_clicked()

        # Order should be [1, 3, 2] (insertion order preserved)
        staged_ids = list(widget._staged_images.keys())
        assert staged_ids == [1, 3, 2]
