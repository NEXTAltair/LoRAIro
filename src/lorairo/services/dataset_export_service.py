"""Dataset Export Service for LoRA training compatible formats.

Provides functionality to export database information as training datasets
compatible with kohya-ss/sd-scripts requirements.
"""

import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genai_tag_db_tools import convert_tags
from loguru import logger

from ..database.db_core import resolve_stored_path
from ..database.db_manager import ImageDatabaseManager
from ..database.filter_criteria import ImageFilterCriteria
from ..storage.file_system import FileSystemManager
from .configuration_service import ConfigurationService
from .search_criteria_processor import SearchCriteriaProcessor

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader

# ADR 0068 Phase 3: 学習 export のデフォルト target format
_DEFAULT_EXPORT_TAG_FORMAT = "danbooru"


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
        tag_format: str = _DEFAULT_EXPORT_TAG_FORMAT,
    ) -> Path:
        """Export dataset in TXT format compatible with kohya-ss training.

        Creates separate .txt and .caption files alongside processed images
        in the specified output directory.

        Args:
            image_ids: List of database image IDs to export
            output_path: Directory path for exported dataset
            resolution: Target resolution for processed images (default: 512)
            merge_caption: Whether to merge captions into tag files
            tag_format: Target tag format for canonical resolution (default: "danbooru").
                Tags are resolved to this format's canonical form and ``type=meta``
                tags are excluded (ADR 0068 Phase 3).

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

        reader = self._get_export_reader()
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
                export_tags = self._resolve_export_tags(image_data["tags"])
                export_caption = self._resolve_export_caption(image_data["captions"])
                tags = ", ".join([tag_data["tag"] for tag_data in export_tags])
                tags = self._convert_tags_for_export(tags, tag_format, reader)
                if merge_caption and export_caption:
                    captions = export_caption["caption"]
                    tags = f"{tags}, {captions}" if tags else captions

                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(tags)

                # Write caption file
                if export_caption:
                    captions = export_caption["caption"]
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
        tag_format: str = _DEFAULT_EXPORT_TAG_FORMAT,
    ) -> Path:
        """Export dataset in JSON metadata format compatible with kohya-ss.

        Creates a single JSON file with metadata for all images and copies
        processed images to the output directory.

        Args:
            image_ids: List of database image IDs to export
            output_path: Directory path for exported dataset
            resolution: Target resolution for processed images (default: 512)
            metadata_filename: Name of the JSON metadata file
            tag_format: Target tag format for canonical resolution (default: "danbooru").
                Tags are resolved to this format's canonical form and ``type=meta``
                tags are excluded (ADR 0068 Phase 3).

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

        reader = self._get_export_reader()
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
                export_tags = self._resolve_export_tags(image_data["tags"])
                export_caption = self._resolve_export_caption(image_data["captions"])
                tags = ", ".join([tag_data["tag"] for tag_data in export_tags])
                tags = self._convert_tags_for_export(tags, tag_format, reader)
                captions = export_caption["caption"] if export_caption else ""
                # ADR 0028: score_labels は {model, label} を主とする JSON-safe な形で埋め込む
                score_labels = [
                    {
                        "model": sl.get("model", "Unknown"),
                        "label": sl.get("label", ""),
                        "is_edited_manually": bool(sl.get("is_edited_manually")),
                    }
                    for sl in image_data.get("score_labels", [])
                ]

                metadata[str(output_image_path)] = {
                    "tags": tags,
                    "caption": captions,
                    "score_labels": score_labels,
                    # ADR 0029: 統一品質 tier (derived view)
                    "quality_summary": image_data.get("quality_summary", {}),
                }

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

    def export_with_criteria(
        self,
        output_path: Path,
        format_type: str = "txt",
        resolution: int = 512,
        criteria: ImageFilterCriteria | None = None,
        image_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> Path:
        """フィルタ条件または画像 ID リストからデータセットをエクスポートする統合メソッド。

        criteria と image_ids のどちらか一方を指定すること。
        image_ids は非推奨。将来のバージョンで削除予定。

        Args:
            output_path: 出力ディレクトリパス。
            format_type: エクスポート形式 ("txt" または "json")。
            resolution: 処理済み画像の解像度。
            criteria: DB フィルタ条件。内部で ID 解決を行う。
            image_ids: エクスポート対象の画像 ID リスト（非推奨）。
            **kwargs: export_filtered_dataset に渡す追加パラメータ。

        Returns:
            エクスポート先ディレクトリのパス。

        Raises:
            ValueError: criteria も image_ids も指定されていない場合、または両方同時に指定された場合。
        """
        if criteria is not None and image_ids is not None:
            raise ValueError(
                "criteria と image_ids を同時に指定することはできません。どちらか一方を使用してください。"
            )
        if image_ids is not None:
            warnings.warn(
                "image_ids パラメータは非推奨です。criteria (ImageFilterCriteria) を使用してください。",
                DeprecationWarning,
                stacklevel=2,
            )
            resolved_ids = image_ids
        elif criteria is not None:
            all_images, _ = self.db_manager.get_images_by_filter(criteria)
            resolved_ids = [img["id"] for img in all_images] if all_images else []
        else:
            raise ValueError("criteria または image_ids のどちらかを指定してください")

        return self.export_filtered_dataset(
            image_ids=resolved_ids,
            output_path=output_path,
            format_type=format_type,
            resolution=resolution,
            **kwargs,
        )

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

    def _get_export_reader(self) -> "MergedTagReader | None":
        """外部 tag_db reader を取得する。

        Returns:
            MergedTagReader。外部 tag_db が無い場合は None (変換せず素通し)。
        """
        return self.db_manager.annotation_repo.get_merged_reader()

    def _convert_tags_for_export(self, tags: str, tag_format: str, reader: "MergedTagReader | None") -> str:
        """学習 export 向けにタグを target format の canonical へ解決し meta タグを除外する。

        alias->preferred 解決は format 依存のため export 時に target format で都度解決する
        (ADR 0068 Phase 3)。reader が None (外部 tag_db 不在) の場合は整形済み文字列を
        そのまま返す (graceful degradation)。

        Args:
            tags: カンマ区切りの整形済みタグ文字列。
            tag_format: 変換先フォーマット名 (例: "danbooru")。
            reader: タグ解決に用いる MergedTagReader。None の場合は変換しない。

        Returns:
            canonical 化 + ``type=meta`` 除外済みのタグ文字列。
        """
        if not tags or reader is None:
            return tags
        # genai_tag_db_tools は mypy 上 untyped 扱いのため str へ明示変換する
        return str(convert_tags(reader, tags, tag_format, exclude_types=["meta"]))

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
                # ADR 0028: canonical scorer の categorical label を {model, label} ペアで保持
                "score_labels": annotations.get("score_labels", []),
                # ADR 0029: 統一品質 tier (derived view)
                "quality_summary": annotations.get("quality_summary", {}),
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
        return self.db_manager.get_batch_available_resolutions(image_ids)

    @staticmethod
    def _resolve_export_tags(tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve adopted tags to a stable string union for export.

        `rejected_at` is target-independent correctness state. Export target
        vocabulary conversion belongs to export profiles, not this resolver.
        """
        resolved_by_tag: dict[str, dict[str, Any]] = {}
        for tag_data in tags:
            if tag_data.get("rejected_at") is not None:
                continue
            tag = tag_data.get("tag")
            if not isinstance(tag, str) or not tag:
                continue
            current = resolved_by_tag.get(tag)
            if current is None or (
                bool(tag_data.get("is_edited_manually")) and not bool(current.get("is_edited_manually"))
            ):
                resolved_by_tag[tag] = tag_data
        return list(resolved_by_tag.values())

    @staticmethod
    def _resolve_export_caption(captions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Resolve adopted captions to the single row used by training export."""
        adopted = [
            caption_data
            for caption_data in captions
            if caption_data.get("rejected_at") is None and caption_data.get("caption")
        ]
        if not adopted:
            return None

        def sort_key(indexed_caption: tuple[int, dict[str, Any]]) -> tuple[bool, float, int]:
            index, caption_data = indexed_caption
            timestamp = caption_data.get("updated_at") or caption_data.get("created_at")
            timestamp_value = timestamp.timestamp() if isinstance(timestamp, datetime) else 0.0
            return (bool(caption_data.get("is_edited_manually")), timestamp_value, -index)

        return max(enumerate(adopted), key=sort_key)[1]

    def filter_changed_since(self, image_ids: list[int], since: datetime) -> list[int]:
        """指定日時以降にタグ変更があった image_id に絞り込む (#614)。

        AI 実行 (model_id 付きタグの created_at) または手動編集
        (is_edited_manually のタグの updated_at) が since より後のものを残す。
        元ファイル由来 (existing) は自然に除外される。対象はタグのみ。

        Args:
            image_ids: 絞り込み元の画像IDリスト。
            since: 変更ありとみなす閾値日時。

        Returns:
            since 以降にタグ変更があった image_id の一覧。
        """
        return self.db_manager.filter_image_ids_with_tag_changes_since(image_ids, since)

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
