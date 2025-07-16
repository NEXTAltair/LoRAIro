"""
Unit tests for ImageProcessor class

Tests for the image processing functionality, specifically the resize_image method
and error handling in the process_image method.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image

from lorairo.editor.image_processor import ImageProcessingManager, ImageProcessor
from lorairo.storage.file_system import FileSystemManager


class TestImageProcessor:
    """Test cases for ImageProcessor class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_file_system = Mock(spec=FileSystemManager)
        self.target_resolution = 512
        self.preferred_resolutions = [(512, 512), (768, 512), (1024, 1024)]

        self.processor = ImageProcessor(
            self.mock_file_system, self.target_resolution, self.preferred_resolutions
        )

    def test_resize_image_with_valid_input(self):
        """Test resize_image with valid input image"""
        # Create a test image
        test_img = Image.new("RGB", (704, 992), color="red")

        # Process the image
        result = self.processor.resize_image(test_img)

        # Verify the result
        assert result is not None
        assert isinstance(result, Image.Image)
        # Expected size should be adjusted to 32-pixel boundaries
        expected_width = round(512 * 704 / 992 / 32) * 32  # ~368
        expected_height = 512
        assert result.size == (expected_width, expected_height)

    def test_resize_image_with_none_input(self):
        """Test resize_image with None input should raise ValueError"""
        with pytest.raises(ValueError, match="入力画像がNoneです"):
            self.processor.resize_image(None)

    def test_resize_image_with_invalid_size(self):
        """Test resize_image with invalid image size"""
        test_img = Image.new("RGB", (0, 0), color="red")

        with pytest.raises(ValueError, match="無効な画像サイズです"):
            self.processor.resize_image(test_img)

    def test_resize_image_with_negative_size(self):
        """Test resize_image with negative image size"""
        # Create a mock image with negative size
        mock_img = Mock(spec=Image.Image)
        mock_img.size = (-100, 200)

        with pytest.raises(ValueError, match="無効な画像サイズです"):
            self.processor.resize_image(mock_img)

    def test_resize_image_32_pixel_alignment(self):
        """Test that resize_image properly aligns to 32-pixel boundaries"""
        # Create a test image with odd dimensions
        test_img = Image.new("RGB", (693, 981), color="blue")

        result = self.processor.resize_image(test_img)

        # Check that both dimensions are multiples of 32
        assert result.size[0] % 32 == 0
        assert result.size[1] % 32 == 0

    def test_resize_image_aspect_ratio_preservation(self):
        """Test that resize_image preserves aspect ratio"""
        original_width, original_height = 693, 981
        test_img = Image.new("RGB", (original_width, original_height), color="green")

        result = self.processor.resize_image(test_img)

        original_ratio = original_width / original_height
        result_ratio = result.size[0] / result.size[1]

        # Allow for small differences due to 32-pixel alignment
        assert abs(original_ratio - result_ratio) < 0.1

    def test_resize_image_with_oversized_result(self):
        """Test resize_image with input that would result in oversized image"""
        # Create a test image that would result in oversized dimensions
        # when processed with extreme target resolution
        test_img = Image.new("RGB", (1000, 1000), color="red")

        # Temporarily change target resolution to cause oversized result
        original_target = self.processor.target_resolution
        self.processor.target_resolution = 10000  # This will cause oversized result

        try:
            with pytest.raises(ValueError, match="計算されたサイズが大きすぎます"):
                self.processor.resize_image(test_img)
        finally:
            # Restore original target resolution
            self.processor.target_resolution = original_target

    def test_find_matching_resolution_with_small_image(self):
        """Test _find_matching_resolution with image smaller than target"""
        result = self.processor._find_matching_resolution(300, 400)

        # Should return None for images smaller than target resolution
        assert result is None

    def test_normalize_color_profile_rgb(self):
        """Test color profile normalization for RGB images"""
        test_img = Image.new("RGB", (100, 100), color="red")

        result = ImageProcessor.normalize_color_profile(test_img, has_alpha=False, mode="RGB")

        assert result.mode == "RGB"
        assert result.size == (100, 100)

    def test_normalize_color_profile_rgba(self):
        """Test color profile normalization for RGBA images"""
        test_img = Image.new("RGBA", (100, 100), color="red")

        result = ImageProcessor.normalize_color_profile(test_img, has_alpha=True, mode="RGBA")

        assert result.mode == "RGBA"
        assert result.size == (100, 100)

    def test_normalize_color_profile_cmyk(self):
        """Test color profile normalization for CMYK images"""
        test_img = Image.new("CMYK", (100, 100), color="red")

        result = ImageProcessor.normalize_color_profile(test_img, has_alpha=False, mode="CMYK")

        assert result.mode == "RGB"
        assert result.size == (100, 100)


