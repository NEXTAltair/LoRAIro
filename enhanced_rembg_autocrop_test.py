"""Enhanced rembg AutoCrop implementation with optimized parameters"""

import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import numpy as np
from PIL import Image
from rembg import remove, new_session
from loguru import logger

class EnhancedRembgAutoCrop:
    """Enhanced rembg-based AutoCrop with parameter optimization"""
    
    def __init__(self):
        self.model_cache = {}
        self.parameter_presets = {
            "high_quality": {
                "model": "birefnet-general",
                "alpha_matting": True,
                "alpha_matting_foreground_threshold": 270,
                "alpha_matting_background_threshold": 15,
                "alpha_matting_erode_size": 8,
                "post_process_mask": True
            },
            "balanced": {
                "model": "u2net",
                "alpha_matting": True,
                "alpha_matting_foreground_threshold": 250,
                "alpha_matting_background_threshold": 20,
                "alpha_matting_erode_size": 10,
                "post_process_mask": True
            },
            "fast": {
                "model": "u2netp",
                "alpha_matting": False,
                "post_process_mask": True
            },
            "anime": {
                "model": "isnet-anime",
                "alpha_matting": True,
                "alpha_matting_foreground_threshold": 280,
                "alpha_matting_background_threshold": 10,
                "alpha_matting_erode_size": 6,
                "post_process_mask": True
            }
        }
    
    def get_session(self, model_name: str):
        """Get cached model session"""
        if model_name not in self.model_cache:
            try:
                self.model_cache[model_name] = new_session(model_name)
                logger.info(f"Loaded model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                return None
        return self.model_cache[model_name]
    
    def crop_from_alpha_channel(self, original_image: Image.Image, alpha_image: Image.Image) -> Tuple[Image.Image, Dict[str, Any]]:
        """Extract crop box from alpha channel and apply to original image"""
        if alpha_image.mode != 'RGBA':
            logger.warning("Alpha image is not RGBA mode")
            return original_image, {"error": "No alpha channel"}
        
        # Get alpha channel
        alpha = alpha_image.split()[-1]
        alpha_array = np.array(alpha)
        
        # Find non-transparent pixels
        non_transparent = alpha_array > 10  # Small threshold to handle anti-aliasing
        
        if not non_transparent.any():
            logger.warning("No non-transparent pixels found")
            return original_image, {"error": "Empty mask"}
        
        # Get bounding box
        rows = np.any(non_transparent, axis=1)
        cols = np.any(non_transparent, axis=0)
        
        if not rows.any() or not cols.any():
            return original_image, {"error": "No valid crop area"}
        
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        
        # Add small padding
        padding = 2
        x_min = max(0, x_min - padding)
        y_min = max(0, y_min - padding)
        x_max = min(original_image.width, x_max + padding)
        y_max = min(original_image.height, y_max + padding)
        
        # Crop original image
        crop_box = (x_min, y_min, x_max, y_max)
        cropped = original_image.crop(crop_box)
        
        crop_info = {
            "method": "enhanced_rembg",
            "crop_box": crop_box,
            "original_size": original_image.size,
            "cropped_size": cropped.size,
            "crop_ratio": (cropped.width * cropped.height) / (original_image.width * original_image.height)
        }
        
        return cropped, crop_info
    
    def crop_with_preset(self, image: Image.Image, preset: str = "balanced") -> Tuple[Image.Image, Dict[str, Any]]:
        """Crop image using parameter preset"""
        if preset not in self.parameter_presets:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(self.parameter_presets.keys())}")
        
        params = self.parameter_presets[preset].copy()
        model_name = params.pop("model")
        
        return self.crop_with_model(image, model_name, **params)
    
    def crop_with_model(self, image: Image.Image, model_name: str, **kwargs) -> Tuple[Image.Image, Dict[str, Any]]:
        """Crop image with specific model and parameters"""
        start_time = time.time()
        
        try:
            session = self.get_session(model_name)
            if session is None:
                return image, {"error": f"Failed to load model: {model_name}"}
            
            # Remove background
            result = remove(image, session=session, **kwargs)
            
            # Extract crop from result
            cropped, crop_info = self.crop_from_alpha_channel(image, result)
            crop_info["model"] = model_name
            crop_info["parameters"] = kwargs
            crop_info["processing_time"] = time.time() - start_time
            
            return cropped, crop_info
            
        except Exception as e:
            logger.error(f"Error processing with model {model_name}: {e}")
            return image, {"error": str(e), "model": model_name}
    
    def crop_with_fallback(self, image: Image.Image, model_priority: list = None) -> Tuple[Image.Image, Dict[str, Any]]:
        """Crop with model fallback strategy"""
        if model_priority is None:
            model_priority = ["birefnet-general", "u2net", "u2netp"]
        
        for model in model_priority:
            try:
                preset = "balanced" if model == "u2net" else "high_quality" if "birefnet" in model else "fast"
                result, info = self.crop_with_preset(image, preset)
                
                if "error" not in info:
                    info["fallback_model"] = model
                    return result, info
                    
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                continue
        
        return image, {"error": "All models failed"}


