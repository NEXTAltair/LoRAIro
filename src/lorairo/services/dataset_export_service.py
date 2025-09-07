"""Dataset Export Service for LoRA training compatible formats.

Provides functionality to export database information as training datasets
compatible with kohya-ss/sd-scripts requirements.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ..database.db_core import resolve_stored_path
from ..database.db_manager import ImageDatabaseManager
from ..storage.file_system import FileSystemManager
from .configuration_service import ConfigurationService
from .search_criteria_processor import SearchCriteriaProcessor


class DatasetExportService:
    """Service for exporting training datasets compatible with kohya-ss/sd-scripts.

    Handles the conversion of database information into LoRA training formats:
    - TXT format: Tags and captions as separate text files
    - JSON format: Metadata format for kohya-ss compatibility

    Uses processed images at specified resolutions instead of original images.
    """

    def __init__(
        self,
        config_service: ConfigurationService,
        file_system_manager: FileSystemManager,
        db_manager: ImageDatabaseManager,
        search_processor: SearchCriteriaProcessor,
    ) -> None:
        """Initialize DatasetExportService.

        Args:
            config_service: Configuration service for export settings
            file_system_manager: File system operations manager
            db_manager: Database manager for image data access
            search_processor: Search and filtering processor
        """
        self.config_service = config_service
        self.file_system_manager = file_system_manager
        self.db_manager = db_manager
        self.search_processor = search_processor
        logger.debug("DatasetExportService initialized")

    def export_dataset_txt_format(
        self,
        image_ids: list[int],
        output_path: Path,
        resolution: int = 512,
        merge_caption: bool = False,
    ) -> Path:
        """Export dataset in TXT format compatible with kohya-ss training.

        Creates separate .txt and .caption files alongside processed images
        in the specified output directory.

        Args:
            image_ids: List of database image IDs to export
            output_path: Directory path for exported dataset
            resolution: Target resolution for processed images (default: 512)
            merge_caption: Whether to merge captions into tag files

        Returns:
            Path: Path to the exported dataset directory

        Raises:
            RuntimeError: If export process fails
            ValueError: If invalid parameters provided
        """
        if not image_ids:
            raise ValueError("image_ids list cannot be empty")

        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting TXT format dataset export: {len(image_ids)} images, resolution={resolution}")

        exported_count = 0
        for image_id in image_ids:
            try:
                # Get processed image path for specified resolution
                processed_image_path = self._resolve_processed_image_path(image_id, resolution)
                if not processed_image_path:
                    logger.warning(
                        f"Processed image not found for ID {image_id} at resolution {resolution}"
                    )
                    continue

                # Get image metadata and annotations
                image_data = self._get_image_export_data(image_id)
                if not image_data:
                    logger.warning(f"No export data found for image ID {image_id}")
                    continue

                # Generate output filenames
                base_filename = processed_image_path.stem
                txt_file = output_path / f"{base_filename}.txt"
                caption_file = output_path / f"{base_filename}.caption"
                output_image_path = output_path / processed_image_path.name

                # Copy processed image
                self.file_system_manager.copy_file(processed_image_path, output_image_path)

                # Write tag file
                tags = ", ".join([tag_data["tag"] for tag_data in image_data["tags"]])
                if merge_caption and image_data["captions"]:
                    captions = ", ".join(
                        [caption_data["caption"] for caption_data in image_data["captions"]]
                    )
                    tags = f"{tags}, {captions}" if tags else captions

                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(tags)

                # Write caption file
                if image_data["captions"]:
                    captions = ", ".join(
                        [caption_data["caption"] for caption_data in image_data["captions"]]
                    )
                    with open(caption_file, "w", encoding="utf-8") as f:
                        f.write(captions)

                exported_count += 1
                logger.debug(f"Exported image {image_id}: {base_filename}")

            except Exception as e:
                logger.error(f"Failed to export image ID {image_id}: {e}")
                continue

        logger.info(f"TXT format export completed: {exported_count}/{len(image_ids)} images exported")
        return output_path

    def export_dataset_json_format(
        self,
        image_ids: list[int],
        output_path: Path,
        resolution: int = 512,
        metadata_filename: str = "metadata.json",
    ) -> Path:
        """Export dataset in JSON metadata format compatible with kohya-ss.

        Creates a single JSON file with metadata for all images and copies
        processed images to the output directory.

        Args:
            image_ids: List of database image IDs to export
            output_path: Directory path for exported dataset
            resolution: Target resolution for processed images (default: 512)
            metadata_filename: Name of the JSON metadata file

        Returns:
            Path: Path to the exported dataset directory

        Raises:
            RuntimeError: If export process fails
            ValueError: If invalid parameters provided
        """
        if not image_ids:
            raise ValueError("image_ids list cannot be empty")

        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Starting JSON format dataset export: {len(image_ids)} images, resolution={resolution}"
        )

        metadata = {}
        exported_count = 0

        for image_id in image_ids:
            try:
                # Get processed image path for specified resolution
                processed_image_path = self._resolve_processed_image_path(image_id, resolution)
                if not processed_image_path:
                    logger.warning(
                        f"Processed image not found for ID {image_id} at resolution {resolution}"
                    )
                    continue

                # Get image metadata and annotations
                image_data = self._get_image_export_data(image_id)
                if not image_data:
                    logger.warning(f"No export data found for image ID {image_id}")
                    continue

                # Copy processed image
                output_image_path = output_path / processed_image_path.name
                self.file_system_manager.copy_file(processed_image_path, output_image_path)

                # Build metadata entry
                tags = ", ".join([tag_data["tag"] for tag_data in image_data["tags"]])
                captions = (
                    ", ".join([caption_data["caption"] for caption_data in image_data["captions"]])
                    if image_data["captions"]
                    else ""
                )

                metadata[str(output_image_path)] = {"tags": tags, "caption": captions}

                exported_count += 1
                logger.debug(f"Exported image {image_id}: {processed_image_path.name}")

            except Exception as e:
                logger.error(f"Failed to export image ID {image_id}: {e}")
                continue

        # Write metadata JSON file (proper JSON format, not append mode)
        metadata_path = output_path / metadata_filename
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON format export completed: {exported_count}/{len(image_ids)} images exported")
        return output_path

    def export_filtered_dataset(
        self,
        image_ids: list[int],
        output_path: Path,
        format_type: str = "txt",
        resolution: int = 512,
        **kwargs: Any,
    ) -> Path:
        """Export dataset based on provided image IDs.

        Note: This method now expects pre-filtered image IDs rather than search filters.
        Use SearchCriteriaProcessor separately to get filtered image IDs if needed.

        Args:
            image_ids: List of database image IDs to export
            output_path: Directory path for exported dataset
            format_type: Export format ("txt" or "json")
            resolution: Target resolution for processed images
            **kwargs: Additional export parameters

        Returns:
            Path: Path to the exported dataset directory

        Raises:
            ValueError: If invalid format_type or parameters
        """
        if not image_ids:
            logger.warning("No images provided for export")
            return output_path

        logger.info(f"Exporting filtered dataset: {len(image_ids)} images found")

        if format_type.lower() == "txt":
            return self.export_dataset_txt_format(image_ids, output_path, resolution, **kwargs)
        elif format_type.lower() == "json":
            return self.export_dataset_json_format(image_ids, output_path, resolution, **kwargs)
        else:
            raise ValueError(f"Unsupported format_type: {format_type}. Use 'txt' or 'json'")

    def _resolve_processed_image_path(self, image_id: int, resolution: int) -> Path | None:
        """Resolve the file system path for a processed image at specified resolution.

        Args:
            image_id: Database image ID
            resolution: Target resolution (e.g., 512, 768, 1024)

        Returns:
            Path to processed image file, None if not found
        """
        try:
            # Check if processed image exists at specified resolution
            processed_metadata = self.db_manager.check_processed_image_exists(image_id, resolution)
            if not processed_metadata:
                logger.debug(f"No processed image found for ID {image_id} at resolution {resolution}")
                return None

            # Resolve the stored path to actual file system path
            stored_path = processed_metadata.get("stored_image_path")
            if not stored_path:
                logger.warning(f"No stored_image_path in metadata for image ID {image_id}")
                return None

            resolved_path = resolve_stored_path(stored_path)
            if not resolved_path.exists():
                logger.warning(f"Processed image file does not exist: {resolved_path}")
                return None

            return resolved_path

        except Exception as e:
            logger.error(f"Error resolving processed image path for ID {image_id}: {e}")
            return None

    def _get_image_export_data(self, image_id: int) -> dict[str, Any] | None:
        """Get image data required for export (tags, captions, metadata).

        Args:
            image_id: Database image ID

        Returns:
            Dictionary with image export data, None if not found
        """
        try:
            # Get image metadata
            metadata = self.db_manager.get_image_metadata(image_id)
            if not metadata:
                return None

            # Get annotations (tags, captions, scores, ratings)
            annotations = self.db_manager.get_image_annotations(image_id)

            return {
                "metadata": metadata,
                "tags": annotations.get("tags", []),
                "captions": annotations.get("captions", []),
            }

        except Exception as e:
            logger.error(f"Error getting export data for image ID {image_id}: {e}")
            return None

    def get_available_resolutions(self, image_ids: list[int]) -> dict[int, list[int]]:
        """Get available processed resolutions for given image IDs.

        Args:
            image_ids: List of database image IDs

        Returns:
            Dictionary mapping image_id -> list of available resolutions
        """
        resolution_map = {}

        for image_id in image_ids:
            try:
                # Check common resolutions
                available_resolutions = []
                for resolution in [512, 768, 1024, 1536]:
                    if self.db_manager.check_processed_image_exists(image_id, resolution):
                        available_resolutions.append(resolution)

                resolution_map[image_id] = available_resolutions

            except Exception as e:
                logger.error(f"Error checking resolutions for image ID {image_id}: {e}")
                resolution_map[image_id] = []

        return resolution_map

    def validate_export_requirements(self, image_ids: list[int], resolution: int) -> dict[str, Any]:
        """Validate that export requirements can be met.

        Args:
            image_ids: List of database image IDs to validate
            resolution: Required resolution

        Returns:
            Validation report with statistics and issues
        """
        report: dict[str, Any] = {
            "total_images": len(image_ids),
            "valid_images": 0,
            "missing_processed": 0,
            "missing_metadata": 0,
            "issues": [],
        }

        for image_id in image_ids:
            try:
                # Check processed image
                if not self._resolve_processed_image_path(image_id, resolution):
                    report["missing_processed"] = report["missing_processed"] + 1
                    issues_list = report["issues"]
                    if isinstance(issues_list, list):
                        issues_list.append(f"Missing processed image for ID {image_id} at {resolution}px")
                    continue

                # Check export data
                if not self._get_image_export_data(image_id):
                    report["missing_metadata"] = report["missing_metadata"] + 1
                    issues_list = report["issues"]
                    if isinstance(issues_list, list):
                        issues_list.append(f"Missing metadata for ID {image_id}")
                    continue

                report["valid_images"] = report["valid_images"] + 1

            except Exception as e:
                issues_list = report["issues"]
                if isinstance(issues_list, list):
                    issues_list.append(f"Error validating image ID {image_id}: {e}")

        return report
