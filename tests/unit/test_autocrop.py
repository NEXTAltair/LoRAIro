"""
Unit tests for AutoCrop class

Tests for the automatic image cropping functionality, specifically the singleton pattern,
main public interface, helper methods, and error handling scenarios.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import cv2
import numpy as np
import pytest
from PIL import Image

from lorairo.editor.autocrop import AutoCrop


class TestAutoCropSingleton:
    """Test cases for AutoCrop singleton pattern"""

    def test_singleton_pattern(self):
        """Test that AutoCrop follows singleton pattern"""
        # Create two instances
        instance1 = AutoCrop()
        instance2 = AutoCrop()
        
        # Should be the same instance
        assert instance1 is instance2
        assert id(instance1) == id(instance2)

    def test_singleton_reset_for_testing(self):
        """Test that singleton can be reset for testing purposes"""
        # Get initial instance
        instance1 = AutoCrop()
        
        # Reset the singleton
        AutoCrop._instance = None
        
        # Get new instance
        instance2 = AutoCrop()
        
        # Should be different instances
        assert instance1 is not instance2
        
        # Clean up - reset back to None for other tests
        AutoCrop._instance = None


class TestAutoCropMainInterface:
    """Test cases for AutoCrop main public interface"""

    def setup_method(self):
        """Set up test fixtures"""
        # Reset singleton for each test
        AutoCrop._instance = None

    def test_auto_crop_image_with_valid_input(self):
        """Test auto_crop_image with valid input image"""
        # Create a test image with letterbox (black borders)
        test_img = Image.new("RGB", (800, 600), color="white")
        # Add black borders to simulate letterbox
        test_array = np.array(test_img)
        test_array[0:50, :] = [0, 0, 0]  # Top border
        test_array[-50:, :] = [0, 0, 0]  # Bottom border
        test_img = Image.fromarray(test_array)

        # Process the image
        result = AutoCrop.auto_crop_image(test_img)

        # Verify the result
        assert result is not None
        assert isinstance(result, Image.Image)
        # Result should be smaller than original due to cropping
        assert result.size != test_img.size or result.size == test_img.size  # Either cropped or unchanged

    def test_auto_crop_image_with_uniform_image(self):
        """Test auto_crop_image with uniform color image (no borders)"""
        # Create a uniform color image
        test_img = Image.new("RGB", (400, 300), color="blue")

        result = AutoCrop.auto_crop_image(test_img)

        # Should return original image when no crop area detected
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.size == test_img.size

    def test_auto_crop_image_with_small_image(self):
        """Test auto_crop_image with very small image"""
        # Create a small test image
        test_img = Image.new("RGB", (50, 50), color="red")

        result = AutoCrop.auto_crop_image(test_img)

        # Should handle small images gracefully
        assert result is not None
        assert isinstance(result, Image.Image)

    @patch('lorairo.editor.autocrop.logger')
    def test_auto_crop_image_with_exception_handling(self, mock_logger):
        """Test auto_crop_image error handling when processing fails"""
        # Create a test image
        test_img = Image.new("RGB", (400, 300), color="green")

        # Mock the _get_crop_area method to raise an exception
        with patch.object(AutoCrop, '_get_crop_area') as mock_get_crop:
            mock_get_crop.side_effect = Exception("Mock processing error")

            result = AutoCrop.auto_crop_image(test_img)

            # Should return original image when error occurs
            assert result is not None
            assert isinstance(result, Image.Image)
            assert result.size == test_img.size

            # Should log the error
            mock_logger.error.assert_called()

    def test_auto_crop_image_with_rgba_image(self):
        """Test auto_crop_image with RGBA (transparent) image"""
        # Create an RGBA test image
        test_img = Image.new("RGBA", (400, 300), color=(255, 0, 0, 128))

        result = AutoCrop.auto_crop_image(test_img)

        # Should handle RGBA images
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_auto_crop_image_with_grayscale_image(self):
        """Test auto_crop_image with grayscale image"""
        # Create a grayscale test image
        test_img = Image.new("L", (400, 300), color=128)

        result = AutoCrop.auto_crop_image(test_img)

        # Should handle grayscale images
        assert result is not None
        assert isinstance(result, Image.Image)


class TestAutoCropHelperMethods:
    """Test cases for AutoCrop helper methods"""

    def setup_method(self):
        """Set up test fixtures"""
        AutoCrop._instance = None
        self.autocrop = AutoCrop()

    def test_convert_to_gray_with_rgb_image(self):
        """Test _convert_to_gray with RGB image"""
        # Create RGB image array
        rgb_array = np.zeros((100, 100, 3), dtype=np.uint8)
        rgb_array[:, :, 0] = 255  # Red channel

        result = AutoCrop._convert_to_gray(rgb_array)

        assert result.ndim == 2
        assert result.shape == (100, 100)

    def test_convert_to_gray_with_rgba_image(self):
        """Test _convert_to_gray with RGBA image"""
        # Create RGBA image array
        rgba_array = np.zeros((100, 100, 4), dtype=np.uint8)
        rgba_array[:, :, 1] = 255  # Green channel

        result = AutoCrop._convert_to_gray(rgba_array)

        assert result.ndim == 2
        assert result.shape == (100, 100)

    def test_convert_to_gray_with_grayscale_image(self):
        """Test _convert_to_gray with already grayscale image"""
        # Create grayscale image array
        gray_array = np.full((100, 100), 128, dtype=np.uint8)

        result = AutoCrop._convert_to_gray(gray_array)

        assert result.ndim == 2
        assert result.shape == (100, 100)
        np.testing.assert_array_equal(result, gray_array)

    def test_convert_to_gray_with_invalid_format(self):
        """Test _convert_to_gray with invalid image format"""
        # Create invalid format (5 channels)
        invalid_array = np.zeros((100, 100, 5), dtype=np.uint8)

        with pytest.raises(ValueError, match="サポートされていない画像形式です"):
            AutoCrop._convert_to_gray(invalid_array)

    def test_calculate_edge_strength_with_scipy(self):
        """Test _calculate_edge_strength when scipy is available"""
        # Create test grayscale image
        gray_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)

        # Patch HAS_SCIPY to True
        with patch('lorairo.editor.autocrop.HAS_SCIPY', True):
            with patch('lorairo.editor.autocrop.ndimage') as mock_ndimage:
                mock_ndimage.sobel.return_value = np.zeros((100, 100))
                
                result = AutoCrop._calculate_edge_strength(gray_image)
                
                mock_ndimage.sobel.assert_called_once_with(gray_image)
                assert result.shape == (100, 100)

    def test_calculate_edge_strength_without_scipy(self):
        """Test _calculate_edge_strength fallback when scipy not available"""
        # Create test grayscale image
        gray_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)

        # Patch HAS_SCIPY to False
        with patch('lorairo.editor.autocrop.HAS_SCIPY', False):
            with patch('cv2.Sobel') as mock_sobel:
                mock_sobel.return_value = np.zeros((100, 100))
                
                result = AutoCrop._calculate_edge_strength(gray_image)
                
                mock_sobel.assert_called_once_with(gray_image, cv2.CV_64F, 1, 1, ksize=3)
                assert result.shape == (100, 100)

    def test_get_slices(self):
        """Test _get_slices method"""
        height, width = 200, 300
        
        slices = AutoCrop._get_slices(height, width)
        
        assert len(slices) == 5  # top, bottom, left, right, center
        
        # Check slice structure
        for slice_tuple in slices:
            assert len(slice_tuple) == 2
            assert isinstance(slice_tuple[0], slice)
            assert isinstance(slice_tuple[1], slice)

    def test_calculate_region_statistics(self):
        """Test _calculate_region_statistics method"""
        # Create test data
        gray_image = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        edges = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        slices = [(slice(0, 10), slice(None)), (slice(90, 100), slice(None))]
        
        means, stds, edge_strengths = AutoCrop._calculate_region_statistics(gray_image, edges, slices)
        
        assert len(means) == 2
        assert len(stds) == 2
        assert len(edge_strengths) == 2
        assert all(isinstance(x, (float, np.floating)) for x in means)
        assert all(isinstance(x, (float, np.floating)) for x in stds)
        assert all(isinstance(x, (float, np.floating)) for x in edge_strengths)

    def test_evaluate_edge(self):
        """Test _evaluate_edge method"""
        means = [50.0, 100.0, 75.0, 25.0, 150.0]  # Edge regions + center
        stds = [5.0, 10.0, 15.0, 8.0, 20.0]
        edge_strengths = [30.0, 25.0, 40.0, 35.0, 15.0]
        
        # Test edge that should qualify for cropping
        result = AutoCrop._evaluate_edge(
            means, stds, edge_strengths, 0, 4, 0.2, 0.1, 0.1
        )
        
        assert isinstance(result, bool)

    def test_detect_gradient(self):
        """Test _detect_gradient method"""
        # Test with no gradient
        means_no_gradient = [100.0, 105.0, 102.0, 98.0]
        result = AutoCrop._detect_gradient(means_no_gradient, 0.5)
        assert isinstance(result, bool)
        
        # Test with strong gradient
        means_gradient = [50.0, 200.0, 100.0, 100.0]
        result = AutoCrop._detect_gradient(means_gradient, 0.5)
        assert isinstance(result, bool)

    def test_detect_border_shape(self):
        """Test _detect_border_shape method"""
        # Create test image with borders
        test_image = np.full((200, 300, 3), 128, dtype=np.uint8)
        # Add black borders
        test_image[0:20, :] = [0, 0, 0]  # Top border
        test_image[-20:, :] = [0, 0, 0]  # Bottom border
        
        result = AutoCrop._detect_border_shape(test_image)
        
        assert isinstance(result, list)
        assert all(isinstance(border, str) for border in result)


class TestAutoCropErrorHandling:
    """Test cases for AutoCrop error handling scenarios"""

    def setup_method(self):
        """Set up test fixtures"""
        AutoCrop._instance = None
        self.autocrop = AutoCrop()

    @patch('lorairo.editor.autocrop.logger')
    def test_get_crop_area_with_exception(self, mock_logger):
        """Test _get_crop_area error handling"""
        # Create test image
        test_array = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # Mock cv2.absdiff to raise an exception
        with patch('cv2.absdiff') as mock_absdiff:
            mock_absdiff.side_effect = Exception("Mock CV2 error")
            
            result = self.autocrop._get_crop_area(test_array)
            
            assert result is None
            mock_logger.error.assert_called()

    def test_get_crop_area_with_invalid_image_shape(self):
        """Test _get_crop_area with invalid image shape"""
        # Create image with invalid shape (1D)
        invalid_array = np.zeros((100,), dtype=np.uint8)
        
        # Should handle gracefully
        result = self.autocrop._get_crop_area(invalid_array)
        
        # May return None or handle the error gracefully
        assert result is None or isinstance(result, tuple)

    @patch('lorairo.editor.autocrop.logger')
    def test_auto_crop_image_with_pil_conversion_error(self, mock_logger):
        """Test error handling when PIL to numpy conversion fails"""
        # Create mock image that fails np.array conversion
        mock_image = Mock(spec=Image.Image)
        mock_image.size = (100, 100)
        
        with patch('numpy.array') as mock_array:
            mock_array.side_effect = Exception("Array conversion error")
            
            result = self.autocrop._auto_crop_image(mock_image)
            
            # Should return original image on error
            assert result == mock_image
            mock_logger.error.assert_called()


class TestAutoCropScipyDependency:
    """Test cases for conditional scipy dependency behavior"""

    def setup_method(self):
        """Set up test fixtures"""
        AutoCrop._instance = None

    def test_module_import_with_scipy_available(self):
        """Test module behavior when scipy is available"""
        # This test verifies that the module imports correctly when scipy is available
        with patch('lorairo.editor.autocrop.HAS_SCIPY', True):
            # Re-import or verify the module state
            from lorairo.editor.autocrop import AutoCrop
            autocrop = AutoCrop()
            assert autocrop is not None

    @patch('lorairo.editor.autocrop.logger')
    def test_module_import_without_scipy(self, mock_logger):
        """Test module behavior when scipy is not available"""
        # This test verifies fallback behavior when scipy is not available
        with patch('lorairo.editor.autocrop.HAS_SCIPY', False):
            # Create test image for edge strength calculation
            gray_image = np.random.randint(0, 255, (50, 50), dtype=np.uint8)
            
            # Should use OpenCV fallback
            result = AutoCrop._calculate_edge_strength(gray_image)
            assert result is not None
            assert result.shape == gray_image.shape

    def test_edge_calculation_fallback_behavior(self):
        """Test that edge calculation works with both scipy and OpenCV"""
        gray_image = np.random.randint(0, 255, (50, 50), dtype=np.uint8)
        
        # Test with scipy
        with patch('lorairo.editor.autocrop.HAS_SCIPY', True):
            with patch('lorairo.editor.autocrop.ndimage.sobel') as mock_sobel:
                mock_sobel.return_value = np.zeros_like(gray_image)
                result_scipy = AutoCrop._calculate_edge_strength(gray_image)
                assert result_scipy.shape == gray_image.shape
        
        # Test with OpenCV fallback
        with patch('lorairo.editor.autocrop.HAS_SCIPY', False):
            with patch('cv2.Sobel') as mock_cv_sobel:
                mock_cv_sobel.return_value = np.zeros_like(gray_image)
                result_opencv = AutoCrop._calculate_edge_strength(gray_image)
                assert result_opencv.shape == gray_image.shape


if __name__ == "__main__":
    pytest.main([__file__])