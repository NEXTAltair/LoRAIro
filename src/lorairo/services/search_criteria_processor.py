"""
SearchCriteriaProcessor - 検索・フィルタリングビジネスロジック専用サービス

このサービスは検索条件の処理、フィルタリングロジック、検索実行の
ビジネスルールを担当します。GUIから分離された純粋なビジネスロジック層です。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..database.db_manager import ImageDatabaseManager
from .search_models import SearchConditions

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader


def resolve_tag_search_targets(
    merged_reader: MergedTagReader | None,
    keywords: list[str],
    *,
    limit_per_keyword: int = 20,
) -> list[str]:
    """入力キーワードを翻訳解決し、元キーワード + 翻訳ヒットした正規タグ名を返す (#1094)。

    日本語などの入力キーワードを genai_tag_db_tools の ``search_tags()`` に通し、
    翻訳テーブル経由でヒットした正規タグ名を検索対象に追加する。英語直接マッチは
    元キーワードをそのまま残すことで維持する。``merged_reader`` が None (tag DB 不在)
    の場合は元キーワードのみを返してグレースフルデグラデーションする。

    Args:
        merged_reader: genai-tag-db-tools の MergedTagReader。None 可。
        keywords: 検索入力キーワード。
        limit_per_keyword: 1 キーワードあたりの翻訳解決取得上限。

    Returns:
        元キーワードと翻訳ヒット正規タグ名を重複排除して結合したリスト。
    """
    resolved: list[str] = list(keywords)
    if merged_reader is None or not keywords:
        return resolved

    from genai_tag_db_tools import search_tags
    from genai_tag_db_tools.models import TagSearchRequest

    seen = {kw.lower() for kw in resolved}
    for keyword in keywords:
        try:
            request = TagSearchRequest(
                query=keyword,
                partial=True,
                resolve_preferred=True,
                include_aliases=True,
                include_deprecated=False,
                limit=limit_per_keyword,
            )
            result = search_tags(merged_reader, request)
        except Exception as e:
            # tag DB 障害は検索全体を止めず縮退させる (元キーワードのみで検索継続)
            logger.debug(f"タグ翻訳解決に失敗 (keyword='{keyword}'): {e}")
            continue
        for item in result.items:
            canonical = item.tag
            if canonical and canonical.lower() not in seen:
                resolved.append(canonical)
                seen.add(canonical.lower())

    if len(resolved) > len(keywords):
        logger.debug(f"タグ翻訳解決: {keywords} -> {resolved}")
    return resolved


def _fetch_merged_reader(db_manager: ImageDatabaseManager) -> MergedTagReader | None:
    """db_manager から MergedTagReader を取得する。取得不能時は None (縮退)。"""
    annotation_repo = getattr(db_manager, "annotation_repo", None)
    get_merged_reader = getattr(annotation_repo, "get_merged_reader", None)
    if not callable(get_merged_reader):
        return None
    try:
        return get_merged_reader()
    except Exception as e:
        logger.debug(f"MergedTagReader 取得に失敗、翻訳解決なしで検索: {e}")
        return None


def build_tag_resolver(db_manager: ImageDatabaseManager) -> Callable[[list[str]], list[str]]:
    """db_manager の MergedTagReader を遅延取得するタグ翻訳解決コールバックを返す (#1094)。

    検索結果と件数見積もりの両経路で同一の翻訳解決を使うための共通ファクトリ。
    #1122 Codex P2: caption-only / rating-only / date-only / 空キーワード検索では
    タグ翻訳解決が不要なため、``get_merged_reader()`` を eager に呼ばず、実際にタグ語解決が
    必要になった初回呼び出し時にだけ reader を取得してキャッシュする。tag DB 不在時は
    元キーワードをそのまま返す。
    """
    reader_holder: dict[str, MergedTagReader | None] = {}

    def resolver(keywords: list[str]) -> list[str]:
        if not keywords:
            return list(keywords)
        if "reader" not in reader_holder:
            reader_holder["reader"] = _fetch_merged_reader(db_manager)
        return resolve_tag_search_targets(reader_holder["reader"], keywords)

    return resolver


class SearchCriteriaProcessor:
    """
    検索・フィルタリングビジネスロジック専用サービス

    責任:
    - 検索条件の分析と変換
    - データベース検索とフロントエンドフィルタリングの分離
    - フィルタリングアルゴリズムの実装
    - 検索パフォーマンスの最適化
    """

    def __init__(self, db_manager: ImageDatabaseManager):
        """
        SearchCriteriaProcessorを初期化

        Args:
            db_manager: データベース操作用のImageDatabaseManager
        """
        self.db_manager = db_manager
        logger.debug("SearchCriteriaProcessor initialized")

    def execute_search_with_filters(self, conditions: SearchConditions) -> tuple[list[dict[str, Any]], int]:
        """
        統一検索実行（直接呼び出し方式）

        SearchConditionsを使用してデータベース検索を実行し、
        フィルター処理も適用した結果を返します。

        Args:
            conditions: 検索条件オブジェクト

        Returns:
            tuple: (検索結果リスト, 総件数)
        """
        try:
            # フロントエンドフィルターが必要な条件のみ分離
            frontend_filters = {
                "aspect_ratio": conditions.aspect_ratio_filter,
                "exclude_duplicates": conditions.exclude_duplicates,
            }

            # DB検索実行（ImageFilterCriteria使用）
            # #1094: タグ検索は入力キーワードを翻訳解決してから DB へ渡す
            filter_criteria = conditions.to_filter_criteria(tag_resolver=self._build_tag_resolver())
            images, total_count = self.db_manager.get_images_by_filter(criteria=filter_criteria)

            # フロントエンドフィルター適用（必要時のみ）
            applied_frontend_filters = any(frontend_filters.values())
            if applied_frontend_filters:
                images = self._apply_simple_frontend_filters(images, conditions)

            # DB検索のみの場合はDB総件数を返す。フロントエンドフィルター適用時は件数が変わるためlen(images)を返す。
            reported_count = len(images) if applied_frontend_filters else total_count
            logger.info(
                "検索実行完了: 結果件数={}, 総件数={}, frontend_filter={}",
                len(images),
                total_count,
                applied_frontend_filters,
            )
            return images, reported_count

        except Exception as e:
            logger.error(f"検索実行中にエラーが発生しました: {e}", exc_info=True)
            raise

    def _build_tag_resolver(self) -> Callable[[list[str]], list[str]]:
        """db_manager の MergedTagReader を束縛したタグ翻訳解決コールバックを返す (#1094)。"""
        return build_tag_resolver(self.db_manager)

    def process_date_filter(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        日付フィルター処理

        日付範囲条件を処理し、データベースクエリに適した形式に変換します。

        Args:
            conditions: 検索条件

        Returns:
            dict: 処理済み日付条件
        """
        try:
            date_conditions = {}

            if conditions.date_filter_enabled:
                if conditions.date_range_start:
                    date_conditions["start_date"] = conditions.date_range_start
                if conditions.date_range_end:
                    date_conditions["end_date"] = conditions.date_range_end

            logger.debug(f"日付条件処理完了: {date_conditions}")
            return date_conditions

        except Exception as e:
            logger.error(f"日付フィルター処理中にエラー: {e}", exc_info=True)
            return {}

    def apply_untagged_filter(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        未タグ付きフィルターの適用

        未タグ付き画像の検索条件を処理します。

        Args:
            conditions: 検索条件

        Returns:
            dict: 未タグ付きフィルター条件
        """
        try:
            untagged_conditions = {}

            if conditions.only_untagged:
                untagged_conditions["has_tags"] = False

            # tagged_onlyプロパティがある場合の処理
            if hasattr(conditions, "tagged_only") and getattr(conditions, "tagged_only", False):
                untagged_conditions["has_tags"] = True

            logger.debug(f"未タグ付きフィルター処理完了: {untagged_conditions}")
            return untagged_conditions

        except Exception as e:
            logger.error(f"未タグ付きフィルター処理中にエラー: {e}", exc_info=True)
            return {}

    def apply_tagged_filter_logic(self, conditions: SearchConditions) -> dict[str, Any]:
        """
        タグ付きフィルターロジックの適用

        論理演算子を含むタグフィルタリングの処理を行います。

        Args:
            conditions: 検索条件

        Returns:
            dict: 処理済みタグ条件
        """
        try:
            tag_conditions: dict[str, Any] = {}

            if conditions.keywords and conditions.is_tag_search_enabled():
                tag_conditions["tags"] = conditions.keywords
                tag_conditions["tag_operator"] = conditions.tag_logic

            logger.debug(f"タグフィルターロジック処理完了: {tag_conditions}")
            return tag_conditions

        except Exception as e:
            logger.error(f"タグフィルターロジック処理中にエラー: {e}", exc_info=True)
            return {}

    def _apply_simple_frontend_filters(
        self, images: list[dict[str, Any]], conditions: SearchConditions
    ) -> list[dict[str, Any]]:
        """
        シンプルなフロントエンドフィルターの適用

        データベースで処理できない条件をメモリ内で処理します。

        Args:
            images: 画像データリスト
            conditions: 検索条件

        Returns:
            list: フィルター済み画像データリスト
        """
        try:
            filtered_images = images

            # アスペクト比フィルター
            if conditions.aspect_ratio_filter:
                filtered_images = self._filter_by_aspect_ratio(
                    filtered_images, conditions.aspect_ratio_filter
                )

            # 重複除外フィルター
            if conditions.exclude_duplicates:
                filtered_images = self._filter_by_duplicate_exclusion(filtered_images)

            logger.debug(f"フロントエンドフィルター適用完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"フロントエンドフィルター適用中にエラー: {e}", exc_info=True)
            return images

    def _resolve_target_aspect_ratio(self, aspect_ratio_filter: str) -> float:
        """フィルター文字列から目標アスペクト比を抽出する。

        UIラベルの「x:y」形式を優先し、名前ベースのフォールバックを行う。

        Args:
            aspect_ratio_filter: アスペクト比フィルター条件（文字列）

        Returns:
            目標アスペクト比（width / height）
        """
        ratio_match = re.search(r"(\d+)\s*:\s*(\d+)", aspect_ratio_filter)
        if ratio_match:
            numerator = int(ratio_match.group(1))
            denominator = int(ratio_match.group(2))
            if denominator != 0:
                return numerator / denominator

        if "正方形" in aspect_ratio_filter:
            return 1.0
        if "風景" in aspect_ratio_filter:
            return 16 / 9
        if "縦長" in aspect_ratio_filter:
            return 9 / 16
        return 1.0

    def _image_matches_aspect_ratio(
        self, image: dict[str, Any], target_ratio: float, tolerance: float
    ) -> bool:
        """画像のアスペクト比が目標範囲内か判定する。

        Args:
            image: 画像データ辞書（width, heightキーを含む）
            target_ratio: 目標アスペクト比
            tolerance: 許容誤差

        Returns:
            マッチすればTrue
        """
        width = int(image.get("width", 0))
        height = int(image.get("height", 0))
        if width <= 0 or height <= 0:
            return False
        return bool(abs(width / height - target_ratio) <= tolerance)

    def _filter_by_aspect_ratio(
        self, images: list[dict[str, Any]], aspect_ratio_filter: str
    ) -> list[dict[str, Any]]:
        """アスペクト比フィルタリング。

        指定されたアスペクト比条件で画像をフィルタリングします。

        Args:
            images: 画像データリスト
            aspect_ratio_filter: アスペクト比フィルター条件（文字列）

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not aspect_ratio_filter or aspect_ratio_filter == "全て":
                return images

            target_ratio = self._resolve_target_aspect_ratio(aspect_ratio_filter)
            tolerance = 0.1

            filtered_images = [
                image
                for image in images
                if self._image_matches_aspect_ratio(image, target_ratio, tolerance)
            ]

            logger.debug(f"アスペクト比フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"アスペクト比フィルター中にエラー: {e}", exc_info=True)
            return images

    def _filter_by_date_range(
        self, images: list[dict[str, Any]], date_filter: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        日付範囲フィルタリング

        指定された日付範囲で画像をフィルタリングします。

        Args:
            images: 画像データリスト
            date_filter: 日付フィルター条件

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not date_filter:
                return images

            filtered_images = []
            start_date = date_filter.get("start_date")
            end_date = date_filter.get("end_date")

            for image in images:
                image_date = image.get("created_at") or image.get("modified_at")
                if image_date:
                    if isinstance(image_date, str):
                        # ISO文字列の「Z」サフィックスを適切に処理
                        if image_date.endswith("Z"):
                            image_date = image_date[:-1] + "+00:00"
                        image_date = datetime.fromisoformat(image_date)

                    # timezone-aware/naive問題を修正:両方ともnaiveにする
                    if image_date.tzinfo is not None:
                        image_date = image_date.replace(tzinfo=None)

                    # start_date/end_dateもnaiveに統一
                    start_date_naive = (
                        start_date.replace(tzinfo=None) if start_date and start_date.tzinfo else start_date
                    )
                    end_date_naive = (
                        end_date.replace(tzinfo=None) if end_date and end_date.tzinfo else end_date
                    )

                    if start_date_naive and image_date < start_date_naive:
                        continue
                    if end_date_naive and image_date > end_date_naive:
                        continue

                    filtered_images.append(image)

            logger.debug(f"日付範囲フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"日付範囲フィルター中にエラー: {e}", exc_info=True)
            return images

    def _filter_by_duplicate_exclusion(self, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        重複画像除外 (属性ベース分類、ADR 0061 §4 / #633)

        pHash 単独ではなく分類属性 (width / height / has_alpha / is_grayscale_like) 込みで
        重複を判定する。#630 以降は同一 pHash でも属性差のある「別版」が別レコードとして
        登録され得るため、pHash 一致だけで除外すると別版を誤って取りこぼす。

        判定には登録側と同じ ``ImageRepository.classify_phash_candidate`` を再利用する。
        これにより遅延 backfill 未済の NULL 属性は「不明 = 一致扱い」(NULL-as-wildcard) となり、
        登録分類と挙動が一致する。NULL を厳密不一致にすると、旧 DB の真の重複が別版に誤判定され
        重複除外フィルタが pHash-only 時代より退行してしまう問題を避ける。

        Args:
            images: 画像データリスト

        Returns:
            list: フィルター済み画像リスト
        """
        from lorairo.database.repository.image import ImageRepository, PhashClassification

        try:
            # 解像度フィルタ検索では返却メタが processed_images 由来で phash / オリジナル
            # 分類属性を欠くため、pHash 不在の画像だけ Image テーブルから重複判定フィールドを
            # 補完する (#1106)。resolution=0 検索は phash を持つため fetch は発生しない。
            missing_ids = [
                img["id"] for img in images if img.get("id") is not None and not img.get("phash")
            ]
            original_by_id: dict[int, dict[str, Any]] = (
                self.db_manager.image_repo.get_phash_classification_by_ids(missing_ids)
                if missing_ids
                else {}
            )

            # pHash → 保持済み画像の分類属性リスト (NULL-as-wildcard 比較の候補)
            kept_candidates_by_phash: dict[str, list[dict[str, Any]]] = {}
            filtered_images: list[dict[str, Any]] = []

            for image in images:
                # 重複判定はオリジナル画像の phash / 分類属性で行う。processed メタで phash が
                # 欠ける場合は補完済みの original_by_id を参照する (#1106)。
                dedup_view = image
                image_id = image.get("id")
                if not image.get("phash") and image_id is not None:
                    original = original_by_id.get(image_id)
                    if original is not None:
                        dedup_view = original

                phash = dedup_view.get("phash")

                if not isinstance(phash, str) or not phash:
                    # pHashがない場合は重複判定不能のため、そのまま保持する
                    filtered_images.append(image)
                    continue

                candidates = kept_candidates_by_phash.setdefault(phash, [])
                # 既に保持済みの同 pHash 画像と分類比較。DUPLICATE なら真の重複として除外。
                classification, _ = ImageRepository.classify_phash_candidate(dedup_view, candidates)
                if classification is PhashClassification.DUPLICATE:
                    continue  # 属性まで一致する真の重複 (NULL は一致扱い) → スキップ

                # 新規 / 別版は保持し、以降の比較候補に加える。表示用には元の image (processed
                # メタ) を残しつつ、比較候補にはオリジナル分類属性を積む。
                # classify_phash_candidate は DUPLICATE 時 candidate["id"] を参照するため
                # id も候補に含める (本フィルタでは戻り値の id は使わない)。
                filtered_images.append(image)
                candidate_attrs: dict[str, Any] = {
                    attr: dedup_view.get(attr) for attr in ImageRepository.CLASSIFICATION_ATTRS
                }
                candidate_attrs["id"] = image.get("id")
                candidates.append(candidate_attrs)

            logger.debug(
                f"重複除外完了: {len(images)} -> {len(filtered_images)}件 "
                f"(重複除外: {len(images) - len(filtered_images)}件)"
            )
            return filtered_images

        except Exception as e:
            logger.error(f"重複除外フィルター中にエラー: {e}", exc_info=True)
            return images

    def filter_images_by_annotation_status(
        self, images: list[dict[str, Any]], annotation_status: str
    ) -> list[dict[str, Any]]:
        """
        アノテーション状態による画像フィルタリング

        メモリ内でアノテーション状態による画像フィルタリングを実行します。

        Args:
            images: 画像データリスト
            annotation_status: アノテーション状態

        Returns:
            list: フィルター済み画像リスト
        """
        try:
            if not annotation_status or annotation_status == "all":
                return images

            # 全画像IDを収集して一括チェック（N+1回避）
            image_ids = [img["id"] for img in images if img.get("id")]
            annotated_ids = self.db_manager.get_annotated_image_ids(image_ids)

            # メモリ内フィルタリング
            if annotation_status == "annotated":
                filtered_images = [img for img in images if img.get("id") in annotated_ids]
            else:  # "not_annotated"
                filtered_images = [img for img in images if img.get("id") not in annotated_ids]

            logger.debug(f"アノテーション状態フィルター完了: {len(images)} -> {len(filtered_images)}件")
            return filtered_images

        except Exception as e:
            logger.error(f"アノテーション状態フィルター中にエラー: {e}", exc_info=True)
            return images

    def _parse_resolution_value(self, resolution_str: str) -> tuple[int | None, int | None]:
        """
        解像度文字列をパースして幅と高さを取得

        Args:
            resolution_str: 解像度文字列 (例: "1920x1080")

        Returns:
            tuple: (幅, 高さ) または (None, None)
        """
        try:
            if not resolution_str:
                return None, None

            # "1920x1080" 形式のパース
            match = re.match(r"(\d+)x(\d+)", resolution_str)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return width, height

            return None, None

        except Exception as e:
            logger.error(f"解像度文字列パース中にエラー: {e}", exc_info=True)
            return None, None
