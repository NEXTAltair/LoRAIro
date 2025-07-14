"""
AutoCrop module for image letterbox detection and removal.

This module provides automatic cropping functionality using complementary color
difference algorithm, optimized for letterbox removal in images commonly found
in machine learning datasets.

The AutoCrop algorithm was validated through comprehensive testing and proven
to be the most effective approach for letterbox detection compared to
alternative methods like rembg and border shape detection.
"""

from typing import Optional

import cv2
import numpy as np
from PIL import Image

from ..utils.log import logger

# Handle optional scipy dependency
try:
    from scipy import ndimage

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy.ndimage not available. Some edge detection features may be limited.")


class AutoCrop:
    """
    Automatic image cropping using complementary color difference algorithm.

    This class implements a singleton pattern and provides letterbox detection
    and removal functionality. The algorithm uses complementary color analysis
    combined with OpenCV edge detection to identify and remove uniform borders
    commonly found in letterboxed images.

    The implementation is optimized for machine learning dataset preparation
    where removing letterbox borders improves training data quality.

    Example:
        >>> from lorairo.editor.autocrop import AutoCrop
        >>> from PIL import Image
        >>>
        >>> image = Image.open("letterboxed_image.png")
        >>> cropped = AutoCrop.auto_crop_image(image)
    """

    _instance: Optional["AutoCrop"] = None

    def __new__(cls) -> "AutoCrop":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the AutoCrop instance."""
        pass

    @classmethod
    def auto_crop_image(cls, pil_image: Image.Image) -> Image.Image:
        """
        Main public interface for automatic image cropping.

        This classmethod provides a convenient interface for cropping images
        without needing to manage instance creation.

        Args:
            pil_image: Input PIL Image to be cropped

        Returns:
            Cropped PIL Image, or original image if no crop area detected

        Example:
            >>> image = Image.open("test.png")
            >>> cropped = AutoCrop.auto_crop_image(image)
        """
        instance = cls()
        return instance._auto_crop_image(pil_image)

    @staticmethod
    def _convert_to_gray(image: np.ndarray) -> np.ndarray:
        """
        Convert RGB or RGBA image to grayscale.

        Args:
            image: Input image array with shape (H, W) or (H, W, C)

        Returns:
            Grayscale image array with shape (H, W)

        Raises:
            ValueError: If image format is not supported
        """
        if image.ndim == 2:
            return image
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if image.shape[2] == 4:
            return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_RGBA2RGB), cv2.COLOR_RGB2GRAY)
        raise ValueError(f"サポートされていない画像形式です。形状: {image.shape}")

    @staticmethod
    def _calculate_edge_strength(gray_image: np.ndarray) -> np.ndarray:
        """
        Calculate edge strength using Sobel filter.

        Args:
            gray_image: Grayscale image array

        Returns:
            Edge strength array with same shape as input
        """
        if HAS_SCIPY:
            return ndimage.sobel(gray_image)
        else:
            # Fallback to OpenCV Sobel if scipy not available
            return cv2.Sobel(gray_image, cv2.CV_64F, 1, 1, ksize=3)

    @staticmethod
    def _get_slices(height: int, width: int) -> list[tuple[slice, slice]]:
        """
        Define slice regions for border detection analysis.

        Creates slices for top, bottom, left, right borders and center region
        used in statistical analysis for border detection.

        Args:
            height: Image height in pixels
            width: Image width in pixels

        Returns:
            List of slice tuples for (top, bottom, left, right, center) regions
        """
        return [
            (slice(0, height // 20), slice(None)),  # top
            (slice(-height // 20, None), slice(None)),  # bottom
            (slice(None), slice(0, width // 20)),  # left
            (slice(None), slice(-width // 20, None)),  # right
            (slice(height // 5, 4 * height // 5), slice(width // 5, 4 * width // 5)),  # center
        ]

    @staticmethod
    def _calculate_region_statistics(
        gray_image: np.ndarray, edges: np.ndarray, slices: list[tuple[slice, slice]]
    ) -> tuple[list[float], list[float], list[float]]:
        """
        Calculate statistical measures for image regions.

        Args:
            gray_image: Grayscale image array
            edges: Edge strength array
            slices: List of slice tuples defining regions

        Returns:
            Tuple of (means, standard_deviations, edge_strengths) for each region
        """
        means = [np.mean(gray_image[s]) for s in slices]
        stds = [np.std(gray_image[s]) for s in slices]
        edge_strengths = [np.mean(edges[s]) for s in slices]
        return means, stds, edge_strengths

    @staticmethod
    def _evaluate_edge(
        means: list[float],
        stds: list[float],
        edge_strengths: list[float],
        edge_index: int,
        center_index: int,
        color_threshold: float,
        std_threshold: float,
        edge_threshold: float,
    ) -> bool:
        """
        Evaluate whether a border edge should be considered for cropping.

        Args:
            means: Mean intensity values for regions
            stds: Standard deviation values for regions
            edge_strengths: Edge strength values for regions
            edge_index: Index of the edge region to evaluate
            center_index: Index of the center region for comparison
            color_threshold: Minimum color difference threshold
            std_threshold: Maximum standard deviation threshold for uniformity
            edge_threshold: Minimum edge strength threshold

        Returns:
            True if edge qualifies for cropping, False otherwise
        """
        color_diff = abs(means[edge_index] - means[center_index]) / 255
        is_uniform = stds[edge_index] < std_threshold * 255
        has_strong_edge = edge_strengths[edge_index] > edge_threshold * 255
        return color_diff > color_threshold and (is_uniform or has_strong_edge)

    @staticmethod
    def _detect_gradient(means: list[float], gradient_threshold: float) -> bool:
        """
        Detect gradients that indicate the image should not be cropped.

        Args:
            means: Mean intensity values for border regions
            gradient_threshold: Threshold for gradient detection

        Returns:
            True if gradient detected (should not crop), False otherwise
        """
        vertical_gradient = abs(means[0] - means[1]) / 255
        horizontal_gradient = abs(means[2] - means[3]) / 255
        return vertical_gradient > gradient_threshold or horizontal_gradient > gradient_threshold

    @staticmethod
    def _detect_border_shape(
        image: np.ndarray,
        color_threshold: float = 0.15,
        std_threshold: float = 0.05,
        edge_threshold: float = 0.1,
        gradient_threshold: float = 0.5,
    ) -> list[str]:
        """
        Detect border shapes using statistical analysis.

        This method analyzes image regions to detect uniform borders that
        can be safely cropped. It's primarily used for legacy compatibility
        but the main cropping algorithm uses complementary color analysis.

        Args:
            image: Input image array
            color_threshold: Minimum color difference for border detection
            std_threshold: Maximum standard deviation for uniformity
            edge_threshold: Minimum edge strength threshold
            gradient_threshold: Threshold for gradient detection

        Returns:
            List of detected border names: ["TOP", "BOTTOM", "LEFT", "RIGHT"]
        """
        height, width = image.shape[:2]
        gray_image = AutoCrop._convert_to_gray(image)
        edges = AutoCrop._calculate_edge_strength(gray_image)
        slices = AutoCrop._get_slices(height, width)
        means, stds, edge_strengths = AutoCrop._calculate_region_statistics(gray_image, edges, slices)

        detected_borders = []
        if AutoCrop._evaluate_edge(
            means, stds, edge_strengths, 0, 4, color_threshold, std_threshold, edge_threshold
        ):
            detected_borders.append("TOP")
        if AutoCrop._evaluate_edge(
            means, stds, edge_strengths, 1, 4, color_threshold, std_threshold, edge_threshold
        ):
            detected_borders.append("BOTTOM")
        if AutoCrop._evaluate_edge(
            means, stds, edge_strengths, 2, 4, color_threshold, std_threshold, edge_threshold
        ):
            detected_borders.append("LEFT")
        if AutoCrop._evaluate_edge(
            means, stds, edge_strengths, 3, 4, color_threshold, std_threshold, edge_threshold
        ):
            detected_borders.append("RIGHT")

        if AutoCrop._detect_gradient(means, gradient_threshold):
            return []  # グラデーションが検出された場合は境界なしとする

        return detected_borders

    def _get_crop_area(self, np_image: np.ndarray) -> tuple[int, int, int, int] | None:
        """
        Detect crop area using complementary color difference algorithm.

        This is the core algorithm that implements complementary color analysis
        for letterbox detection. It has been validated as the most effective
        approach for this use case.

        Args:
            np_image: Input image as numpy array

        Returns:
            Crop area as (x, y, width, height) tuple, or None if no crop detected
        """
        try:
            # Complementary color-based crop area detection
            complementary_color = [255 - np.mean(np_image[..., i]) for i in range(3)]
            background = np.full(np_image.shape, complementary_color, dtype=np.uint8)
            diff = cv2.absdiff(np_image, background)

            # Convert difference to grayscale
            gray_diff = self._convert_to_gray(diff)

            # Apply blur to reduce noise
            blurred_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)

            # Dynamic parameter calculation
            height, width = np_image.shape[:2]

            # Adjust blockSize based on image size (must be odd)
            block_size = max(11, min(width, height) // 50)
            if block_size % 2 == 0:
                block_size += 1

            # Adjust C value based on image brightness
            mean_brightness = np.mean(gray_diff)
            adaptive_c = max(2, int(mean_brightness / 32))

            # Adaptive thresholding with optimized parameters
            thresh = cv2.adaptiveThreshold(
                blurred_diff,  # Use grayscaled difference image
                255,  # Maximum value (white)
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # Adaptive threshold type (Gaussian)
                cv2.THRESH_BINARY,  # Binary threshold (white or black)
                block_size,  # Dynamically adjusted neighborhood size
                adaptive_c,  # Dynamically adjusted subtraction constant
            )

            # Optimize Canny edge detection using Otsu's automatic threshold
            otsu_threshold, _ = cv2.threshold(blurred_diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            high_threshold = otsu_threshold
            low_threshold = high_threshold * 0.3

            # Edge detection with dynamic thresholds
            edges = cv2.Canny(thresh, threshold1=int(low_threshold), threshold2=int(high_threshold))

            # Contour detection
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                x_min, y_min, x_max, y_max = np_image.shape[1], np_image.shape[0], 0, 0
                for contour in contours:
                    x, y, w, h = cv2.boundingRect(contour)
                    x_min, y_min = min(x_min, x), min(y_min, y)
                    x_max, y_max = max(x_max, x + w), max(y_max, y + h)

                # Use mask processing to determine crop area
                mask = np.zeros(np_image.shape[:2], dtype=np.uint8)
                for contour in contours:
                    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

                # Get coordinates of white regions in mask
                y_coords, x_coords = np.where(mask == 255)
                if len(x_coords) > 0 and len(y_coords) > 0:
                    x_min, y_min = int(np.min(x_coords)), int(np.min(y_coords))
                    x_max, y_max = int(np.max(x_coords)), int(np.max(y_coords))

                    # Add margin to trim excess regions
                    # TODO: This logic should be reviewed for appropriateness
                    margin = 5  # Number of pixels to trim
                    x_min = max(0, x_min + margin)
                    y_min = max(0, y_min + margin)
                    x_max = min(np_image.shape[1], x_max - margin)
                    y_max = min(np_image.shape[0], y_max - margin)

                    return x_min, y_min, x_max - x_min, y_max - y_min
            return None
        except Exception as e:
            logger.error(f"AutoCrop._get_crop_area: クロップ領域の検出中にエラーが発生しました: {e}")
            return None

    def _auto_crop_image(self, pil_image: Image.Image) -> Image.Image:
        """
        Perform automatic cropping on a PIL Image.

        This method handles the complete cropping workflow including
        error handling and logging.

        Args:
            pil_image: Input PIL Image to be processed

        Returns:
            Cropped PIL Image, or original image if cropping fails or
            no crop area is detected
        """
        try:
            np_image = np.array(pil_image)
            crop_area = self._get_crop_area(np_image)

            # Output debug information
            logger.debug(f"Crop area: {crop_area}")
            logger.debug(f"Original image size: {pil_image.size}")

            if crop_area:
                x, y, w, h = crop_area
                right, bottom = x + w, y + h
                cropped_image = pil_image.crop((x, y, right, bottom))
                logger.debug(f"Cropped image size: {cropped_image.size}")
                return cropped_image
            else:
                logger.debug("No crop area detected, returning original image")
                return pil_image
        except Exception as e:
            logger.error(f"自動クロップ処理中にエラーが発生しました: {e}")
            return pil_image
