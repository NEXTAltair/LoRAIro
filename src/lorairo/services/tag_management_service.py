"""タグ管理サービスモジュール。

unknown typeタグの検索、type_name選択、一括更新を担当します。
"""

from typing import cast

from genai_tag_db_tools import (
    TagReaderProtocol,
    TagWriterProtocol,
    get_all_type_names,
    get_format_type_names,
    get_tag_reader,
    get_unknown_type_tags,
    get_user_repository,
    recommend_manual_refinement,
    recommend_translation_quality,
    search_tags,
    update_tags_type_batch,
)
from genai_tag_db_tools.models import (
    RefinementRecommendation,
    TagRecordPublic,
    TagSearchRequest,
    TagTypeUpdate,
)
from sqlalchemy.exc import SQLAlchemyError

from ..utils.log import logger


class TagManagementService:
    """LoRAIro format (format_id=1000) のタグ管理サービス。

    genai-tag-db-tools の公開APIを使用して、unknown typeタグの検索、
    type_name一覧取得、一括type更新を提供します。

    Note:
        読み込みは base DB + user overlay の merged reader を使用します。
        アノテーションパスが legacy 書き込みパス（scope なし）を使用している間、
        TAGS/TAG_STATUS に書き込まれたタグを可視化するために merged reader が必要です。
        書き込み（type 更新）は get_user_repository() 経由で user DB に行います。
    """

    LORAIRO_FORMAT_ID = 1000  # LoRAIro専用format_id（ユーザーDB範囲: 1000-）

    # 翻訳品質評価の対象言語 (#976)。ja の翻訳候補のみを評価する。
    # en は元タグ自身 (英語タグ) なので翻訳品質の問題対象にならず、それ以外の言語は
    # 本 Issue のスコープ外 (多言語拡張は対象外)。
    TRANSLATION_QUALITY_LANGUAGE = "ja"

    def __init__(self) -> None:
        """TagManagementServiceを初期化します。

        base DB + user overlay を統合した merged reader を使用します。
        アノテーションパスが legacy 書き込みパス (scope なし) を使う間は
        merged reader が必要です。
        """
        self.reader: TagReaderProtocol = get_tag_reader()
        self.repository: TagWriterProtocol = get_user_repository()
        logger.info(
            "TagManagementService initialized with format_id={}",
            self.LORAIRO_FORMAT_ID,
        )

    def get_unknown_tags(self) -> list[TagRecordPublic]:
        """user DBからunknown typeタグ一覧を取得します。

        Note:
            base DBのタグは含まれません。ユーザーが登録したタグのみが対象です。

        Returns:
            list[TagRecordPublic]: type_name="unknown"のタグリスト（user DBのみ）

        Raises:
            Exception: タグ検索中にエラーが発生した場合
        """
        try:
            tags = get_unknown_type_tags(self.reader, format_id=self.LORAIRO_FORMAT_ID)
            logger.info("Found {} unknown type tags for format_id={}", len(tags), self.LORAIRO_FORMAT_ID)
            return cast("list[TagRecordPublic]", tags)
        except Exception as e:
            logger.error("Error getting unknown type tags: {}", e, exc_info=True)
            raise

    def get_all_available_types(self) -> list[str]:
        """user DBで利用可能な全type_nameを取得します。

        Note:
            user DBに登録されているtype_nameのみが返されます。

        Returns:
            list[str]: user DBのtype_name一覧（例: ["character", "general", "meta", "unknown"]）

        Raises:
            Exception: type_name一覧取得中にエラーが発生した場合
        """
        try:
            types = get_all_type_names(self.reader)
            logger.debug("Retrieved {} type names", len(types))
            return cast("list[str]", types)
        except Exception as e:
            logger.error("Error getting all type names: {}", e, exc_info=True)
            raise

    def get_format_specific_types(self) -> list[str]:
        """user DBからLoRAIro format固有のtype_nameを取得します。

        Note:
            format_id=1000でuser DBに登録されているtype_nameのみが返されます。

        Returns:
            list[str]: format_id=1000で使用中のtype_name一覧（user DBのみ）

        Raises:
            Exception: format固有type_name取得中にエラーが発生した場合
        """
        try:
            types = get_format_type_names(self.reader, format_id=self.LORAIRO_FORMAT_ID)
            logger.debug(
                "Retrieved {} format-specific type names for format_id={}",
                len(types),
                self.LORAIRO_FORMAT_ID,
            )
            return cast("list[str]", types)
        except Exception as e:
            logger.error("Error getting format-specific type names: {}", e, exc_info=True)
            raise

    def update_tag_types(self, updates: list[TagTypeUpdate]) -> None:
        """タグのtypeを一括更新します。

        Args:
            updates (list[TagTypeUpdate]): 更新するタグとtype_nameのリスト

        Raises:
            ValueError: 無効なformat_idまたはtag_idが指定された場合
            Exception: 更新処理中にエラーが発生した場合
        """
        if not updates:
            logger.warning("No tag updates provided")
            return

        try:
            update_tags_type_batch(self.repository, updates, format_id=self.LORAIRO_FORMAT_ID)
            logger.info(
                "Successfully updated {} tags for format_id={}", len(updates), self.LORAIRO_FORMAT_ID
            )
        except ValueError as e:
            logger.error("Invalid tag update request: {}", e)
            raise
        except Exception as e:
            logger.error("Error updating tag types: {}", e, exc_info=True)
            raise

    def recommend_manual_refinement(
        self, tag: str, *, repo: object | None = None, format_name: str = "unknown"
    ) -> RefinementRecommendation:
        """タグ1個の refinement リコメンドを取得します (#931)。

        genai-tag-db-tools の判定をラップする単一窓口。repo 未指定時は本サービスの
        merged reader を渡し、エイリアス/タイポ候補を DB から参照させる (suggestion の品質向上)。

        Args:
            tag: 評価対象のタグ文字列。
            repo: lib に渡す DB リーダー。None なら merged reader を使う。
            format_name: タグの format 名。判定不能時は "unknown"。

        Returns:
            RefinementRecommendation: 判定結果 (needs_refinement / reasons / suggestions / proposals)。
        """
        reader = repo if repo is not None else self.reader
        return recommend_manual_refinement(tag, reader, format_name=format_name)

    def recommend_with_translation_quality(
        self, tag: str, *, repo: object | None = None, format_name: str = "unknown"
    ) -> RefinementRecommendation:
        """手動 refinement と翻訳品質リコメンドを統合して返す (#976)。

        manual refinement (`recommend_manual_refinement`) の結果に、タグの ja 翻訳候補を
        全件評価した翻訳品質 reason を合流させる。返り値は既存の ⚠ / tooltip / ignore
        フローへそのまま乗る単一の RefinementRecommendation。

        翻訳品質は advisory な非ブロッキング情報のため、翻訳取得 (DB read) が失敗しても
        manual refinement の結果のみを返す (例外は伝播させない)。

        Args:
            tag: 評価対象の canonical タグ文字列。
            repo: lib に渡す DB リーダー。None なら merged reader を使う。
            format_name: タグの format 名。判定不能時は "unknown"。

        Returns:
            manual refinement reason と翻訳品質 reason を統合した RefinementRecommendation。
        """
        manual = self.recommend_manual_refinement(tag, repo=repo, format_name=format_name)
        translation_recs = self._evaluate_translation_quality(tag, repo=repo)
        if not translation_recs:
            return manual
        return self._merge_recommendations(manual, translation_recs)

    def _evaluate_translation_quality(
        self, tag: str, *, repo: object | None = None
    ) -> list[RefinementRecommendation]:
        """タグの ja 翻訳候補を全件評価し、問題が出たものだけ返す (#976)。

        翻訳候補が無いタグは評価対象が無いため空リストを返す (未翻訳タグを一律で
        ⚠ にはしない)。

        Args:
            tag: 評価対象の canonical タグ文字列。
            repo: lib に渡す DB リーダー。None なら merged reader を使う。

        Returns:
            needs_refinement=True だった候補ごとの RefinementRecommendation。
        """
        translations = self._fetch_translations(tag, repo=repo)
        candidates = translations.get(self.TRANSLATION_QUALITY_LANGUAGE, [])
        recommendations: list[RefinementRecommendation] = []
        for candidate in candidates:
            rec = recommend_translation_quality(
                source_tag=tag,
                translation=candidate,
                language=self.TRANSLATION_QUALITY_LANGUAGE,
            )
            if rec.needs_refinement:
                recommendations.append(rec)
        if recommendations:
            logger.trace(
                f"翻訳品質の問題を検出: tag='{tag}', 候補数={len(candidates)}, 問題={len(recommendations)}"
            )
        return recommendations

    def _fetch_translations(self, tag: str, *, repo: object | None = None) -> dict[str, list[str]]:
        """tag の言語別翻訳候補 (language -> 候補リスト) を取得する (#976)。

        public API `search_tags` の完全一致検索で行を引き、`translations` を返す。
        翻訳取得は advisory な評価のための補助であり、DB read 失敗時は空 dict へ縮退する
        (呼び出し元は manual refinement のみを表示できる)。

        Args:
            tag: 検索する canonical タグ文字列。
            repo: 検索に使う DB リーダー。None なら merged reader を使う。

        Returns:
            言語コード -> 翻訳候補リストのマップ。該当行・翻訳が無ければ空 dict。
        """
        reader = cast("TagReaderProtocol", repo) if repo is not None else self.reader
        request = TagSearchRequest(
            query=tag,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=True,
        )
        try:
            result = search_tags(reader, request)
        except SQLAlchemyError as e:
            logger.warning(f"翻訳取得に失敗 (翻訳品質評価をスキップ): tag='{tag}': {e}")
            return {}
        for item in result.items:
            if item.tag == tag and item.translations:
                return item.translations
        if result.items and result.items[0].translations:
            return result.items[0].translations
        return {}

    def _merge_recommendations(
        self,
        manual: RefinementRecommendation,
        translation_recs: list[RefinementRecommendation],
    ) -> RefinementRecommendation:
        """manual と翻訳品質リコメンドを 1 つの RefinementRecommendation へ統合する (#976)。

        reason は code 単位で重複排除する (複数 ja 候補が同じ問題を出しても tooltip は1行)。
        proposals は全件連結し、suggestions は tag を持つ補正候補のみ連結する
        (翻訳品質の review_only suggestion は tag を持たず tooltip に出ないため除外)。
        score は最大値を採用する。

        Args:
            manual: manual refinement の結果。
            translation_recs: 問題が出た翻訳候補ごとのリコメンド。

        Returns:
            needs_refinement=True の統合 RefinementRecommendation。
        """
        seen_codes = {reason.code for reason in manual.reasons}
        merged_reasons = list(manual.reasons)
        merged_suggestions = list(manual.suggestions)
        merged_proposals = list(manual.proposals)
        max_score = manual.score
        for rec in translation_recs:
            for reason in rec.reasons:
                if reason.code not in seen_codes:
                    seen_codes.add(reason.code)
                    merged_reasons.append(reason)
            merged_suggestions.extend(s for s in rec.suggestions if s.tag)
            merged_proposals.extend(rec.proposals)
            max_score = max(max_score, rec.score)
        return manual.model_copy(
            update={
                "needs_refinement": True,
                "score": max_score,
                "reasons": merged_reasons,
                "suggestions": merged_suggestions,
                "proposals": merged_proposals,
            }
        )

    def update_single_tag_type(self, tag_id: int, type_name: str) -> None:
        """単一タグのtypeを更新します。

        Args:
            tag_id (int): 更新するタグのID
            type_name (str): 新しいtype_name

        Raises:
            ValueError: 無効なtag_idまたはtype_nameが指定された場合
            Exception: 更新処理中にエラーが発生した場合
        """
        update = TagTypeUpdate(tag_id=tag_id, type_name=type_name)
        self.update_tag_types([update])