def test_enhanced_rembg_autocrop():
    """Test enhanced rembg AutoCrop with different parameter combinations"""
    
    # Setup
    test_images_dir = Path("/workspaces/LoRAIro/test_images")
    results_dir = Path("/workspaces/LoRAIro/enhanced_rembg_results")
    results_dir.mkdir(exist_ok=True)
    
    autocrop = EnhancedRembgAutoCrop()
    
    if not test_images_dir.exists():
        print(f"Test images directory not found: {test_images_dir}")
        return
    
    # Test images
    image_files = list(test_images_dir.glob("*.jpg")) + list(test_images_dir.glob("*.png"))
    if not image_files:
        print("No test images found")
        return
    
    presets_to_test = ["high_quality", "balanced", "fast", "anime"]
    
    for img_path in image_files[:3]:  # Test first 3 images
        print(f"\nTesting image: {img_path.name}")
        
        try:
            original = Image.open(img_path).convert("RGB")
            print(f"Original size: {original.size}")
            
            # Test each preset
            results = {}
            for preset in presets_to_test:
                print(f"  Testing preset: {preset}")
                
                try:
                    cropped, info = autocrop.crop_with_preset(original, preset)
                    results[preset] = {
                        "image": cropped,
                        "info": info
                    }
                    
                    if "error" not in info:
                        print(f"    Success: {info['cropped_size']}, ratio: {info['crop_ratio']:.3f}, time: {info['processing_time']:.2f}s")
                    else:
                        print(f"    Error: {info['error']}")
                        
                except Exception as e:
                    print(f"    Exception: {e}")
                    results[preset] = {"error": str(e)}
            
            # Create comparison image
            create_enhanced_comparison(original, results, img_path.stem, results_dir)
            
        except Exception as e:
            print(f"Error processing {img_path.name}: {e}")


def create_enhanced_comparison(original: Image.Image, results: Dict, image_name: str, output_dir: Path):
    """Create comparison image with all preset results"""
    
    successful_results = {k: v for k, v in results.items() if "image" in v and "error" not in v["info"]}
    
    if not successful_results:
        print(f"  No successful results for {image_name}")
        return
    
    # Calculate dimensions
    max_width = 300
    original_aspect = original.height / original.width
    display_height = int(max_width * original_aspect)
    
    # Resize original
    original_resized = original.resize((max_width, display_height), Image.Resampling.LANCZOS)
    
    # Create layout
    cols = len(successful_results) + 1  # +1 for original
    total_width = cols * max_width
    total_height = display_height + 100  # +100 for text
    
    comparison = Image.new("RGB", (total_width, total_height), "white")
    
    # Place original
    comparison.paste(original_resized, (0, 80))
    
    # Place results
    x_offset = max_width
    for preset, result_data in successful_results.items():
        cropped = result_data["image"]
        info = result_data["info"]
        
        # Resize maintaining aspect ratio
        crop_aspect = cropped.height / cropped.width
        if crop_aspect > original_aspect:
            # Taller than original aspect, fit by height
            display_width = int(display_height / crop_aspect)
            display_width = min(display_width, max_width)
            cropped_resized = cropped.resize((display_width, int(display_width * crop_aspect)), Image.Resampling.LANCZOS)
        else:
            # Wider than original aspect, fit by width
            cropped_resized = cropped.resize((max_width, int(max_width * crop_aspect)), Image.Resampling.LANCZOS)
        
        # Center in column
        paste_x = x_offset + (max_width - cropped_resized.width) // 2
        paste_y = 80 + (display_height - cropped_resized.height) // 2
        
        comparison.paste(cropped_resized, (paste_x, paste_y))
        x_offset += max_width
    
    # Add labels (would need PIL drawing for text)
    output_path = output_dir / f"{image_name}_enhanced_comparison.png"
    comparison.save(output_path)
    print(f"  Saved comparison: {output_path}")


def benchmark_parameter_combinations():
    """Benchmark different parameter combinations"""
    
    test_image_path = Path("/workspaces/LoRAIro/test_images")
    if not test_image_path.exists():
        print("No test images found for benchmarking")
        return
    
    # Get first test image
    image_files = list(test_image_path.glob("*.jpg")) + list(test_image_path.glob("*.png"))
    if not image_files:
        print("No test images found")
        return
    
    test_image = Image.open(image_files[0]).convert("RGB")
    autocrop = EnhancedRembgAutoCrop()
    
    # Parameter combinations to test
    parameter_matrix = [
        # Model variations
        {"model": "u2net", "alpha_matting": False},
        {"model": "u2net", "alpha_matting": True, "alpha_matting_foreground_threshold": 240},
        {"model": "u2net", "alpha_matting": True, "alpha_matting_foreground_threshold": 270},
        {"model": "u2netp", "alpha_matting": False},
        {"model": "u2netp", "post_process_mask": True},
        
        # BiRefNet if available
        {"model": "birefnet-general", "alpha_matting": False},
        {"model": "birefnet-general", "alpha_matting": True, "alpha_matting_foreground_threshold": 270},
    ]
    
    print(f"\nBenchmarking with image: {image_files[0].name}")
    print(f"Original size: {test_image.size}")
    
    for i, params in enumerate(parameter_matrix):
        model = params["model"]
        print(f"\nTest {i+1}: {params}")
        
        try:
            start_time = time.time()
            cropped, info = autocrop.crop_with_model(test_image, **params)
            total_time = time.time() - start_time
            
            if "error" not in info:
                print(f"  Success: {info['cropped_size']}")
                print(f"  Crop ratio: {info['crop_ratio']:.3f}")
                print(f"  Processing time: {total_time:.2f}s")
            else:
                print(f"  Error: {info['error']}")
                
        except Exception as e:
            print(f"  Exception: {e}")


if __name__ == "__main__":
    print("Enhanced rembg AutoCrop Testing")
    print("=" * 40)
    
    # Test enhanced implementation
    test_enhanced_rembg_autocrop()
    
    # Benchmark parameters
    print("\n" + "=" * 40)
    print("Parameter Benchmarking")
    benchmark_parameter_combinations()