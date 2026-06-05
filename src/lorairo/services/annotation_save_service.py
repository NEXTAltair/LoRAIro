"""アノテーション保存サービス。

アノテーション結果をDBに保存するビジネスロジックを提供する。
CLI・GUI・API の3経路で共有する Qt-free サービス。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lorairo.database.repository.annotation_record import AnnotationRepository, AnnotationSaveItem
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
from lorairo.domain.rating_mapper import map_rating
from lorairo.domain.score_scaler import is_ai_scored_model, positive_key_for
from lorairo.utils.log import logger

if TYPE_CHECKING:
    from lorairo.database.schema import AnnotationsDict, RatingAnnotationData


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


@dataclass(frozen=True)
class _ModelRef:
    id: int


@dataclass(frozen=True)
class _PreparedAnnotationSave:
    source_key: str
    image_id: int
    annotations: AnnotationsDict


class AnnotationSaveService:
    """アノテーション結果のDB保存サービス。

    PHashAnnotationResults をDBに保存する。CLI・GUI・API の3経路で共有する。
    Qt依存なし。
    """

    def __init__(
        self,
        annotation_repo: AnnotationRepository,
        image_repo: ImageRepository | None = None,
        model_repo: ModelRepository | None = None,
        error_record_repo: ErrorRecordRepository | None = None,
    ) -> None:
        """AnnotationSaveService初期化。

        ADR 0035 段階 6 (#423): legacy facade 撤廃により、関連 Aggregate Repo を個別に
        inject する。`annotation_repo` のみ必須で、他は共有 session_factory から
        自動生成されたものが渡されることを想定。

        Args:
            annotation_repo: AnnotationRepository (save_annotations / tag 登録系)。
            image_repo: ImageRepository (phash / filepath ベースの画像 ID lookup)。
            model_repo: ModelRepository (model lookup)。
            error_record_repo: ErrorRecordRepository (エラー記録 / refused 画像 ID)。
        """
        if isinstance(annotation_repo, ImageRepository):
            raise TypeError("annotation_repo must be AnnotationRepository, not ImageRepository")
        self._annotation_repo = annotation_repo
        # 補助 Repo: 未指定時は session_factory を流用して生成 (DI contract 維持)。
        sf = annotation_repo.session_factory
        self._image_repo = image_repo or ImageRepository(session_factory=sf)
        self._model_repo = model_repo or ModelRepository(session_factory=sf)
        self._error_record_repo = error_record_repo or ErrorRecordRepository(session_factory=sf)

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
        model_name: str,
    ) -> None:
        """モデルの1件分アノテーション結果をAnnotationsDictに追加する。

        ADR 0027 / iam-lib ADR 0002: ``score_labels`` は canonical scorer の
        categorical label (例: "very aesthetic", "aesthetic")。``tags`` フィールドとは
        独立に保持する (content tag との混入を避ける)。

        Issue #626: AI scorer は ``higher_is_better=True`` の positive key 1 個だけを
        生値で保存する (complement の lq / not_aesthetic は保存しない)。同一 model で
        cafe/shadow が 2 行保存され DB で positive 判別不能になる問題を防ぐ。変換
        (0-10 表示尺度) は読み取り時に行う。
        """
        if scores:
            self._append_scores(model_id, scores, model_name, result)
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
            self._append_rating_row(model_id, ratings, result)

    def _append_scores(
        self,
        model_id: int,
        scores: dict[str, float],
        model_name: str,
        result: AnnotationsDict,
    ) -> None:
        """scores を Score 行として AnnotationsDict に追加する (Issue #626)。

        既知の AI scorer は positive key (``higher_is_better=True``) 1 個だけを保存する。
        positive key が ``scores`` に無い場合は warning を出してスキップする。未知 scorer
        (テーブル未登録) は後方互換のため従来どおり全 key を保存する。

        Args:
            model_id: scorer の DB model ID。
            scores: scorer が出力した ``{key: raw_value}`` 辞書。
            model_name: scorer model 名 (positive key 判定に使う registry key)。
            result: 追記先の AnnotationsDict。
        """
        if is_ai_scored_model(model_name):
            positive_key = positive_key_for(model_name)
            if positive_key is None or positive_key not in scores:
                logger.warning(
                    f"scorer '{model_name}' の positive key={positive_key!r} が scores に無いため"
                    f"スコア保存をスキップ: keys={list(scores.keys())}"
                )
                return
            result["scores"].append(
                {
                    "model_id": model_id,
                    "score": float(scores[positive_key]),
                    "is_edited_manually": False,
                }
            )
            return

        # 未知 scorer: 後方互換で全 key を保存する。
        for _name, value in scores.items():
            result["scores"].append(
                {"model_id": model_id, "score": float(value), "is_edited_manually": False}
            )

    def _append_rating_row(self, model_id: int, ratings: Any, result: AnnotationsDict) -> None:
        """rating を canonical 値に変換して result["ratings"] へ追加する (変換不能なら無視)。"""
        rating_row = self._build_rating_row(model_id, ratings)
        if rating_row is not None:
            result["ratings"].append(rating_row)

    # canonical rating の有効値 (後方互換 str 経路の検証用)。
    # api/types.py の _VALID_RATINGS から保存対象外の UNRATED を除いた集合。
    _CANONICAL_RATINGS: frozenset[str] = frozenset({"PG", "PG-13", "R", "X", "XXX"})

    @staticmethod
    def _extract_prediction_attr(prediction: Any, name: str) -> Any:
        """RatingPrediction (Pydantic モデル) / 辞書の両対応で属性を取得する。"""
        if isinstance(prediction, dict):
            return prediction.get(name)
        return getattr(prediction, name, None)

    def _confidence_sort_key(self, prediction: Any) -> float:
        """confidence_score の sort key。欠損 (None) は最下位扱い、実値 0.0 はそのまま保持する。"""
        score = self._extract_prediction_attr(prediction, "confidence_score")
        return -1.0 if score is None else float(score)

    def _select_rating_prediction(self, ratings: Any) -> Any | None:
        """structured rating 群から最高 confidence の予測を 1 件選ぶ。

        ``list[RatingPrediction]`` が主経路。``confidence_score`` が None の予測は
        最下位扱い。全 None / 同値の場合は ``max`` の安定性により先頭 (top-1) を選ぶ。

        Args:
            ratings: image-annotator-lib の ``UnifiedAnnotationResult.ratings`` 相当。

        Returns:
            選択された RatingPrediction 相当のオブジェクト。候補が無ければ None。
        """
        candidates = ratings if isinstance(ratings, list) else [ratings]
        predictions = [p for p in candidates if isinstance(p, dict) or hasattr(p, "raw_label")]
        if not predictions:
            return None
        return max(predictions, key=self._confidence_sort_key)

    def _build_canonical_str_row(self, model_id: int, value: str) -> RatingAnnotationData | None:
        """後方互換: source_scheme を持たない str rating を canonical 値として保存する。

        ``source_scheme`` が無いため変換できず、値が canonical rating
        (``PG/PG-13/R/X/XXX``) であればそのまま保存、そうでなければスキップする。
        """
        normalized = value.strip().upper()
        if normalized not in self._CANONICAL_RATINGS:
            logger.warning(f"canonical でない str rating をスキップ: {value!r}")
            return None
        return {
            "model_id": model_id,
            "raw_rating_value": value.strip(),
            "normalized_rating": normalized,
            "confidence_score": None,
        }

    def _build_rating_row(self, model_id: int, ratings: Any) -> RatingAnnotationData | None:
        """``ratings`` を canonical rating 1 行 (RatingAnnotationData) に変換する。

        ``Rating`` テーブルは ``(image_id, model_id)`` で upsert されるため、list が
        来ても 1 行に絞る。マッピング不能・未知スキーマの場合は None を返す
        (壊れた値を保存せずスキップ)。

        Args:
            model_id: rating を出力したモデルの DB ID。
            ratings: image-annotator-lib 由来の rating (structured / str 後方互換)。

        Returns:
            保存用 RatingAnnotationData。変換不能なら None。
        """
        # 後方互換: str / list[str] は source_scheme を持たないため canonical 値とみなす
        if isinstance(ratings, str):
            return self._build_canonical_str_row(model_id, ratings)
        if isinstance(ratings, list) and ratings and all(isinstance(r, str) for r in ratings):
            return self._build_canonical_str_row(model_id, ratings[0])

        prediction = self._select_rating_prediction(ratings)
        if prediction is None:
            logger.warning(f"rating 予測を抽出できません: {ratings!r}")
            return None

        raw_label = self._extract_prediction_attr(prediction, "raw_label")
        source_scheme = self._extract_prediction_attr(prediction, "source_scheme")
        confidence = self._extract_prediction_attr(prediction, "confidence_score")
        if not raw_label or not source_scheme:
            logger.warning(f"rating 予測に raw_label / source_scheme が欠落: {prediction!r}")
            return None

        normalized = map_rating(str(raw_label), str(source_scheme))
        if normalized is None:
            logger.warning(f"rating マッピング不能: scheme={source_scheme!r} label={raw_label!r}")
            return None

        return {
            "model_id": model_id,
            "raw_rating_value": str(raw_label),
            "normalized_rating": normalized,
            "confidence_score": confidence,
        }

    # ADR 0023 Phase 1.5 amendment (Issue #599): iam-lib は refusal / empty annotation
    # を library error ではなく structured outcome として返す。LoRAIro ではこれらを
    # annotation 対象から除外すべき outcome として error_records に記録する。
    _ANNOTATION_OUTCOME_RECORD_ERROR_CODES: tuple[str, ...] = (
        "SAFETY_REFUSAL",
        "CONTENT_POLICY_REFUSAL",
        "EMPTY_ANNOTATION",
    )

    # legacy migration 行の fallback sentinel: __legacy_<id>__.
    # runtime 保存経路では通常モデルとして扱わず必ずスキップする。
    _LEGACY_SENTINEL_PREFIX = "__legacy_"
    _LEGACY_SENTINEL_SUFFIX = "__"

    @classmethod
    def _is_legacy_sentinel_model_id(cls, model_name: str) -> bool:
        """モデル名が legacy fallback sentinel (`__legacy_<id>__`) かどうかを判定する。"""
        if not (
            model_name.startswith(cls._LEGACY_SENTINEL_PREFIX)
            and model_name.endswith(cls._LEGACY_SENTINEL_SUFFIX)
        ):
            return False

        if len(model_name) <= len(cls._LEGACY_SENTINEL_PREFIX) + len(cls._LEGACY_SENTINEL_SUFFIX):
            return False

        model_id = model_name[len(cls._LEGACY_SENTINEL_PREFIX) : -len(cls._LEGACY_SENTINEL_SUFFIX)]
        return model_id.isdecimal()

    @classmethod
    def _detect_annotation_outcome_error_type(cls, error_code: Any) -> str | None:
        """`UnifiedAnnotationResult.error_code` から LoRAIro 記録対象 code を抽出する。

        Args:
            error_code: `UnifiedAnnotationResult.error_code` の値 (str | StrEnum | None | 他)。

        Returns:
            `error_records.error_type` に保存する code 文字列、または記録対象外なら None。
        """
        if error_code is None:
            return None
        code = getattr(error_code, "value", error_code)
        if not isinstance(code, str):
            return None
        return code if code in cls._ANNOTATION_OUTCOME_RECORD_ERROR_CODES else None

    def _process_model_result(
        self,
        model_name: str,
        unified_result: Any,
        models_cache: dict[str, Any],
        result: AnnotationsDict,
        image_id: int | None = None,
    ) -> None:
        """1モデル分のアノテーション結果をAnnotationsDictに追記する。

        ADR 0023 Phase 1.5 amendment (Issue #599): error_code が
        SAFETY_REFUSAL / CONTENT_POLICY_REFUSAL / EMPTY_ANNOTATION の場合、
        `error_records` に記録してから skip する。`image_id is None` の場合は
        記録できないため warning のみ出して skip する。

        Args:
            model_name: アノテーションを行ったモデル名。
            unified_result: image-annotator-lib から返された UnifiedAnnotationResult。
            models_cache: model_name → Model の事前取得キャッシュ。
            result: 追記先の AnnotationsDict。
            image_id: 対象画像 ID。outcome を error_records に記録する際に必要。
        """
        if self._is_legacy_sentinel_model_id(model_name):
            logger.warning(
                f"legacy sentinel モデルID {model_name} を保存対象外としてスキップ: image_id={image_id}"
            )
            return

        error_code = self._extract_field(unified_result, "error_code")
        error = self._extract_field(unified_result, "error")
        retryable = self._extract_field(unified_result, "retryable")
        outcome_error_type = self._detect_annotation_outcome_error_type(error_code)
        if outcome_error_type is not None:
            # LoRAIro では retry せず error_records に記録 → 送信前 filter で除外。
            error_message = str(error or "")
            if image_id is not None:
                self._error_record_repo.save_error_record(
                    operation_type="annotation",
                    error_type=outcome_error_type,
                    error_message=error_message,
                    image_id=image_id,
                    model_name=model_name,
                )
                logger.warning(
                    f"Annotation outcome recorded to error_records: model={model_name}, "
                    f"image_id={image_id}, type={outcome_error_type}"
                )
            else:
                logger.warning(
                    f"Annotation outcome detected but image_id missing, cannot persist: "
                    f"model={model_name}, type={outcome_error_type}"
                )
            return

        if error or error_code:
            if retryable:
                logger.warning(f"モデル {model_name} retryable annotation outcome をスキップ")
            else:
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
            model_name,
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
                if self._is_legacy_sentinel_model_id(model_name):
                    continue
                if self._extract_field(unified_result, "error") or self._extract_field(
                    unified_result, "error_code"
                ):
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

        return self._annotation_repo.batch_resolve_tag_ids(normalized_tags)

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

        self._annotation_repo.save_annotations(
            image_id,
            annotations_dict,
            skip_existence_check=True,
            tag_id_cache=tag_id_cache if tag_id_cache else None,
        )
        logger.debug(f"画像ID {image_id} のアノテーション保存成功")
        return True

    def _annotation_save_chunk_size(self) -> int:
        chunk_size = getattr(self._annotation_repo, "BATCH_CHUNK_SIZE", 15000)
        return chunk_size if isinstance(chunk_size, int) and chunk_size > 0 else 15000

    @staticmethod
    def _iter_chunks(
        items: Sequence[_PreparedAnnotationSave], chunk_size: int
    ) -> Iterator[Sequence[_PreparedAnnotationSave]]:
        for start in range(0, len(items), chunk_size):
            yield items[start : start + chunk_size]

    def _save_prepared_batch(
        self,
        prepared_items: Sequence[_PreparedAnnotationSave],
        *,
        tag_id_cache: dict[str, int | None],
        error_message: Callable[[_PreparedAnnotationSave, Exception], str],
        log_message: Callable[[_PreparedAnnotationSave, Exception], str],
    ) -> tuple[int, int, list[str]]:
        """準備済み annotation を chunked batch 保存し、失敗 chunk は per-image retry する。"""
        if not prepared_items:
            return (0, 0, [])

        success_count = 0
        error_count = 0
        error_details: list[str] = []
        chunk_size = self._annotation_save_chunk_size()

        for chunk in self._iter_chunks(prepared_items, chunk_size):
            repo_items = [
                AnnotationSaveItem(
                    image_id=item.image_id,
                    annotations=item.annotations,
                    skip_existence_check=True,
                    tag_id_cache=tag_id_cache if tag_id_cache else None,
                )
                for item in chunk
            ]
            try:
                self._annotation_repo.save_annotations_batch(repo_items, chunk_size=len(repo_items))
                success_count += len(repo_items)
                continue
            except Exception as e:
                logger.warning(
                    f"バッチDB保存に失敗しました。per-image fallbackへ切り替えます: "
                    f"chunk_size={len(repo_items)}, error={e}"
                )

            for item in chunk:
                try:
                    self._annotation_repo.save_annotations(
                        item.image_id,
                        item.annotations,
                        skip_existence_check=True,
                        tag_id_cache=tag_id_cache if tag_id_cache else None,
                    )
                    success_count += 1
                except Exception as e:
                    error_msg = error_message(item, e)
                    error_details.append(error_msg)
                    error_count += 1
                    logger.error(log_message(item, e), exc_info=True)

        return (success_count, error_count, error_details)

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

        # #633: 同一 pHash に別版 (複数 image_id) が紐づき得るため、全 image_id へ fan-out 保存する。
        # pHash 単独 → 単一 image_id の旧キー化では別版が突合から漏れていた。
        phash_to_image_ids = self._image_repo.find_image_ids_by_phashes_multi(set(results.keys()))

        all_model_names, all_raw_tags = self._collect_names_and_tags(results)
        # ADR 0023 Phase 1.11 (Issue #238): registry key (= AnnotatorInfo.name) を
        # litellm_model_id SSoT に直接マップする。Phase 1.10 後は registry key と
        # litellm_model_id が一致するため (WebAPI 完全 ID / ローカル ML bare name)。
        models_cache = self._model_repo.get_models_by_litellm_ids(all_model_names)
        tag_id_cache = self._resolve_tag_ids(all_raw_tags)

        skip_count = 0
        error_count = 0
        error_details: list[str] = []
        prepared_items: list[_PreparedAnnotationSave] = []

        for phash, phash_annotations in results.items():
            try:
                image_ids = phash_to_image_ids.get(phash) or []
                if not image_ids:
                    logger.warning(
                        f"pHash {phash[:8]}... に対応する画像がDBに見つかりません。スキップします。"
                    )
                    skip_count += 1
                    continue

                # 別版を含む全 image_id へアノテーションを保存する (#633)
                appended = False
                for image_id in image_ids:
                    annotations_dict = self._build_annotations_dict(
                        phash_annotations, models_cache, image_id=image_id
                    )
                    if not annotations_dict or not any(annotations_dict.values()):
                        logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
                        continue
                    prepared_items.append(
                        _PreparedAnnotationSave(
                            source_key=str(phash), image_id=image_id, annotations=annotations_dict
                        )
                    )
                    appended = True

                # この pHash でどの image_id にも保存対象が無ければスキップ集計
                if not appended:
                    skip_count += 1
            except Exception as e:
                error_msg = f"phash={phash[:8]}...: {e}"
                error_details.append(error_msg)
                error_count += 1
                logger.error(f"保存失敗 phash={phash[:8]}...: {e}", exc_info=True)

        success_count, batch_error_count, batch_error_details = self._save_prepared_batch(
            prepared_items,
            tag_id_cache=tag_id_cache,
            error_message=lambda item, e: f"phash={item.source_key[:8]}...: {e}",
            log_message=lambda item, e: f"保存失敗 phash={item.source_key[:8]}...: {e}",
        )
        error_count += batch_error_count
        error_details.extend(batch_error_details)

        total_count = len(results)
        logger.info(f"DB保存完了: {success_count}/{total_count}件成功")

        return AnnotationSaveResult(
            success_count=success_count,
            skip_count=skip_count,
            error_count=error_count,
            total_count=total_count,
            error_details=error_details,
        )

    def save_provider_batch_results_by_image_id(
        self,
        results_by_image_id: Mapping[int, Any],
        *,
        model_id: int | None,
        model_name: str,
    ) -> AnnotationSaveResult:
        """Provider Batch の normalized result を image_id keyed で保存する。

        Provider Batch import は ``custom_id`` → ``provider_batch_items.image_id`` を
        SSoT とするため、pHash や file stem fallback は使わない。
        """
        if not results_by_image_id:
            return AnnotationSaveResult(
                success_count=0,
                skip_count=0,
                error_count=0,
                total_count=0,
            )
        if model_id is None:
            raise ValueError("Provider Batch result 保存には model_id が必要です")

        wrapped_results = {
            int(image_id): {model_name: unified_result}
            for image_id, unified_result in results_by_image_id.items()
        }
        _model_names, all_raw_tags = self._collect_names_and_tags(wrapped_results)
        models_cache: dict[str, Any] = {model_name: _ModelRef(model_id)}
        tag_id_cache = self._resolve_tag_ids(all_raw_tags)

        skip_count = 0
        error_count = 0
        error_details: list[str] = []
        prepared_items: list[_PreparedAnnotationSave] = []

        for image_id, image_annotations in wrapped_results.items():
            try:
                annotations_dict = self._build_annotations_dict(
                    image_annotations,
                    models_cache,
                    image_id=image_id,
                )
                if not annotations_dict or not any(annotations_dict.values()):
                    logger.debug(f"画像ID {image_id} に保存するアノテーションがありません")
                    skip_count += 1
                    continue
                prepared_items.append(
                    _PreparedAnnotationSave(
                        source_key=str(image_id), image_id=image_id, annotations=annotations_dict
                    )
                )
            except Exception as e:
                error_msg = f"image_id={image_id}: {e}"
                error_details.append(error_msg)
                error_count += 1
                logger.error(f"Provider Batch result 保存失敗 image_id={image_id}: {e}", exc_info=True)

        success_count, batch_error_count, batch_error_details = self._save_prepared_batch(
            prepared_items,
            tag_id_cache=tag_id_cache,
            error_message=lambda item, e: f"image_id={item.image_id}: {e}",
            log_message=lambda item, e: f"Provider Batch result 保存失敗 image_id={item.image_id}: {e}",
        )
        error_count += batch_error_count
        error_details.extend(batch_error_details)

        total_count = len(wrapped_results)
        logger.info(f"Provider Batch result DB保存完了: {success_count}/{total_count}件成功")
        return AnnotationSaveResult(
            success_count=success_count,
            skip_count=skip_count,
            error_count=error_count,
            total_count=total_count,
            error_details=error_details,
        )

    # ADR 0023 Phase 1.5 amendment (Issue #599): WebAPI annotation 対象から、過去に
    # refusal / empty annotation outcome を返した画像を除外するための送信前 filter。
    REFUSAL_ERROR_TYPES: tuple[str, ...] = (
        "SAFETY_REFUSAL",
        "CONTENT_POLICY_REFUSAL",
        "EMPTY_ANNOTATION",
    )
    _RATING_EXCLUSION_VALUES: frozenset[str] = frozenset({"X", "XXX"})

    def filter_refused_image_paths(self, image_paths: list[str]) -> list[str]:
        """過去に safety/content refusal または empty annotation を返した画像 path を除外する。

        **本 method は WebAPI 推論経路向けの filter** — SafetyRefusal /
        ContentPolicyRefusal は cloud provider の content policy 拒否概念で、
        ローカル ML モデル (WD-Tagger 等) はこの種の refusal を返さない。
        したがって caller はローカルモデル単独実行時に本 filter を呼ばないこと。
        WebAPI モデルが選択モデルに含まれているかの判定は呼び出し側 (`worker_service`)
        で行う (`selection_includes_webapi_model()` 参照)。

        ADR 0023 Phase 1.5 amendment の送信前 filter:
            operation_type = "annotation"
            error_type in {"SAFETY_REFUSAL", "CONTENT_POLICY_REFUSAL", "EMPTY_ANNOTATION"}
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
            self._error_record_repo.get_error_image_ids(
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
        path_to_image_id = self._image_repo.get_image_ids_by_filepaths(image_paths)

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
                f"(outcome 除外: {excluded_count}件)"
            )
        return filtered

    def filter_excluded_by_rating(self, image_paths: list[str]) -> list[str]:
        """`ratings.normalized_rating` が X / XXX の画像を除外する prefilter を行う。

        本 method は rating 事前フィルタの SSoT として、`ratings.normalized_rating`
        を唯一の判定源として扱う。
        - X / XXX: 送信除外
        - PG / PG-13 / R / UNRATED / None: 送信許可
        - 未登録 path: filter 対象外として通過

        Args:
            image_paths: アノテーション対象候補の画像 path リスト。

        Returns:
            X / XXX 除外後の image_path リスト (順序維持)。
        """
        if not image_paths:
            return []

        path_to_image_id = self._image_repo.get_image_ids_by_filepaths(image_paths)
        image_ids = [image_id for image_id in set(path_to_image_id.values()) if image_id is not None]
        if not image_ids:
            logger.debug("rating prefilter: 画像ID未解決のため除外なし")
            return list(image_paths)

        try:
            latest_rating_map = self._image_repo.get_latest_normalized_ratings_by_image_ids(image_ids)
        except Exception as e:
            logger.warning(f"rating prefilter 取得失敗: {e}", exc_info=True)
            return list(image_paths)

        excluded_image_ids = {
            image_id
            for image_id, normalized in latest_rating_map.items()
            if normalized in self._RATING_EXCLUSION_VALUES
        }
        if not excluded_image_ids:
            logger.debug(f"rating prefilter: 除外対象なし (対象件数={len(image_paths)}件)")
            return list(image_paths)

        filtered = []
        excluded_count = 0
        for path in image_paths:
            image_id = path_to_image_id.get(path)
            if image_id is not None and image_id in excluded_image_ids:
                excluded_count += 1
                continue
            filtered.append(path)

        if excluded_count > 0:
            logger.info(f"rating prefilter: 対象 {len(filtered)}件 (rating 除外: {excluded_count}件)")

        return filtered
