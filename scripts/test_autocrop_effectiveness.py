#!/usr/bin/env python3
"""
AutoCrop効果確認スクリプト

このスクリプトは、AutoCropの最適化前後の効果を視覚的に比較します。
テスト画像を生成し、従来のパラメータと最適化されたパラメータでの
クロップ結果を比較して効果を確認します。
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
import time
from typing import Optional

# rembg依存関係チェック
try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    print("Warning: rembg not found. Install with: UV_PROJECT_ENVIRONMENT=.venv_linux uv add rembg")
    REMBG_AVAILABLE = False

# 依存関係チェック
try:
    import scipy.ndimage
except ImportError:
    print("Warning: scipy.ndimage not found. Border detection may not work properly.")
    print("Install with: UV_PROJECT_ENVIRONMENT=.venv_linux uv add scipy")

# プロジェクトルートを追加
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))

from lorairo.editor.image_processor import AutoCrop


class LegacyAutoCrop:
    """境界形状検出ベースのAutoCropレガシー実装（真のレガシー手法）"""
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LegacyAutoCrop, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初期化処理（ロガー設定は簡略化）"""
        pass

    @classmethod
    def auto_crop_image(cls, pil_image: Image.Image) -> Image.Image:
        """クラスメソッドインターフェース（後方互換性）"""
        instance = cls()
        return instance._auto_crop_image(pil_image)

    def crop_image(self, pil_image: Image.Image) -> tuple[Image.Image, dict]:
        """
        境界形状検出によるクロップ（統合インターフェース）
        
        Returns:
            tuple: (cropped_image, crop_info)
        """
        start_time = time.time()
        
        try:
            # NumPy配列に変換
            np_image = np.array(pil_image)
            
            # 境界形状検出
            detected_borders = self._safe_detect_border_shape(np_image)
            
            # クロップ実行
            if detected_borders:
                crop_box = self._borders_to_crop_box(np_image.shape, detected_borders)
                x, y, w, h = crop_box
                cropped_img = pil_image.crop((x, y, x + w, y + h))
                
                crop_info = {
                    "detected": True,
                    "method": "border_shape_detection",
                    "borders_found": detected_borders,
                    "original_size": pil_image.size,
                    "crop_box": crop_box,
                    "cropped_size": cropped_img.size,
                    "crop_ratio": (w * h) / (pil_image.size[0] * pil_image.size[1]),
                    "processing_time": time.time() - start_time,
                    "contours_found": len(detected_borders)  # 互換性のため
                }
            else:
                cropped_img = pil_image.copy()
                crop_info = {
                    "detected": False,
                    "method": "border_shape_detection",
                    "borders_found": [],
                    "original_size": pil_image.size,
                    "crop_box": None,
                    "cropped_size": pil_image.size,
                    "crop_ratio": 1.0,
                    "processing_time": time.time() - start_time,
                    "contours_found": 0  # 互換性のため
                }
            
            return cropped_img, crop_info
            
        except Exception as e:
            # エラー時は元画像を返す
            print(f"LegacyAutoCrop error: {e}")
            cropped_img = pil_image.copy()
            crop_info = {
                "detected": False,
                "method": "border_shape_detection",
                "error": str(e),
                "original_size": pil_image.size,
                "crop_box": None,
                "cropped_size": pil_image.size,
                "crop_ratio": 1.0,
                "processing_time": time.time() - start_time,
                "contours_found": 0
            }
            return cropped_img, crop_info


