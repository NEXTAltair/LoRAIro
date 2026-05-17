"""アノテーション保存サービス。

アノテーション結果をDBに保存するビジネスロジックを提供する。
CLI・GUI・API の3経路で共有する Qt-free サービス。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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

    def _append_model_result(
        self,
        model_id: int,
        scores: dict[str, float] | None,
        score_labels: list[str] | None,
        tags: list[str] | None,
        captions: list[str] | None,
        ratings: Any,
        result: AnnotationsDict,
    ) -> None:
        """モデルの1件分アノテーション結果をAnnotationsDictに追加する。

        ADR 0027 / iam-lib ADR 0002: ``score_labels`` は canonical scorer の
        categorical label (例: "very aesthetic", "aesthetic")。``tags`` フィールドとは
        独立に保持する (content tag との混入を避ける)。
        """
        if scores:
            for _name, value in scores.items():
                result["scores"].append(
                    {"model_id": model_id, "score": float(value), "is_edited_manually": False}
                )
        if score_labels:
            for label in score_labels:
                result["score_labels"].append(
                    {"model_id": model_id, "label": label, "is_edited_manually": False}
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

    # ADR 0023 Phase 1.5 (Issue #42): image-annotator-lib 側で refusal を検出した
    # 場合、UnifiedAnnotationResult.error は f"{type(refusal_exc).__name__}: {msg}"
    # 形式の文字列で乗ってくる。LoRAIro 側はこの prefix を string match で decode
    # して error_records に記録する (型 import せず文字列 prefix のみで疎結合に保つ)。
    _REFUSAL_ERROR_PREFIXES: tuple[str, ...] = (
        "SafetyRefusalError:",
        "ContentPolicyRefusalError:",
    )

    @classmethod
    def _detect_refusal_error_type(cls, error: Any) -> str | None:
        """`UnifiedAnnotationResult.error` から refusal exception type 名を抽出する。

        ADR 0023 Phase 1.5: image-annotator-lib 側 `_classify_refusal()` が
        `f"{type(refusal_exc).__name__}: {refusal_exc}"` 形式で error 文字列を
        構築するため、prefix を startswith で判定して error_type を切り出す。

        Args:
            error: `UnifiedAnnotationResult.error` の値 (str | None | 他)。

        Returns:
            "SafetyRefusalError" / "ContentPolicyRefusalError"、または非 refusal なら None。
        """
        if not isinstance(error, str):
            return None
        for prefix in cls._REFUSAL_ERROR_PREFIXES:
            if error.startswith(prefix):
                # prefix は ":" を含むため strip して error_type 名のみ返す
                return prefix.rstrip(":")
        return None

    def _process_model_result(
        self,
        model_name: str,
        unified_result: Any,
        models_cache: dict[str, Any],
        result: AnnotationsDict,
        image_id: int | None = None,
    ) -> None:
        """1モデル分のアノテーション結果をAnnotationsDictに追記する。

        ADR 0023 Phase 1.5 (Issue #42): error が SafetyRefusalError /
        ContentPolicyRefusalError の prefix を持つ場合、`error_records` に記録
        してから skip する。`image_id is None` の場合は記録できないため warning
        のみ出して skip する。

        Args:
            model_name: アノテーションを行ったモデル名。
            unified_result: image-annotator-lib から返された UnifiedAnnotationResult。
            models_cache: model_name → Model の事前取得キャッシュ。
            result: 追記先の AnnotationsDict。
            image_id: 対象画像 ID。refusal を error_records に記録する際に必要。
        """
        error = self._extract_field(unified_result, "error")
        if error:
            refusal_type = self._detect_refusal_error_type(error)
            if refusal_type is not None:
                # ADR 0023 line 347-372: refusal は retry せず error_records に
                # 記録 → 送信前 filter で除外。
                error_message = error.split(":", 1)[1].strip() if ":" in error else ""
                if image_id is not None:
                    self._repository.save_error_record(
                        operation_type="annotation",
                        error_type=refusal_type,
                        error_message=error_message,
                        image_id=image_id,
                        model_name=model_name,
                    )
                    logger.warning(
                        f"Refusal recorded to error_records: model={model_name}, "
                        f"image_id={image_id}, type={refusal_type}"
                    )
                else:
                    logger.warning(
                        f"Refusal detected but image_id missing, cannot persist: "
                        f"model={model_name}, type={refusal_type}"
                    )
                return
            logger.warning(f"モデル {model_name} エラーをスキップ")
            return

        model = models_cache.get(model_name)
        if not model:
            logger.warning(f"モデル '{model_name}' がDB未登録")
            return

        self._append_model_result(
            model.id,
            self._extract_field(unified_result, "scores"),
            self._extract_field(unified_result, "score_labels"),
            self._extract_field(unified_result, "tags"),
            self._extract_field(unified_result, "captions"),
            self._extract_field(unified_result, "ratings"),
            result,
        )

    def _build_annotations_dict(
        self,
        phash_annotations: dict[str, Any],
        models_cache: dict[str, Any],
        image_id: int | None = None,
    ) -> AnnotationsDict:
        """1画像分のアノテーション結果をAnnotationsDictに変換する。

        Args:
            phash_annotations: model_name → UnifiedAnnotationResult のマッピング。
            models_cache: model_name → Model の事前取得キャッシュ。
            image_id: 対象画像 ID。refusal を error_records に記録する際に必要。

        Returns:
            DB保存用のAnnotationsDict。
        """
        result: AnnotationsDict = {
            "scores": [],
            "score_labels": [],
            "tags": [],
            "captions": [],
            "ratings": [],
        }
        for model_name, unified_result in phash_annotations.items():
            self._process_model_result(model_name, unified_result, models_cache, result, image_id=image_id)
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

        annotations_dict = self._build_annotations_dict(phash_annotations, models_cache, image_id=image_id)

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
        # ADR 0023 Phase 1.11 (Issue #238): registry key (= AnnotatorInfo.name) を
        # litellm_model_id SSoT に直接マップする。Phase 1.10 後は registry key と
        # litellm_model_id が一致するため (WebAPI 完全 ID / ローカル ML bare name)。
        models_cache = self._repository.get_models_by_litellm_ids(all_model_names)
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

    # ADR 0023 Phase 1.5 (Issue #42): WebAPI annotation 対象から、過去に refusal
    # を返した画像を除外するための送信前 filter。AnnotationWorker 等の caller が
    # image_paths を構築した直後に呼ぶことで、無駄な API 課金 + refusal ループを防ぐ。
    REFUSAL_ERROR_TYPES: tuple[str, ...] = (
        "SafetyRefusalError",
        "ContentPolicyRefusalError",
    )

    def filter_refused_image_paths(self, image_paths: list[str]) -> list[str]:
        """過去に safety/content refusal を返した画像 path を除外する。

        **本 method は WebAPI 推論経路向けの filter** — SafetyRefusal /
        ContentPolicyRefusal は cloud provider の content policy 拒否概念で、
        ローカル ML モデル (WD-Tagger 等) はこの種の refusal を返さない。
        したがって caller はローカルモデル単独実行時に本 filter を呼ばないこと。
        WebAPI モデルが選択モデルに含まれているかの判定は呼び出し側 (`worker_service`)
        で行う (`selection_includes_webapi_model()` 参照)。

        ADR 0023 line 363-369 の送信前 filter:
            operation_type = "annotation"
            error_type in {"SafetyRefusalError", "ContentPolicyRefusalError"}
            resolved_at IS NULL

        を満たす image_id 集合を取得し、対応する image_path を除外する。
        path → image_id の解決には `_repository.get_image_id_by_filepath()` を使う。
        DB に未登録の画像 path は filter 対象外として通過させる (新規画像扱い)。

        Args:
            image_paths: アノテーション対象候補の画像 path リスト。

        Returns:
            refusal 履歴を持たない image_path のサブリスト (順序維持)。
        """
        if not image_paths:
            return []

        refused_image_ids = set(
            self._repository.get_error_image_ids(
                operation_type="annotation",
                resolved=False,
                error_types=list(self.REFUSAL_ERROR_TYPES),
            )
        )
        if not refused_image_ids:
            return list(image_paths)

        # ADR 0023 Phase 1.5 (Codex P2 r3209342204): N+1 回避のため、path → image_id
        # は 1 クエリでバッチ解決する。`get_image_ids_by_filepaths()` は filename IN
        # 句 + Python 側 resolve 比較で大量パスを sub-second で処理する。
        path_to_image_id = self._repository.get_image_ids_by_filepaths(image_paths)

        filtered: list[str] = []
        excluded_count = 0
        for path in image_paths:
            image_id = path_to_image_id.get(path)
            if image_id is not None and image_id in refused_image_ids:
                excluded_count += 1
                continue
            filtered.append(path)

        if excluded_count > 0:
            logger.info(
                f"WebAPI annotation 送信前 filter: 対象 {len(filtered)}件 "
                f"(refusal 除外: {excluded_count}件)"
            )
        return filtered
