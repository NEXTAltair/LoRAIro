"""アノテーション保存サービス。

アノテーション結果をDBに保存するビジネスロジックを提供する。
CLI・GUI・API の3経路で共有する Qt-free サービス。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast  # cast: _extract_scores_from_formatted_outputで使用

from lorairo.database.db_repository import ImageRepository
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from lorairo.database.schema import AnnotationsDict


@dataclass(frozen=True)
class AnnotationSaveResult:
    """アノテーション保存結果。

    Attributes:
        success_count: 保存成功件数。
        skip_count: スキップ件数（phash不一致・アノテーションなし）。
        error_count: 保存エラー件数。
        total_count: 処理対象の総件数。
        error_details: エラー詳細メッセージリスト。
    """

    success_count: int
    skip_count: int
    error_count: int
    total_count: int
    error_details: list[str] = field(default_factory=list)


class AnnotationSaveService:
    """アノテーション結果のDB保存サービス。

    PHashAnnotationResults をDBに保存する。CLI・GUI・API の3経路で共有する。
    Qt依存なし。
    """

    def __init__(self, repository: ImageRepository) -> None:
        """AnnotationSaveService初期化。

        Args:
            repository: ImageRepository インスタンス。
        """
        self._repository = repository

    @staticmethod
    def _extract_field(result: Any, field_name: str) -> Any:
        """UnifiedAnnotationResultからフィールドを取得する。辞書/Pydanticモデル両対応。"""
        if isinstance(result, dict):
            return result.get(field_name)
        return getattr(result, field_name, None)

    @staticmethod
    def _extract_scores_from_formatted_output(formatted_output: Any) -> dict[str, float] | None:
        """formatted_outputからスコア辞書を抽出する。

        Pipeline/CLIPモデルはscoresではなくformatted_outputにスコアを格納するため変換する。
        FIXME: image-annotator-libのUnifiedAnnotationResultスコアフィールド統一後に削除
        """
        if formatted_output is None:
            return None

        if hasattr(formatted_output, "scores") and isinstance(
            getattr(formatted_output, "scores", None), dict
        ):
            return cast("dict[str, float]", formatted_output.scores)

        if isinstance(formatted_output, dict) and "hq" in formatted_output:
            hq_value = formatted_output.get("hq")
            if isinstance(hq_value, (int, float)):
                return {"aesthetic": float(hq_value)}

        if isinstance(formatted_output, (int, float)):
            return {"aesthetic": float(formatted_output)}

        return None

    def _append_model_result(
        self,
        model_id: int,
        scores: dict[str, float] | None,
        tags: list[str] | None,
        captions: list[str] | None,
        ratings: Any,
        result: AnnotationsDict,
    ) -> None:
        """モデルの1件分アノテーション結果をAnnotationsDictに追加する。"""
        if scores:
            for _name, value in scores.items():
                result["scores"].append(
                    {"model_id": model_id, "score": float(value), "is_edited_manually": False}
                )
        if tags:
            for tag in tags:
                result["tags"].append(
                    {
                        "model_id": model_id,
                        "tag": tag,
                        "existing": False,
                        "is_edited_manually": False,
                        "confidence_score": None,
                        "tag_id": None,
                    }
                )
        if captions:
            for caption in captions:
                result["captions"].append(
                    {
                        "model_id": model_id,
                        "caption": caption,
                        "existing": False,
                        "is_edited_manually": False,
                    }
                )
        if ratings:
            result["ratings"].append(
                {
                    "model_id": model_id,
                    "raw_rating_value": str(ratings),
                    "normalized_rating": str(ratings),
                    "confidence_score": None,
                }
            )

    def _process_model_result(
        self,
        model_name: str,
        unified_result: Any,
        models_cache: dict[str, Any],
        result: AnnotationsDict,
    ) -> None:
        """1モデル分のアノテーション結果をAnnotationsDictに追記する。"""
        if self._extract_field(unified_result, "error"):
            logger.warning(f"モデル {model_name} エラーをスキップ")
            return

        model = models_cache.get(model_name)
        if not model:
            logger.warning(f"モデル '{model_name}' がDB未登録")
            return

        scores = self._extract_field(unified_result, "scores")
        if scores is None:
            scores = self._extract_scores_from_formatted_output(
                self._extract_field(unified_result, "formatted_output")
            )

        self._append_model_result(
            model.id,
            scores,
            self._extract_field(unified_result, "tags"),
            self._extract_field(unified_result, "captions"),
            self._extract_field(unified_result, "ratings"),
            result,
        )

    def _build_annotations_dict(
        self,
        phash_annotations: dict[str, Any],
        models_cache: dict[str, Any],
    ) -> AnnotationsDict:
        """1画像分のアノテーション結果をAnnotationsDictに変換する。

        Args:
            phash_annotations: model_name → UnifiedAnnotationResult のマッピング。
            models_cache: model_name → Model の事前取得キャッシュ。

        Returns:
            DB保存用のAnnotationsDict。
        """
        result: AnnotationsDict = {"scores": [], "tags": [], "captions": [], "ratings": []}
        for model_name, unified_result in phash_annotations.items():
            self._process_model_result(model_name, unified_result, models_cache, result)
        return result

    def _collect_names_and_tags(self, results: Any) -> tuple[set[str], set[str]]:
        """全結果からユニークなモデル名とタグ文字列を収集する。

        Args:
            results: PHashAnnotationResults ({phash: {model_name: UnifiedAnnotationResult}})

        Returns:
            (モデル名セット, タグ文字列セット) のタプル。
        """
        all_model_names: set[str] = set()
        all_raw_tags: set[str] = set()
        for phash_annotations in results.values():
            for model_name, unified_result in phash_annotations.items():
                if self._extract_field(unified_result, "error"):
                    continue
                all_model_names.add(model_name)
                tags = self._extract_field(unified_result, "tags")
                if tags:
                    all_raw_tags.update(tags)
        return all_model_names, all_raw_tags

    def _resolve_tag_ids(self, all_raw_tags: set[str]) -> dict[str, int | None]:
        """タグ文字列を正規化してtag_IDを一括解決する。

        Args:
            all_raw_tags: 生のタグ文字列セット。

        Returns:
            正規化済みタグ文字列 → tag_id のキャッシュ辞書。
        """
        from genai_tag_db_tools.utils.cleanup_str import TagCleaner

        if not all_raw_tags:
            return {}

        normalized_tags: set[str] = set()
        for raw_tag in all_raw_tags:
            normalized = TagCleaner.clean_format(raw_tag).strip()
            if normalized:
                normalized_tags.add(normalized)

        if not normalized_tags:
            return {}

        return self._repository.batch_resolve_tag_ids(normalized_tags)

    def _save_single(
        self,
        phash: str,
        phash_annotations: dict[str, Any],
        phash_to_image_id: dict[str, int],
        models_cache: dict[str, Any],
        tag_id_cache: dict[str, int | None],
    ) -> bool:
        """単一phashのアノテーション結果をDBに保存する。

        Args:
            phash: 対象画像のpHash。
            phash_annotations: model_name → UnifiedAnnotationResult のマッピング。
            phash_to_image_id: pHash → image_id のマッピング。
            models_cache: model_name → Model のキャッシュ。
            tag_id_cache: 正規化タグ → tag_id のキャッシュ。

        Returns:
            保存成功した場合True、スキップした場合False。
        """
        image_id = phash_to_image_id.get(phash)
        if image_id is None:
            logger.warning(f"pHash {phash[:8]}... に対応する画像がDBに見つかりません。スキップします。")
            return False

        annotations_dict = self._build_annotations_dict(phash_annotations, models_cache)

        if not annotations_dict or not any(annotations_dict.values()):
            logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
            return False

        self._repository.save_annotations(
            image_id,
            annotations_dict,
            skip_existence_check=True,
            tag_id_cache=tag_id_cache if tag_id_cache else None,
        )
        logger.debug(f"画像ID {image_id} のアノテーション保存成功")
        return True

    def save_annotation_results(self, results: Any) -> AnnotationSaveResult:
        """アノテーション結果をDBに保存する。

        phash → image_id のマッピングはリポジトリから一括取得する。
        エラー発生時は error_count に集計して処理を継続する。

        Args:
            results: PHashAnnotationResults ({phash: {model_name: UnifiedAnnotationResult}})

        Returns:
            AnnotationSaveResult: 保存結果（成功数・スキップ数・エラー数）
        """
        if not results:
            return AnnotationSaveResult(
                success_count=0,
                skip_count=0,
                error_count=0,
                total_count=0,
            )

        phash_to_image_id = self._repository.find_image_ids_by_phashes(set(results.keys()))

        all_model_names, all_raw_tags = self._collect_names_and_tags(results)
        models_cache = self._repository.get_models_by_names(all_model_names)
        tag_id_cache = self._resolve_tag_ids(all_raw_tags)

        success_count = 0
        skip_count = 0
        error_count = 0
        error_details: list[str] = []

        for phash, phash_annotations in results.items():
            try:
                if self._save_single(
                    phash, phash_annotations, phash_to_image_id, models_cache, tag_id_cache
                ):
                    success_count += 1
                else:
                    skip_count += 1
            except Exception as e:
                error_msg = f"phash={phash[:8]}...: {e}"
                error_details.append(error_msg)
                error_count += 1
                logger.error(f"保存失敗 phash={phash[:8]}...: {e}", exc_info=True)

        total_count = len(results)
        logger.info(f"DB保存完了: {success_count}/{total_count}件成功")

        return AnnotationSaveResult(
            success_count=success_count,
            skip_count=skip_count,
            error_count=error_count,
            total_count=total_count,
            error_details=error_details,
        )