class RembgAutoCrop:
    """rembgベースの背景除去AutoCrop実装"""
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RembgAutoCrop, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初期化処理"""
        if not REMBG_AVAILABLE:
            print("Warning: rembg not available, RembgAutoCrop will return original images")

    def crop_image(self, pil_image: Image.Image) -> tuple[Image.Image, dict]:
        """
        rembgによる背景除去ベースのクロップ（最適化パラメータ適用）
        
        Returns:
            tuple: (cropped_image, crop_info)
        """
        start_time = time.time()
        
        if not REMBG_AVAILABLE:
            crop_info = {
                "detected": False,
                "method": "rembg_background_removal_optimized",
                "error": "rembg_not_available",
                "original_size": pil_image.size,
                "crop_box": None,
                "cropped_size": pil_image.size,
                "crop_ratio": 1.0,
                "processing_time": time.time() - start_time,
                "contours_found": 0
            }
            return pil_image.copy(), crop_info
        
        try:
            # 最適化されたパラメータでrembg実行（調査結果に基づく）
            from rembg import new_session
            
            # BiRefNet優先で高品質処理、フォールバック付き
            models_to_try = ["birefnet-general", "u2net", "u2netp"]
            
            for model_name in models_to_try:
                try:
                    session = new_session(model_name)
                    
                    # 最適化パラメータ（調査結果より）
                    optimized_params = {
                        "session": session,
                        "alpha_matting": True,
                        "alpha_matting_foreground_threshold": 270,  # デフォルト240→270（前景保持強化）
                        "alpha_matting_background_threshold": 15,   # デフォルト10→15（背景除去強化）
                        "alpha_matting_erode_size": 8,              # デフォルト10→8（エッジ品質向上）
                        "post_process_mask": True                   # マスクスムージング有効化
                    }
                    
                    with_alpha = remove(pil_image, **optimized_params)
                    break  # 成功したらループ終了
                    
                except Exception as model_error:
                    print(f"Model {model_name} failed: {model_error}, trying next...")
                    continue
            else:
                # 全モデル失敗時はデフォルトで実行
                with_alpha = remove(pil_image)
            
            # アルファチャンネルからマスクを作成
            if with_alpha.mode == 'RGBA':
                # アルファチャンネル取得
                alpha = with_alpha.split()[-1]
                alpha_array = np.array(alpha)
                
                # 最適化された非透明領域検出（調査結果適用）
                # アンチエイリアシング対応で閾値を調整
                non_transparent = alpha_array > 10  # 0→10（アンチエイリアシング対応）
                
                if np.any(non_transparent):
                    # 非透明領域の境界ボックスを計算
                    coords = np.where(non_transparent)
                    y_min, y_max = coords[0].min(), coords[0].max()
                    x_min, x_max = coords[1].min(), coords[1].max()
                    
                    # 最適化されたマージン計算（画像サイズ適応型）
                    height, width = alpha_array.shape
                    margin = max(2, min(width, height) // 200)  # 固定5→適応型
                    y_min = max(0, y_min - margin)
                    y_max = min(height, y_max + margin)
                    x_min = max(0, x_min - margin)
                    x_max = min(width, x_max + margin)
                    
                    # 元画像をクロップ
                    cropped_img = pil_image.crop((x_min, y_min, x_max, y_max))
                    
                    crop_info = {
                        "detected": True,
                        "method": "rembg_background_removal_optimized",
                        "model_used": model_name if 'model_name' in locals() else "default",
                        "alpha_matting_enabled": True,
                        "optimized_parameters": "applied",
                        "original_size": pil_image.size,
                        "crop_box": (x_min, y_min, x_max - x_min, y_max - y_min),
                        "cropped_size": cropped_img.size,
                        "crop_ratio": ((x_max - x_min) * (y_max - y_min)) / (width * height),
                        "processing_time": time.time() - start_time,
                        "contours_found": 1,  # 互換性のため
                        "alpha_coverage": np.sum(non_transparent) / (width * height)
                    }
                    return cropped_img, crop_info
                else:
                    # 非透明領域が見つからない場合
                    cropped_img = pil_image.copy()
                    crop_info = {
                        "detected": False,
                        "method": "rembg_background_removal_optimized", 
                        "error": "no_foreground_detected",
                        "model_attempted": model_name if 'model_name' in locals() else "default",
                        "original_size": pil_image.size,
                        "crop_box": None,
                        "cropped_size": pil_image.size,
                        "crop_ratio": 1.0,
                        "processing_time": time.time() - start_time,
                        "contours_found": 0,
                        "alpha_coverage": 0.0
                    }
                    return cropped_img, crop_info
            else:
                # アルファチャンネルがない場合
                cropped_img = pil_image.copy()
                crop_info = {
                    "detected": False,
                    "method": "rembg_background_removal_optimized",
                    "error": "no_alpha_channel",
                    "model_attempted": model_name if 'model_name' in locals() else "default",
                    "original_size": pil_image.size,
                    "crop_box": None,
                    "cropped_size": pil_image.size,
                    "crop_ratio": 1.0,
                    "processing_time": time.time() - start_time,
                    "contours_found": 0
                }
                return cropped_img, crop_info
                
        except Exception as e:
            print(f"RembgAutoCrop error: {e}")
            cropped_img = pil_image.copy()
            crop_info = {
                "detected": False,
                "method": "rembg_background_removal_optimized",
                "error": str(e),
                "fallback_attempted": True,
                "original_size": pil_image.size,
                "crop_box": None,
                "cropped_size": pil_image.size,
                "crop_ratio": 1.0,
                "processing_time": time.time() - start_time,
                "contours_found": 0
            }
            return cropped_img, crop_info

    def _safe_detect_border_shape(self, image: np.ndarray) -> list[str]:
        """安全な境界形状検出（エラーハンドリング付き）"""
        try:
            return LegacyAutoCrop._detect_border_shape(image)
        except Exception as e:
            print(f"Border shape detection failed: {e}")
            return []

    def _borders_to_crop_box(self, img_shape: tuple, borders: list[str]) -> tuple[int, int, int, int]:
        """
        境界リストをクロップボックスに変換
        
        Args:
            img_shape: (height, width, channels)
            borders: ["TOP", "BOTTOM", "LEFT", "RIGHT"] の組み合わせ
            
        Returns:
            (x, y, width, height): クロップボックス
        """
        height, width = img_shape[:2]
        
        # 初期値: 全体の画像
        crop_x, crop_y = 0, 0
        crop_width, crop_height = width, height
        
        # 境界サイズの計算（画像サイズの5%）
        vertical_margin = max(1, height // 20)
        horizontal_margin = max(1, width // 20)
        
        # 各境界に応じてクロップ領域を調整
        if "TOP" in borders:
            crop_y += vertical_margin
            crop_height -= vertical_margin
            
        if "BOTTOM" in borders:
            crop_height -= vertical_margin
            
        if "LEFT" in borders:
            crop_x += horizontal_margin
            crop_width -= horizontal_margin
            
        if "RIGHT" in borders:
            crop_width -= horizontal_margin
        
        # 最小サイズの保証（元サイズの10%以上）
        min_width = max(1, width // 10)
        min_height = max(1, height // 10)
        crop_width = max(crop_width, min_width)
        crop_height = max(crop_height, min_height)
        
        # 境界チェック
        crop_x = max(0, min(crop_x, width - crop_width))
        crop_y = max(0, min(crop_y, height - crop_height))
        
        return (crop_x, crop_y, crop_width, crop_height)

    @staticmethod
    def _convert_to_gray(image: np.ndarray) -> np.ndarray:
        """RGBまたはRGBA画像をグレースケールに変換する"""
        if image.ndim == 2:
            return image
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if image.shape[2] == 4:
            return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_RGBA2RGB), cv2.COLOR_RGB2GRAY)
        raise ValueError(f"サポートされていない画像形式です。形状: {image.shape}")

    @staticmethod
    def _calculate_edge_strength(gray_image: np.ndarray) -> np.ndarray:
        """グレースケール画像でエッジの強さを計算する"""
        try:
            return scipy.ndimage.sobel(gray_image)
        except:
            # scipy.ndimageが利用できない場合のフォールバック
            return cv2.Sobel(gray_image, cv2.CV_64F, 1, 1, ksize=3)

    @staticmethod
    def _get_slices(height: int, width: int) -> list[tuple[slice, slice]]:
        """画像の特定の領域（上下左右および中央）をスライスで定義する"""
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
        """各領域の平均値、標準偏差、およびエッジ強度を計算する"""
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
        """各辺の評価を行う"""
        color_diff = abs(means[edge_index] - means[center_index]) / 255
        is_uniform = stds[edge_index] < std_threshold * 255
        has_strong_edge = edge_strengths[edge_index] > edge_threshold * 255
        return color_diff > color_threshold and (is_uniform or has_strong_edge)

    @staticmethod
    def _detect_gradient(means: list[float], gradient_threshold: float) -> bool:
        """グラデーションを検出する"""
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
        """境界形状を検出する（提供されたアルゴリズム）"""
        height, width = image.shape[:2]
        gray_image = LegacyAutoCrop._convert_to_gray(image)
        edges = LegacyAutoCrop._calculate_edge_strength(gray_image)
        slices = LegacyAutoCrop._get_slices(height, width)
        means, stds, edge_strengths = LegacyAutoCrop._calculate_region_statistics(gray_image, edges, slices)

        detected_borders = []
        if LegacyAutoCrop._evaluate_edge(means, stds, edge_strengths, 0, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("TOP")
        if LegacyAutoCrop._evaluate_edge(means, stds, edge_strengths, 1, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("BOTTOM")
        if LegacyAutoCrop._evaluate_edge(means, stds, edge_strengths, 2, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("LEFT")
        if LegacyAutoCrop._evaluate_edge(means, stds, edge_strengths, 3, 4, color_threshold, std_threshold, edge_threshold):
            detected_borders.append("RIGHT")

        if LegacyAutoCrop._detect_gradient(means, gradient_threshold):
            return []  # グラデーションが検出された場合は境界なしとする

        return detected_borders

    def _auto_crop_image(self, pil_image: Image.Image) -> Image.Image:
        """
        PIL.Image オブジェクトを受け取り、必要に応じて自動クロップを行います。
        （後方互換性のため）

        Args:
            pil_image (Image.Image): 処理する PIL.Image オブジェクト

        Returns:
            Image.Image: クロップされた（または元の）PIL.Image オブジェクト
        """
        cropped_image, _ = self.crop_image(pil_image)
        return cropped_image


def create_test_image_with_border(size: tuple[int, int], border_width: int = 20, content_type: str = "gradient") -> Image.Image:
    """テスト用の画像を作成（背景とコンテンツ領域を明確に分離）"""
    width, height = size
    
    # 背景（白）
    img_array = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # コンテンツ領域（背景とは明確に異なる）
    content_start_x = border_width
    content_end_x = width - border_width
    content_start_y = border_width
    content_end_y = height - border_width
    
    if content_type == "gradient":
        # グラデーション
        for y in range(content_start_y, content_end_y):
            for x in range(content_start_x, content_end_x):
                intensity = int(((x - content_start_x) / (content_end_x - content_start_x)) * 200 + 50)
                img_array[y, x] = [intensity, intensity // 2, 255 - intensity]
                
    elif content_type == "pattern":
        # チェッカーパターン
        checker_size = 20
        for y in range(content_start_y, content_end_y):
            for x in range(content_start_x, content_end_x):
                if ((x - content_start_x) // checker_size + (y - content_start_y) // checker_size) % 2:
                    img_array[y, x] = [50, 50, 50]
                else:
                    img_array[y, x] = [200, 100, 50]
                    
    elif content_type == "circle":
        # 円形パターン
        center_x = (content_start_x + content_end_x) // 2
        center_y = (content_start_y + content_end_y) // 2
        radius = min(content_end_x - content_start_x, content_end_y - content_start_y) // 3
        
        for y in range(content_start_y, content_end_y):
            for x in range(content_start_x, content_end_x):
                distance = np.sqrt((x - center_x)**2 + (y - center_y)**2)
                if distance < radius:
                    intensity = int((1 - distance / radius) * 200 + 50)
                    img_array[y, x] = [intensity, 100, 255 - intensity]
                else:
                    img_array[y, x] = [80, 80, 80]
    
    return Image.fromarray(img_array)


def create_legacy_autocrop_params(img_size: tuple[int, int], mean_brightness: float) -> dict:
    """従来の固定パラメータ"""
    return {
        "block_size": 11,
        "adaptive_c": 2,
        "canny_low": 30,
        "canny_high": 100,
        "description": "Legacy Fixed Parameters"
    }


def create_optimized_autocrop_params(img_size: tuple[int, int], mean_brightness: float) -> dict:
    """最適化された動的パラメータ"""
    height, width = img_size
    
    # 動的 blockSize 計算
    block_size = max(11, min(width, height) // 50)
    if block_size % 2 == 0:
        block_size += 1
    
    # 動的 adaptive_c 計算
    adaptive_c = max(2, int(mean_brightness / 32))
    
    # Otsu法シミュレーション（簡易版）
    otsu_threshold = mean_brightness
    canny_high = int(otsu_threshold)
    canny_low = int(canny_high * 0.3)
    
    return {
        "block_size": block_size,
        "adaptive_c": adaptive_c,
        "canny_low": canny_low,
        "canny_high": canny_high,
        "description": "Optimized Dynamic Parameters"
    }


def apply_autocrop_with_params(img: Image.Image, params: dict) -> tuple[Image.Image, dict]:
    """指定されたパラメータでAutoCropを適用（補色差分ベース）"""
    start_time = time.time()
    
    # PIL画像をOpenCV形式に変換
    img_array = np.array(img)
    img_rgb = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # 白背景を作成（クロップ検出用）
    white_bg = np.ones_like(img_array) * 255
    
    # グレースケール変換
    gray_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    gray_bg = cv2.cvtColor(white_bg, cv2.COLOR_RGB2GRAY)
    
    # 差分計算
    gray_diff = cv2.absdiff(gray_img, gray_bg)
    
    # ブラー処理
    blurred_diff = cv2.GaussianBlur(gray_diff, (5, 5), 0)
    
    # 適応的しきい値処理（パラメータ使用）
    thresh = cv2.adaptiveThreshold(
        blurred_diff,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        params["block_size"],
        params["adaptive_c"]
    )
    
    # エッジ検出（パラメータ使用）
    edges = cv2.Canny(thresh, params["canny_low"], params["canny_high"])
    
    # 輪郭検出
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # 最大の輪郭を取得
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # クロップ実行
        cropped_img = img.crop((x, y, x + w, y + h))
        
        # 検出情報
        detection_info = {
            "detected": True,
            "method": "complementary_diff",
            "original_size": img.size,
            "crop_box": (x, y, x + w, y + h),
            "cropped_size": (w, h),
            "contours_found": len(contours),
            "crop_ratio": (w * h) / (img.size[0] * img.size[1]),
            "processing_time": time.time() - start_time
        }
    else:
        # 輪郭が見つからない場合は元画像を返す
        cropped_img = img.copy()
        detection_info = {
            "detected": False,
            "method": "complementary_diff",
            "original_size": img.size,
            "crop_box": None,
            "cropped_size": img.size,
            "contours_found": 0,
            "crop_ratio": 1.0,
            "processing_time": time.time() - start_time
        }
    
    return cropped_img, detection_info


def apply_three_autocrop_methods(img: Image.Image, params_opt: dict, params_leg: dict) -> tuple:
    """3つのAutoCrop手法を適用して比較"""
    results = []
    
    # 1. Current Optimized (補色差分・最適化パラメータ)
    opt_result, opt_info = apply_autocrop_with_params(img, params_opt)
    opt_info["method"] = "complementary_diff_optimized"
    opt_info["method_description"] = "Complementary Diff (Optimized)"
    results.append((opt_result, opt_info))
    
    # 2. Current Legacy (補色差分・固定パラメータ)
    leg_result, leg_info = apply_autocrop_with_params(img, params_leg)
    leg_info["method"] = "complementary_diff_legacy"
    leg_info["method_description"] = "Complementary Diff (Legacy)"
    results.append((leg_result, leg_info))
    
    # 3. True Legacy (境界形状検出)
    legacy_autocrop = LegacyAutoCrop()
    true_leg_result, true_leg_info = legacy_autocrop.crop_image(img)
    true_leg_info["method_description"] = "Border Shape Detection"
    results.append((true_leg_result, true_leg_info))
    
    return tuple(results)


def apply_four_autocrop_methods(img: Image.Image, params_opt: dict, params_leg: dict) -> tuple:
    """4つのAutoCrop手法を適用して比較（rembg追加）"""
    results = []
    
    # 1. Current Optimized (補色差分・最適化パラメータ)
    opt_result, opt_info = apply_autocrop_with_params(img, params_opt)
    opt_info["method"] = "complementary_diff_optimized"
    opt_info["method_description"] = "Complementary Diff (Optimized)"
    results.append((opt_result, opt_info))
    
    # 2. Current Legacy (補色差分・固定パラメータ)
    leg_result, leg_info = apply_autocrop_with_params(img, params_leg)
    leg_info["method"] = "complementary_diff_legacy"
    leg_info["method_description"] = "Complementary Diff (Legacy)"
    results.append((leg_result, leg_info))
    
    # 3. True Legacy (境界形状検出)
    legacy_autocrop = LegacyAutoCrop()
    true_leg_result, true_leg_info = legacy_autocrop.crop_image(img)
    true_leg_info["method_description"] = "Border Shape Detection"
    results.append((true_leg_result, true_leg_info))
    
    # 4. Rembg (背景除去ベース)
    rembg_autocrop = RembgAutoCrop()
    rembg_result, rembg_info = rembg_autocrop.crop_image(img)
    rembg_info["method_description"] = "Background Removal (rembg)"
    results.append((rembg_result, rembg_info))
    
    return tuple(results)


def create_comparison_image(original: Image.Image, legacy_result: Image.Image, optimized_result: Image.Image, 
                           legacy_info: dict, optimized_info: dict, test_name: str) -> Image.Image:
    """比較用の画像を作成（2手法版・後方互換性）"""
    
    # 最大サイズを決定
    max_width = max(original.size[0], legacy_result.size[0], optimized_result.size[0])
    max_height = max(original.size[1], legacy_result.size[1], optimized_result.size[1])
    
    # 各画像を同じサイズにリサイズ（パディング）
    target_size = (max_width, max_height)
    
    def pad_image(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        new_img = Image.new("RGB", target_size, (240, 240, 240))
        x_offset = (target_size[0] - img.size[0]) // 2
        y_offset = (target_size[1] - img.size[1]) // 2
        new_img.paste(img, (x_offset, y_offset))
        return new_img
    
    original_padded = pad_image(original, target_size)
    legacy_padded = pad_image(legacy_result, target_size)
    optimized_padded = pad_image(optimized_result, target_size)
    
    # 比較画像作成（横並び）
    text_height = 120
    comparison_width = max_width * 3 + 20  # 余白
    comparison_height = max_height + text_height
    
    comparison = Image.new("RGB", (comparison_width, comparison_height), (255, 255, 255))
    
    # 画像を配置
    comparison.paste(original_padded, (0, text_height))
    comparison.paste(legacy_padded, (max_width, text_height))
    comparison.paste(optimized_padded, (max_width * 2, text_height))
    
    # テキスト描画
    draw = ImageDraw.Draw(comparison)
    
    try:
        # デフォルトフォントを使用
        font = ImageFont.load_default()
    except:
        font = None
    
    # タイトル
    title = f"AutoCrop Comparison: {test_name}"
    draw.text((10, 10), title, fill=(0, 0, 0), font=font)
    
    # 各画像のラベル
    labels = [
        f"Original\n{original.size[0]}x{original.size[1]}",
        f"Legacy\n{legacy_info['cropped_size'][0]}x{legacy_info['cropped_size'][1]}\nRatio: {legacy_info['crop_ratio']:.3f}",
        f"Optimized\n{optimized_info['cropped_size'][0]}x{optimized_info['cropped_size'][1]}\nRatio: {optimized_info['crop_ratio']:.3f}"
    ]
    
    x_positions = [10, max_width + 10, max_width * 2 + 10]
    for i, (label, x_pos) in enumerate(zip(labels, x_positions)):
        draw.text((x_pos, 50), label, fill=(0, 0, 0), font=font)
    
    return comparison


def create_four_method_comparison_image(
    original: Image.Image,
    three_results: tuple,
    test_name: str
) -> Image.Image:
    """4画像の比較画像を作成（オリジナル + 3手法）"""
    
    opt_result, opt_info = three_results[0]
    leg_result, leg_info = three_results[1]
    true_leg_result, true_leg_info = three_results[2]
    
    # 最大サイズ決定
    all_images = [original, opt_result, leg_result, true_leg_result]
    max_width = max(img.size[0] for img in all_images)
    max_height = max(img.size[1] for img in all_images)
    target_size = (max_width, max_height)
    
    # パディング関数
    def pad_image(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        new_img = Image.new("RGB", target_size, (240, 240, 240))
        x_offset = (target_size[0] - img.size[0]) // 2
        y_offset = (target_size[1] - img.size[1]) // 2
        new_img.paste(img, (x_offset, y_offset))
        return new_img
    
    # 画像パディング
    padded_images = [pad_image(img, target_size) for img in all_images]
    
    # 比較画像作成（横4列レイアウト）
    text_height = 160  # 3手法のため情報が多いので高さを増加
    spacing = 10
    comparison_width = max_width * 4 + spacing * 5  # 余白
    comparison_height = max_height + text_height
    
    comparison = Image.new("RGB", (comparison_width, comparison_height), (255, 255, 255))
    
    # 画像配置
    for i, padded_img in enumerate(padded_images):
        x_pos = spacing + i * (max_width + spacing)
        comparison.paste(padded_img, (x_pos, text_height))
    
    # テキスト描画
    draw = ImageDraw.Draw(comparison)
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    # タイトル
    title = f"AutoCrop 3-Method Comparison: {test_name}"


def create_five_method_comparison_image(
    original: Image.Image,
    four_results: tuple,
    test_name: str
) -> Image.Image:
    """5画像の比較画像を作成（オリジナル + 4手法）"""
    
    opt_result, opt_info = four_results[0]
    leg_result, leg_info = four_results[1]
    true_leg_result, true_leg_info = four_results[2]
    rembg_result, rembg_info = four_results[3]
    
    # 最大サイズ決定
    all_images = [original, opt_result, leg_result, true_leg_result, rembg_result]
    max_width = max(img.size[0] for img in all_images)
    max_height = max(img.size[1] for img in all_images)
    target_size = (max_width, max_height)
    
    # パディング関数
    def pad_image(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        new_img = Image.new("RGB", target_size, (240, 240, 240))
        x_offset = (target_size[0] - img.size[0]) // 2
        y_offset = (target_size[1] - img.size[1]) // 2
        new_img.paste(img, (x_offset, y_offset))
        return new_img
    
    # 画像パディング
    padded_images = [pad_image(img, target_size) for img in all_images]
    
    # 比較画像作成（横5列レイアウト）
    text_height = 180  # 4手法のため情報が多いので高さを増加
    spacing = 8
    comparison_width = max_width * 5 + spacing * 6  # 余白
    comparison_height = max_height + text_height
    
    comparison = Image.new("RGB", (comparison_width, comparison_height), (255, 255, 255))
    
    # 画像配置
    for i, padded_img in enumerate(padded_images):
        x_pos = spacing + i * (max_width + spacing)
        comparison.paste(padded_img, (x_pos, text_height))
    
    # テキスト描画
    draw = ImageDraw.Draw(comparison)
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    # タイトル
    title = f"AutoCrop 4-Method Comparison: {test_name}"
    draw.text((10, 10), title, fill=(0, 0, 0), font=font)
    
    # 各画像のラベル
    processing_times = [
        "N/A",
        f"{opt_info.get('processing_time', 0):.3f}s",
        f"{leg_info.get('processing_time', 0):.3f}s", 
        f"{true_leg_info.get('processing_time', 0):.3f}s",
        f"{rembg_info.get('processing_time', 0):.3f}s"
    ]
    
    borders_info = [
        "",
        "",
        "",
        f"Borders: {', '.join(true_leg_info.get('borders_found', [])) if true_leg_info.get('borders_found') else 'None'}",
        f"Alpha: {rembg_info.get('alpha_coverage', 0):.3f}" if 'alpha_coverage' in rembg_info else ""
    ]
    
    labels = [
        f"Original\n{original.size[0]}x{original.size[1]}\n{processing_times[0]}",
        f"Optimized\n{opt_info['cropped_size'][0]}x{opt_info['cropped_size'][1]}\nRatio: {opt_info['crop_ratio']:.3f}\nTime: {processing_times[1]}",
        f"Legacy\n{leg_info['cropped_size'][0]}x{leg_info['cropped_size'][1]}\nRatio: {leg_info['crop_ratio']:.3f}\nTime: {processing_times[2]}",
        f"Border Detection\n{true_leg_info['cropped_size'][0]}x{true_leg_info['cropped_size'][1]}\nRatio: {true_leg_info['crop_ratio']:.3f}\nTime: {processing_times[3]}\n{borders_info[3]}",
        f"Background Removal\n{rembg_info['cropped_size'][0]}x{rembg_info['cropped_size'][1]}\nRatio: {rembg_info['crop_ratio']:.3f}\nTime: {processing_times[4]}\n{borders_info[4]}"
    ]
    
    x_positions = [spacing + i * (max_width + spacing) for i in range(5)]
    for label, x_pos in zip(labels, x_positions):
        draw.text((x_pos, 40), label, fill=(0, 0, 0), font=font)
    
    return comparison


def test_real_images(output_dir: Path):
    """実際の画像でのテスト（2手法版・後方互換性）"""
    print("\n=== 実画像テスト ===")
    
    # テスト画像ディレクトリ
    test_img_dir = Path("tests/resources/img/bordercrop")
    
    if not test_img_dir.exists():
        print(f"テスト画像ディレクトリが見つかりません: {test_img_dir}")
        return []
    
    real_results = []
    
    # ディレクトリ内の画像ファイルを取得
    image_files = list(test_img_dir.glob("*.png")) + list(test_img_dir.glob("*.jpg")) + list(test_img_dir.glob("*.jpeg"))
    
    if not image_files:
        print("テスト画像が見つかりません")
        return []
    
    for img_file in sorted(image_files):
        print(f"\n実画像テスト: {img_file.name}")
        
        try:
            # 画像読み込み
            test_img = Image.open(img_file)
            if test_img.mode != "RGB":
                test_img = test_img.convert("RGB")
            
            # 画像の平均明度計算
            img_array = np.array(test_img)
            mean_brightness = float(np.mean(cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)))
            
            print(f"   画像サイズ: {test_img.size}")
            print(f"   平均明度: {mean_brightness:.1f}")
            
            # パラメータ生成
            legacy_params = create_legacy_autocrop_params(test_img.size, mean_brightness)
            optimized_params = create_optimized_autocrop_params(test_img.size, mean_brightness)
            
            print(f"   Legacy params: block_size={legacy_params['block_size']}, adaptive_c={legacy_params['adaptive_c']}, canny=({legacy_params['canny_low']}, {legacy_params['canny_high']})")
            print(f"   Optimized params: block_size={optimized_params['block_size']}, adaptive_c={optimized_params['adaptive_c']}, canny=({optimized_params['canny_low']}, {optimized_params['canny_high']})")
            
            # AutoCrop適用
            legacy_result, legacy_info = apply_autocrop_with_params(test_img, legacy_params)
            optimized_result, optimized_info = apply_autocrop_with_params(test_img, optimized_params)
            
            # 結果比較画像作成
            comparison_img = create_comparison_image(
                test_img, legacy_result, optimized_result,
                legacy_info, optimized_info, f"Real_{img_file.stem}"
            )
            
            # ファイル保存
            output_path = output_dir / f"Real_{img_file.stem}_comparison.png"
            comparison_img.save(output_path)
            
            print(f"   Legacy検出: {legacy_info['detected']}, クロップ率: {legacy_info['crop_ratio']:.3f}")
            print(f"   Optimized検出: {optimized_info['detected']}, クロップ率: {optimized_info['crop_ratio']:.3f}")
            print(f"   比較画像保存: {output_path}")
            
            # 結果記録
            real_results.append({
                "test_case": f"Real_{img_file.stem}",
                "image_size": test_img.size,
                "mean_brightness": mean_brightness,
                "legacy": legacy_info,
                "optimized": optimized_info,
                "legacy_params": legacy_params,
                "optimized_params": optimized_params,
                "source_file": str(img_file)
            })
            
        except Exception as e:
            print(f"   エラー: {e}")
            continue
    
    return real_results


def test_real_images_three_methods(output_dir: Path) -> list:
    """実画像での3手法テスト"""
    print("\n=== 実画像 3手法テスト ===")
    
    test_img_dir = Path("tests/resources/img/bordercrop")
    if not test_img_dir.exists():
        print(f"テスト画像ディレクトリが見つかりません: {test_img_dir}")
        return []
    
    real_results = []
    image_files = list(test_img_dir.glob("*.png")) + list(test_img_dir.glob("*.jpg")) + list(test_img_dir.glob("*.jpeg"))
    
    for img_file in sorted(image_files):
        print(f"\n実画像 3手法テスト: {img_file.name}")
        
        try:
            test_img = Image.open(img_file)
            if test_img.mode != "RGB":
                test_img = test_img.convert("RGB")
            
            img_array = np.array(test_img)
            mean_brightness = float(np.mean(cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)))
            
            print(f"   画像サイズ: {test_img.size}, 平均明度: {mean_brightness:.1f}")
            
            # パラメータ生成
            legacy_params = create_legacy_autocrop_params(test_img.size, mean_brightness)
            optimized_params = create_optimized_autocrop_params(test_img.size, mean_brightness)
            
            # 3手法適用
            three_results = apply_three_autocrop_methods(test_img, optimized_params, legacy_params)
            
            # 比較画像作成
            comparison_img = create_four_method_comparison_image(test_img, three_results, f"Real_{img_file.stem}")
            
            # ファイル保存
            output_path = output_dir / f"Real_{img_file.stem}_three_methods_comparison.png"
            comparison_img.save(output_path)
            
            # 結果記録
            opt_info, leg_info, true_leg_info = [result[1] for result in three_results]
            
            real_results.append({
                "test_case": f"Real_{img_file.stem}",
                "source_file": str(img_file),
                "image_size": test_img.size,
                "mean_brightness": mean_brightness,
                "optimized": opt_info,
                "legacy": leg_info,
                "border_detection": true_leg_info
            })
            
            print(f"   比較画像保存: {output_path}")
            
        except Exception as e:
            print(f"   エラー: {e}")
            continue
    
    return real_results


def print_three_method_summary(results: list, real_results: list):
    """3手法の結果サマリーを出力"""
    print("\n=== 3手法比較結果サマリー ===")
    
    if results:
        print("\n--- 合成画像テスト ---")
        for result in results:
            print(f"\n{result['test_case']}:")
            print(f"  画像サイズ: {result['image_size']}")
            print(f"  Optimized: 検出={result['optimized']['detected']}, ratio={result['optimized']['crop_ratio']:.3f}, time={result['optimized']['processing_time']:.3f}s")
            print(f"  Legacy: 検出={result['legacy']['detected']}, ratio={result['legacy']['crop_ratio']:.3f}, time={result['legacy']['processing_time']:.3f}s")
            print(f"  Border Detection: 検出={result['border_detection']['detected']}, ratio={result['border_detection']['crop_ratio']:.3f}, time={result['border_detection']['processing_time']:.3f}s")
            print(f"  Detected Borders: {result['border_detection']['borders_found']}")
    
    if real_results:
        print("\n--- 実画像テスト ---")
        for result in real_results:
            print(f"\n{result['test_case']}:")
            print(f"  ソース: {Path(result['source_file']).name}")
            print(f"  画像サイズ: {result['image_size']}")
            print(f"  Optimized: ratio={result['optimized']['crop_ratio']:.3f}, time={result['optimized']['processing_time']:.3f}s")
            print(f"  Legacy: ratio={result['legacy']['crop_ratio']:.3f}, time={result['legacy']['processing_time']:.3f}s")
            print(f"  Border Detection: ratio={result['border_detection']['crop_ratio']:.3f}, time={result['border_detection']['processing_time']:.3f}s")
            print(f"  Detected Borders: {result['border_detection']['borders_found']}")
    
    # パフォーマンス比較
    print("\n--- パフォーマンス比較 ---")
    all_results = results + real_results
    if all_results:
        opt_times = [r['optimized']['processing_time'] for r in all_results]
        leg_times = [r['legacy']['processing_time'] for r in all_results]
        border_times = [r['border_detection']['processing_time'] for r in all_results]
        
        print(f"平均処理時間:")
        print(f"  Optimized: {sum(opt_times)/len(opt_times):.3f}s")
        print(f"  Legacy: {sum(leg_times)/len(leg_times):.3f}s")
        print(f"  Border Detection: {sum(border_times)/len(border_times):.3f}s")
    
    print(f"\nテスト完了: 合成画像 {len(results)} 件, 実画像 {len(real_results)} 件")
    print("3手法の比較により、AutoCropアルゴリズムの特性差を確認できます。")


def main():
    """メイン処理（3手法比較対応）"""
    print("=== AutoCrop 3手法比較スクリプト ===")
    
    # 出力ディレクトリ作成
    output_dir = Path("autocrop_test_results")
    output_dir.mkdir(exist_ok=True)
    
    # テストケース定義
    test_cases = [
        {
            "name": "Small_Gradient",
            "size": (200, 200),
            "border": 30,
            "content": "gradient"
        },
        {
            "name": "Medium_Pattern", 
            "size": (400, 400),
            "border": 50,
            "content": "pattern"
        },
        {
            "name": "Large_Circle",
            "size": (800, 600),
            "border": 80,
            "content": "circle"
        },
        {
            "name": "XLarge_Gradient",
            "size": (1200, 800),
            "border": 100,
            "content": "gradient"
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. テストケース: {test_case['name']}")
        
        # テスト画像作成
        test_img = create_test_image_with_border(
            test_case["size"], 
            test_case["border"], 
            test_case["content"]
        )
        
        # 画像の平均明度計算
        img_array = np.array(test_img)
        mean_brightness = float(np.mean(cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)))
        
        print(f"   画像サイズ: {test_img.size}")
        print(f"   平均明度: {mean_brightness:.1f}")
        
        # パラメータ生成
        legacy_params = create_legacy_autocrop_params(test_img.size, mean_brightness)
        optimized_params = create_optimized_autocrop_params(test_img.size, mean_brightness)
        
        print(f"   Testing 3 methods:")
        print(f"   - Optimized params: {optimized_params}")
        print(f"   - Legacy params: {legacy_params}")
        print(f"   - Border detection: adaptive")
        
        # 3手法適用
        try:
            three_results = apply_three_autocrop_methods(test_img, optimized_params, legacy_params)
            
            # 比較画像作成
            comparison_img = create_four_method_comparison_image(test_img, three_results, test_case['name'])
            
            # ファイル保存
            output_path = output_dir / f"{test_case['name']}_three_methods_comparison.png"
            comparison_img.save(output_path)
            
            # 結果出力
            opt_info, leg_info, true_leg_info = [result[1] for result in three_results]
            print(f"   Optimized: 検出={opt_info['detected']}, ratio={opt_info['crop_ratio']:.3f}, time={opt_info['processing_time']:.3f}s")
            print(f"   Legacy: 検出={leg_info['detected']}, ratio={leg_info['crop_ratio']:.3f}, time={leg_info['processing_time']:.3f}s")
            print(f"   Border Detection: 検出={true_leg_info['detected']}, ratio={true_leg_info['crop_ratio']:.3f}, time={true_leg_info['processing_time']:.3f}s, borders={true_leg_info['borders_found']}")
            print(f"   比較画像保存: {output_path}")
            
            # 結果記録
            results.append({
                "test_case": test_case['name'],
                "image_size": test_img.size,
                "mean_brightness": mean_brightness,
                "optimized": opt_info,
                "legacy": leg_info,
                "border_detection": true_leg_info
            })
            
        except Exception as e:
            print(f"   エラー: {e}")
            continue
    
    # 実画像テストも3手法対応で実行
    real_results = test_real_images_three_methods(output_dir)
    
    # 結果サマリー（3手法対応）
    print_three_method_summary(results, real_results)


if __name__ == "__main__":
    main()