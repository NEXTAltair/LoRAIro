"""
AutoCrop module for image letterbox detection and removal.

This module provides automatic cropping functionality using complementary color
difference algorithm, optimized for letterbox removal in images commonly found
in machine learning datasets.

The AutoCrop algorithm was validated through comprehensive testing and proven
to be the most effective approach for letterbox detection compared to
alternative methods like rembg and border shape detection.
"""

from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image

from ..utils.log import logger


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
        >>> from lorairo.image_transforms.autocrop import AutoCrop
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
    def _convert_to_gray(image: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
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

    def _normalize_to_rgb(self, np_image: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        """グレースケール・RGBA・LA 画像を RGB 3ch 配列に正規化する。

        Args:
            np_image: 入力画像 (Grayscale / RGBA / LA / RGB)。

        Returns:
            RGB 3ch に変換された画像配列。
        """
        # グレースケール(2D)対応: RGB変換
        if np_image.ndim == 2:
            logger.debug("グレースケール画像検出: RGB変換を実行")
            return cv2.cvtColor(np_image, cv2.COLOR_GRAY2RGB)

        # RGBA対応: アルファチャンネルを破棄してRGB変換
        if np_image.ndim == 3 and np_image.shape[2] == 4:
            logger.debug("RGBA画像検出: RGB変換を実行")
            return cv2.cvtColor(np_image, cv2.COLOR_RGBA2RGB)

        # LA(グレースケール+アルファ)対応: アルファを破棄しグレースケール→RGB変換
        if np_image.ndim == 3 and np_image.shape[2] == 2:
            logger.debug("LA画像検出(2ch): グレースケール→RGB変換を実行")
            return cv2.cvtColor(np_image[:, :, 0], cv2.COLOR_GRAY2RGB)

        return np_image

    def _compute_adaptive_threshold_params(
        self, gray_diff: np.ndarray[Any, Any], shape: tuple[int, int]
    ) -> tuple[int, int]:
        """適応的閾値処理のパラメータ (blockSize, C値) を画像サイズ・輝度から算出する。

        Args:
            gray_diff: グレースケール差分画像。
            shape: 画像の (height, width)。

        Returns:
            (block_size, adaptive_c) のタプル。
        """
        height, width = shape
        # blockSize は奇数かつ画像サイズに比例 (最小 11)
        block_size = max(11, min(width, height) // 50)
        if block_size % 2 == 0:
            block_size += 1

        mean_brightness = np.mean(gray_diff)
        adaptive_c = max(2, int(mean_brightness / 32))
        return block_size, adaptive_c

    def _get_crop_area(self, np_image: np.ndarray[Any, Any]) -> tuple[int, int, int, int] | None:
        """
        Detect crop area using complementary color difference algorithm.

        This is the core algorithm that implements complementary color analysis
        for letterbox detection. It has been validated as the most effective
        approach for this use case.

        Supports RGB, RGBA, LA, and grayscale images. Non-RGB images are converted
        to RGB before processing (RGBA/LA discards alpha, grayscale expands to 3ch).

        The algorithm applies a dynamic margin based on the detected bounding box size:
        - Formula: margin_x = max(2, int(bbox_width * 0.005)), margin_y = max(2, int(bbox_height * 0.005))
        - Minimum margin: 2px to protect small content
        - Safety check: Each axis applies margin independently (bbox_width > 2 * margin_x, bbox_height > 2 * margin_y)
        - Axis-specific: Non-square bounding boxes apply margin per axis (e.g., wide bbox skips y-margin only)

        Args:
            np_image: Input image as numpy array (RGB, RGBA, or grayscale)

        Returns:
            Crop area as (x, y, width, height) tuple, or None if no crop detected
        """
        try:
            np_image = self._normalize_to_rgb(np_image)

            # Complementary color-based crop area detection
            complementary_color = [255 - np.mean(np_image[..., i]) for i in range(3)]
            background = np.full(np_image.shape, complementary_color, dtype=np.uint8)
            diff = cv2.absdiff(np_image, background)

            # Convert difference to grayscale
            gray_diff = self._convert_to_gray(diff)

            # Apply blur to reduce noise
            blurred_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)

            height, width = np_image.shape[:2]
            block_size, adaptive_c = self._compute_adaptive_threshold_params(gray_diff, (height, width))

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

                    # Calculate dynamic margin based on detected bounding box size
                    # Formula: 0.5% of bbox dimension per axis, minimum 2px
                    # Rationale: Margin should scale with detected content, not canvas size
                    # Safety check prevents negative crop dimensions for small bboxes
                    bbox_width = x_max - x_min
                    bbox_height = y_max - y_min

                    margin_x = max(2, int(bbox_width * 0.005))
                    margin_y = max(2, int(bbox_height * 0.005))

                    # Apply margin independently per axis
                    if bbox_width > 2 * margin_x:
                        x_min = max(0, x_min + margin_x)
                        x_max = min(width, x_max - margin_x)
                        logger.debug(f"Applied x-axis margin: {margin_x}px")
                    else:
                        logger.debug(
                            f"Bbox width too small for x-margin ({bbox_width} <= {2 * margin_x}), "
                            f"skipping x-margin"
                        )

                    if bbox_height > 2 * margin_y:
                        y_min = max(0, y_min + margin_y)
                        y_max = min(height, y_max - margin_y)
                        logger.debug(f"Applied y-axis margin: {margin_y}px")
                    else:
                        logger.debug(
                            f"Bbox height too small for y-margin ({bbox_height} <= {2 * margin_y}), "
                            f"skipping y-margin"
                        )

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
