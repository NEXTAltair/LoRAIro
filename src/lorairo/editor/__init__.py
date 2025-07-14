"""
LoRAIro Editor Module

This module provides image editing and processing functionality for LoRAIro,
including automatic cropping, image processing workflows, and upscaling capabilities.

Classes:
    AutoCrop: Automatic image cropping using complementary color difference algorithm
    ImageProcessingManager: High-level image processing workflow coordination
    ImageProcessor: Core image processing operations (resize, color conversion)
    Upscaler: AI-based image upscaling functionality
"""

from .autocrop import AutoCrop
from .image_processor import ImageProcessingManager, ImageProcessor, Upscaler

__all__ = ["AutoCrop", "ImageProcessingManager", "ImageProcessor", "Upscaler"]