class TestImageProcessingManager:
    """Test cases for ImageProcessingManager class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_file_system = Mock(spec=FileSystemManager)
        self.target_resolution = 512
        self.preferred_resolutions = [(512, 512), (768, 512), (1024, 1024)]

        # Mock ConfigurationService for ImageProcessingManager
        self.mock_config_service = Mock()
        self.mock_config_service.validate_upscaler_config.return_value = True

        self.manager = ImageProcessingManager(
            self.mock_file_system,
            self.target_resolution,
            self.preferred_resolutions,
            self.mock_config_service,
        )

    def test_process_image_success(self):
        """Test process_image with successful processing"""
        # Create a temporary test image file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            test_img = Image.new("RGB", (704, 992), color="red")
            test_img.save(tmp_file.name)
            tmp_path = Path(tmp_file.name)

        try:
            # Mock AutoCrop to return the image unchanged
            with patch("lorairo.editor.autocrop.AutoCrop") as mock_autocrop:
                mock_autocrop.auto_crop_image.return_value = test_img

                result = self.manager.process_image(
                    db_stored_original_path=tmp_path, original_has_alpha=False, original_mode="RGB"
                )

                assert result is not None
                assert isinstance(result, tuple)
                assert len(result) == 2
                processed_image, metadata = result
                assert isinstance(processed_image, Image.Image)
                assert isinstance(metadata, dict)
                # Verify the result has been resized
                assert processed_image.size != test_img.size

        finally:
            # Clean up
            tmp_path.unlink()

    def test_process_image_with_error_handling(self):
        """Test process_image error handling when resize fails"""
        # Create a temporary test image file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            test_img = Image.new("RGB", (704, 992), color="red")
            test_img.save(tmp_file.name)
            tmp_path = Path(tmp_file.name)

        try:
            # Mock AutoCrop to return the image unchanged
            with patch("lorairo.editor.autocrop.AutoCrop") as mock_autocrop:
                mock_autocrop.auto_crop_image.return_value = test_img

                # Mock resize_image to raise an exception
                with patch.object(self.manager.image_processor, "resize_image") as mock_resize:
                    mock_resize.side_effect = ValueError("Test error")

                    result = self.manager.process_image(
                        db_stored_original_path=tmp_path, original_has_alpha=False, original_mode="RGB"
                    )

                    # Should return tuple with None image when an error occurs
                    assert result is not None
                    assert isinstance(result, tuple)
                    processed_image, metadata = result
                    assert processed_image is None
                    assert isinstance(metadata, dict)

        finally:
            # Clean up
            tmp_path.unlink()

    def test_process_image_with_nonexistent_file(self):
        """Test process_image with non-existent file"""
        non_existent_path = Path("/nonexistent/file.jpg")

        result = self.manager.process_image(
            db_stored_original_path=non_existent_path, original_has_alpha=False, original_mode="RGB"
        )

        # Should return tuple with None image when file doesn't exist
        assert result is not None
        assert isinstance(result, tuple)
        processed_image, metadata = result
        assert processed_image is None
        assert isinstance(metadata, dict)

    def test_process_image_small_image_without_upscaler(self):
        """Test process_image with small image and no upscaler"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            # Create a small image (smaller than target resolution)
            small_img = Image.new("RGB", (300, 400), color="blue")
            small_img.save(tmp_file.name)
            tmp_path = Path(tmp_file.name)

        try:
            with patch("lorairo.editor.image_processor.AutoCrop") as mock_autocrop:
                mock_autocrop.auto_crop_image.return_value = small_img

                result = self.manager.process_image(
                    db_stored_original_path=tmp_path, original_has_alpha=False, original_mode="RGB"
                )

                # Should still process the image even if it's small
                assert result is not None
                assert isinstance(result, tuple)
                assert len(result) == 2
                processed_image, metadata = result
                assert isinstance(processed_image, Image.Image)
                assert isinstance(metadata, dict)

        finally:
            tmp_path.unlink()

    def test_initialization_success(self):
        """Test successful initialization of ImageProcessingManager"""
        # Test that the manager was initialized successfully
        assert self.manager.target_resolution == 512
        assert self.manager.image_processor is not None
        assert self.manager.file_system_manager is not None

    def test_initialization_with_invalid_parameters(self):
        """Test initialization with invalid parameters"""
        # Mock FileSystemManager to raise an exception during ImageProcessor initialization
        with patch("lorairo.editor.image_processor.ImageProcessor") as mock_processor:
            mock_processor.side_effect = Exception("Mock initialization error")

            with pytest.raises(ValueError, match="ImageProcessingManagerの初期化中エラー"):
                ImageProcessingManager(
                    self.mock_file_system,
                    target_resolution=512,
                    preferred_resolutions=[(512, 512)],
                    config_service=self.mock_config_service,
                )


if __name__ == "__main__":
    pytest.main([__file__])
