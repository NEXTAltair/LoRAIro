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
    write_user_translation,
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

    # 翻訳品質評価で recommend_translation_quality へ渡す言語コード (#976)。ja のみ評価する
    # (en は元タグ自身、それ以外は #976 スコープ外)。
    TRANSLATION_QUALITY_LANGUAGE = "ja"

    # tagdb は翻訳の language を verbatim 格納する (正規化しない)。日本語翻訳の格納キーは
    # "japanese" (LoRAIro 登録 / tagdb register GUI 既定) と ISO code "ja" (一部データ源 /
    # base patch) が混在しうる。片方しか見ないと有効な日本語訳を「未翻訳」と誤判定し
    # missing_translation の大量偽陽性 ⚠ になる (#991 P1) ため、両表記を日本語として扱う。
    _JAPANESE_TRANSLATION_KEYS = ("japanese", "ja")

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
        translation_recs = self._evaluate_translation_quality(tag, repo=repo, format_name=format_name)
        if not translation_recs:
            return manual
        return self._merge_recommendations(manual, translation_recs)

    def _evaluate_translation_quality(
        self, tag: str, *, repo: object | None = None, format_name: str = "unknown"
    ) -> list[RefinementRecommendation]:
        """タグの ja 翻訳品質を評価し、問題が出たものだけ返す (#976)。

        実在タグ (入力に完全一致する行が存在) の網羅性を優先する (ユーザー判断 #991):
        - 完全一致行が無い (別タグの翻訳経由マッチ / 行なし / 取得失敗) → 素通し
          (偽陽性 ⚠ 防止、missing も出さない)。
        - 完全一致行があり ja 翻訳候補がある → 全候補を評価。
        - 完全一致行があるが ja 翻訳が未登録/空 → `translation=None` で評価して
          `missing_translation` を発火させる (search_tags の projection は空翻訳を除外する
          ため、候補ループでは missing を検出できないので明示的に評価する)。

        日本語翻訳の格納キーは "japanese" と "ja" が混在しうるため、両方を集約してから
        評価する (#991 P1)。

        Args:
            tag: 評価対象の canonical タグ文字列。
            repo: lib に渡す DB リーダー。None なら merged reader を使う。
            format_name: タグの format 名。manual refinement と同じ format で翻訳を引く
                (判定不能時 "unknown" は format フィルタなし)。

        Returns:
            needs_refinement=True だった評価ごとの RefinementRecommendation。
        """
        translations = self._fetch_exact_match_translations(tag, repo=repo, format_name=format_name)
        if translations is None:
            # 完全一致行が無い → 翻訳品質評価をスキップ (素通し)。
            return []
        candidates: list[str] = []
        for key in self._JAPANESE_TRANSLATION_KEYS:
            for value in translations.get(key, []):
                if value not in candidates:
                    candidates.append(value)
        recommendations: list[RefinementRecommendation] = []
        if not candidates:
            # 実在タグだが ja 翻訳が未登録/空 → missing_translation を発火させる。
            rec = recommend_translation_quality(
                source_tag=tag,
                translation=None,
                language=self.TRANSLATION_QUALITY_LANGUAGE,
            )
            if rec.needs_refinement:
                recommendations.append(rec)
        else:
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

    def _fetch_exact_match_translations(
        self, tag: str, *, repo: object | None = None, format_name: str = "unknown"
    ) -> dict[str, list[str]] | None:
        """入力タグに完全一致する行の言語別翻訳候補を取得する (#976)。

        戻り値で「完全一致行の有無」と「翻訳候補の中身」を区別する:
        - None: 完全一致行が無い (別タグの翻訳経由マッチ / 行なし / DB read 失敗)。
          呼び出し元は翻訳品質評価をスキップする (偽陽性 ⚠ 防止)。
        - dict: 完全一致行が存在する。中身が空 ({} や ja キー無し) の場合は ja 翻訳が
          未登録/空であることを表し、呼び出し元は missing_translation を判定する。

        完全一致の判定は tagdb の refinement path
        (`genai_tag_db_tools.core_api._canonical_exact_recommendation_rows`) と同じく、
        行の `tag` または `source_tag` が入力タグへ casefold 一致するかで行う。これにより
        手動保存された source tag や大文字小文字違いの canonical でも、manual refinement と
        翻訳品質評価の対象範囲が一致する。複数の完全一致行 (base / user 分割等) は
        言語ごとに翻訳候補をマージする。

        `format_name` が既知 (≠ "unknown") のときは search を当該 format に絞り、同一
        canonical tag が複数 format に存在する DB で別 format の翻訳を借用しないようにする
        (#991 P2)。

        Args:
            tag: 検索する canonical タグ文字列。
            repo: 検索に使う DB リーダー。None なら merged reader を使う。
            format_name: 検索を絞る format 名。"unknown" のときは format フィルタなし。

        Returns:
            完全一致行が無ければ None、あれば言語コード -> 翻訳候補リストのマップ。
        """
        reader = cast("TagReaderProtocol", repo) if repo is not None else self.reader
        # format が既知のときだけ絞る ("unknown" は判定不能の sentinel なので絞らない)。
        format_names = None if format_name == "unknown" else [format_name]
        request = TagSearchRequest(
            query=tag,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=True,
            format_names=format_names,
        )
        try:
            result = search_tags(reader, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            # 既存 search_tags 呼び出し箇所 (trigger_vocab) と同じ search-failure クラスを
            # catch し、翻訳品質評価を非ブロッキングに縮退させる (#991 P2)。
            logger.warning(f"翻訳取得に失敗 (翻訳品質評価をスキップ): tag='{tag}': {e}")
            return None
        # tag / source_tag が casefold 一致した行のみ採用する (Codex #991 P2)。partial=False でも
        # alias / 別タグの翻訳経由でマッチした行はその翻訳を借用せず、無関係な偽陽性 ⚠ を防ぐ。
        normalized_query = tag.casefold()
        merged: dict[str, list[str]] = {}
        found_exact = False
        for item in result.items:
            is_exact_match = item.tag.casefold() == normalized_query or (
                item.source_tag is not None and item.source_tag.casefold() == normalized_query
            )
            if not is_exact_match:
                continue
            found_exact = True
            if not item.translations:
                continue
            for language, values in item.translations.items():
                bucket = merged.setdefault(language, [])
                for value in values:
                    if value not in bucket:
                        bucket.append(value)
        # 完全一致行があれば翻訳 (空でも可) を返し、無ければ None で素通しさせる。
        return merged if found_exact else None

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

    def resolve_tag_id(self, canonical: str) -> int | None:
        """canonical タグ文字列を tag_db の tag_id へ解決します (#989)。

        TagPanelWidget の userdb 操作 Signal は canonical (str) のみを運ぶため、書き込み
        API (翻訳追加 / type 補正) が要求する tag_id を親 dispatch でここから解決する。
        danbooru format に絞った完全一致検索を行い、`tag` または `source_tag` が casefold
        一致した行の tag_id を返す (別タグの翻訳経由マッチを採用しない、#991 P2 と同方針)。

        Args:
            canonical: 解決する canonical タグ文字列。

        Returns:
            一致した tag_id。未ヒット / 検索失敗時は None。
        """
        request = TagSearchRequest(
            query=canonical,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=True,
            format_names=["danbooru"],
        )
        try:
            result = search_tags(self.reader, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"tag_id 解決に失敗: canonical='{canonical}': {e}")
            return None
        normalized = canonical.casefold()
        for item in result.items:
            if item.tag.casefold() == normalized or (
                item.source_tag is not None and item.source_tag.casefold() == normalized
            ):
                return cast("int", item.tag_id)
        logger.warning(f"tag_id 解決で完全一致なし: canonical='{canonical}'")
        return None

    def add_translation(self, tag_id: int, language: str, translation: str) -> None:
        """タグへ言語別翻訳を user DB overlay として追加します (#989)。

        書き込みは user DB の翻訳 overlay (`USER_TAG_TRANSLATION_PATCH`) にのみ行われ、
        base DB は書き換えない (公開 API `write_user_translation` が scope を tag_id から導出)。

        Args:
            tag_id: 翻訳を付与する対象タグの tag_id。
            language: 言語コード (例: "ja")。
            translation: 翻訳文字列。

        Raises:
            Exception: 書き込みに失敗した場合。
        """
        try:
            write_user_translation(self.repository, tag_id, language, translation)
            logger.info(
                "Added translation overlay: tag_id={}, language={}",
                tag_id,
                language,
            )
        except Exception as e:
            logger.error(
                "Error adding translation: tag_id={}, language={}: {}",
                tag_id,
                language,
                e,
                exc_info=True,
            )
            raise
