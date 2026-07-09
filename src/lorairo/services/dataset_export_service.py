"""Dataset Export Service for LoRA training compatible formats.

Provides functionality to export database information as training datasets
compatible with kohya-ss/sd-scripts requirements.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genai_tag_db_tools import convert_tags, get_preferred_translations_batch, search_tags_batch
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from ..database.db_core import resolve_stored_path
from ..database.db_manager import ImageDatabaseManager
from ..database.filter_criteria import ImageFilterCriteria
from ..filesystem import FileSystemManager
from ..utils.language_keys import canonical_language_key, translation_for_language
from .configuration_service import ConfigurationService
from .export_overlay import ExportOverlayPlan, apply_overlay
from .search_criteria_processor import SearchCriteriaProcessor

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader

# ADR 0068 Phase 3: 学習 export のデフォルト target format
_DEFAULT_EXPORT_TAG_FORMAT = "danbooru"
_CANONICAL_TAG_LANGUAGE = "canonical"


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
        overlay_plan: ExportOverlayPlan | None = None,
        tag_languages: list[str] | None = None,
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
            overlay_plan: オーバーレイ適用プラン（ADR 0080）。None の場合は従来挙動を完全維持する。
                画像ごとに effective_for(image_id) で実効 overlay を解決して apply_overlay に渡す。
            tag_languages: 出力するタグ言語。None / ["canonical"] は従来の canonical 出力。
                1 言語なら output_path 直下へ、複数言語なら ``output_path/<language>/`` ごとに
                完全な dataset を出力する (ADR 0088)。

        Returns:
            Path: Path to the exported dataset directory

        Raises:
            RuntimeError: If export process fails
            ValueError: If invalid parameters provided
        """
        if not image_ids:
            raise ValueError("image_ids list cannot be empty")

        language_roots = self._resolve_language_output_roots(output_path, tag_languages)
        for _, language_output_path in language_roots:
            language_output_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Starting TXT format dataset export: {} images, resolution={}, tag_languages={}",
            len(image_ids),
            resolution,
            [language for language, _ in language_roots],
        )

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

                base_filename = processed_image_path.stem

                # タグ文字列構築: overlay 有無で分岐（ADR 0080）
                export_tags = self._resolve_export_tags(image_data["tags"])
                export_caption = self._resolve_export_caption(image_data["captions"])
                tag_list = [tag_data["tag"] for tag_data in export_tags]
                canonical_tags = self._build_export_tag_list(
                    tag_list, image_id, tag_format, reader, overlay_plan
                )
                captions = export_caption["caption"] if export_caption else ""

                for tag_language, language_output_path in language_roots:
                    txt_file = language_output_path / f"{base_filename}.txt"
                    caption_file = language_output_path / f"{base_filename}.caption"
                    output_image_path = language_output_path / processed_image_path.name

                    # Copy processed image
                    self.file_system_manager.copy_file(processed_image_path, output_image_path)

                    tags = ", ".join(self._translate_export_tag_list(canonical_tags, tag_language, reader))
                    if merge_caption and captions:
                        tags = f"{tags}, {captions}" if tags else captions

                    with open(txt_file, "w", encoding="utf-8") as f:
                        f.write(tags)

                    # Write caption file
                    if captions:
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
        overlay_plan: ExportOverlayPlan | None = None,
        tag_languages: list[str] | None = None,
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
            overlay_plan: オーバーレイ適用プラン（ADR 0080）。None の場合は従来挙動を完全維持する。
                画像ごとに effective_for(image_id) で実効 overlay を解決して apply_overlay に渡す。
            tag_languages: 出力するタグ言語。None / ["canonical"] は従来の canonical 出力。
                1 言語なら output_path 直下へ、複数言語なら ``output_path/<language>/`` ごとに
                完全な dataset を出力する (ADR 0088)。

        Returns:
            Path: Path to the exported dataset directory

        Raises:
            RuntimeError: If export process fails
            ValueError: If invalid parameters provided
        """
        if not image_ids:
            raise ValueError("image_ids list cannot be empty")

        language_roots = self._resolve_language_output_roots(output_path, tag_languages)
        for _, language_output_path in language_roots:
            language_output_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Starting JSON format dataset export: {} images, resolution={}, tag_languages={}",
            len(image_ids),
            resolution,
            [language for language, _ in language_roots],
        )

        reader = self._get_export_reader()
        metadata_by_language: dict[str, dict[str, dict[str, Any]]] = {
            language: {} for language, _ in language_roots
        }
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

                # タグ文字列構築: overlay 有無で分岐（ADR 0080）
                export_tags = self._resolve_export_tags(image_data["tags"])
                export_caption = self._resolve_export_caption(image_data["captions"])
                tag_list = [tag_data["tag"] for tag_data in export_tags]
                canonical_tags = self._build_export_tag_list(
                    tag_list, image_id, tag_format, reader, overlay_plan
                )
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

                for tag_language, language_output_path in language_roots:
                    output_image_path = language_output_path / processed_image_path.name
                    self.file_system_manager.copy_file(processed_image_path, output_image_path)
                    metadata_by_language[tag_language][str(output_image_path)] = {
                        "tags": ", ".join(
                            self._translate_export_tag_list(canonical_tags, tag_language, reader)
                        ),
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
        for tag_language, language_output_path in language_roots:
            metadata_path = language_output_path / metadata_filename
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata_by_language[tag_language], f, indent=2, ensure_ascii=False)

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
        **kwargs: Any,
    ) -> Path:
        """フィルタ条件からデータセットをエクスポートする統合メソッド。

        Args:
            output_path: 出力ディレクトリパス。
            format_type: エクスポート形式 ("txt" または "json")。
            resolution: 処理済み画像の解像度。
            criteria: DB フィルタ条件。内部で ID 解決を行う。必須。
                exact-set 選択 (ステージング集合) は
                ``ImageFilterCriteria(image_ids=...)`` として渡す (ADR 0055)。
            **kwargs: export_filtered_dataset に渡す追加パラメータ。

        Returns:
            エクスポート先ディレクトリのパス。

        Raises:
            ValueError: criteria が指定されていない場合。
        """
        if criteria is None:
            raise ValueError("criteria (ImageFilterCriteria) を指定してください")

        all_images, _ = self.db_manager.get_images_by_filter(criteria)
        resolved_ids = [img["id"] for img in all_images] if all_images else []

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

    def _build_export_tags_str(
        self,
        tag_list: list[str],
        image_id: int,
        tag_format: str,
        reader: "MergedTagReader | None",
        overlay_plan: ExportOverlayPlan | None,
    ) -> str:
        """タグリストを overlay または従来変換で文字列化する（ADR 0080）。

        overlay_plan が None の場合はレガシーパス（_convert_tags_for_export）を使用する。
        overlay_plan が指定された場合は apply_overlay に委譲する。
        apply_overlay は add/replace が空のとき dedup をスキップするため、
        空 overlay や exclude-only overlay でもレガシー出力と bit 単位一致が保証される。

        Args:
            tag_list: convert 前のタグリスト。
            image_id: 対象画像の DB ID。
            tag_format: 変換先フォーマット名。
            reader: MergedTagReader。None の場合は変換しない。
            overlay_plan: オーバーレイプラン。None の場合は従来挙動。

        Returns:
            カンマ区切りのタグ文字列。
        """
        return ", ".join(self._build_export_tag_list(tag_list, image_id, tag_format, reader, overlay_plan))

    def _build_export_tag_list(
        self,
        tag_list: list[str],
        image_id: int,
        tag_format: str,
        reader: "MergedTagReader | None",
        overlay_plan: ExportOverlayPlan | None,
    ) -> list[str]:
        """タグリストを overlay または従来変換で list 化する（ADR 0080 / ADR 0088）。"""
        if overlay_plan is not None:
            effective_overlay = overlay_plan.effective_for(image_id)
            # apply_overlay 内で add/replace が空のとき dedup をスキップするため
            # is_noop チェックによる分岐は不要（ADR 0080 §2 改訂）
            return apply_overlay(tag_list, effective_overlay, reader, tag_format)
        converted = self._convert_tags_for_export(", ".join(tag_list), tag_format, reader)
        return [tag.strip() for tag in converted.split(",") if tag.strip()]

    def _translate_export_tag_list(
        self,
        tag_list: list[str],
        tag_language: str,
        reader: "MergedTagReader | None",
    ) -> list[str]:
        """canonical タグリストを指定言語の主訳で置換する（訳なしは fallback）。"""
        if tag_language == _CANONICAL_TAG_LANGUAGE or not tag_list or reader is None:
            return tag_list

        unique_tags = list(dict.fromkeys(tag_list))
        try:
            search_results = search_tags_batch(
                reader, unique_tags, format_names=None, resolve_preferred=False
            )
            tag_ids_by_tag = {
                tag: tag_id
                for tag, result in search_results.items()
                if (tag_id := self._extract_exact_search_tag_id(result.items, tag)) is not None
            }
            preferred = get_preferred_translations_batch(reader, list(tag_ids_by_tag.values()))
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            logger.warning(
                "Tag translation lookup failed; falling back to canonical tags: language={}, error={}",
                tag_language,
                e,
            )
            return tag_list

        translations_by_tag = {
            tag: translation
            for tag, tag_id in tag_ids_by_tag.items()
            if (translation := translation_for_language(preferred.get(tag_id, {}), tag_language))
        }
        return [translations_by_tag.get(tag, tag) for tag in tag_list]

    @staticmethod
    def _extract_exact_search_tag_id(items: list[Any], tag: str) -> int | None:
        """search_tags_batch の結果から tag/source_tag が完全一致する行の tag_id を選ぶ。"""
        normalized_query = tag.casefold()
        tag_ids: list[int] = []
        for item in items:
            tag_id = getattr(item, "tag_id", None)
            if not isinstance(tag_id, int):
                continue
            source_tag = getattr(item, "source_tag", None)
            if item.tag.casefold() == normalized_query or (
                source_tag is not None and source_tag.casefold() == normalized_query
            ):
                tag_ids.append(tag_id)
        if not tag_ids:
            return None
        return max(tag_ids)

    def _resolve_language_output_roots(
        self, output_path: Path, tag_languages: list[str] | None
    ) -> list[tuple[str, Path]]:
        """出力言語と実際の出力 root を解決する（ADR 0088）。"""
        languages = self._normalize_tag_languages(tag_languages)
        if len(languages) == 1:
            return [(languages[0], output_path)]
        return [(language, output_path / language) for language in languages]

    @staticmethod
    def _normalize_tag_languages(tag_languages: list[str] | None) -> list[str]:
        """tag language 指定を正規化・検証する。"""
        if tag_languages is None:
            return [_CANONICAL_TAG_LANGUAGE]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_language in tag_languages:
            language = canonical_language_key(raw_language.strip().lower())
            if not language:
                continue
            if language in {".", ".."} or any(separator in language for separator in ("/", "\\")):
                raise ValueError(f"Invalid tag language path segment: {raw_language!r}")
            if any(not (char.isalnum() or char in {"-", "_"}) for char in language):
                raise ValueError(f"Invalid tag language: {raw_language!r}")
            if language not in seen:
                seen.add(language)
                normalized.append(language)
        return normalized or [_CANONICAL_TAG_LANGUAGE]

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
