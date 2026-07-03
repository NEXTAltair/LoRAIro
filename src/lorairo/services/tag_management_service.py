"""タグ管理サービスモジュール。

unknown typeタグの検索、type_name選択、一括更新を担当します。
"""

import threading
from collections.abc import Iterable
from typing import cast

from genai_tag_db_tools import (
    TagReaderProtocol,
    TagWriterProtocol,
    get_all_type_names,
    get_format_type_names,
    get_preferred_translations_batch,
    get_tag_reader,
    get_unknown_type_tags,
    get_user_repository,
    recommend_manual_refinement,
    recommend_translation_quality,
    search_tags,
    search_tags_batch,
    set_preferred_translation,
    update_tags_type_batch,
    write_user_translation,
)
from genai_tag_db_tools.models import (
    RefinementRecommendation,
    TagRecordPublic,
    TagSearchRequest,
    TagSearchResult,
    TagTypeUpdate,
)
from sqlalchemy.exc import SQLAlchemyError

from ..utils.language_keys import language_alias_keys, translation_for_language
from ..utils.log import logger

# prefetch キャッシュの「未命中」を None (完全一致行なし) と区別するための番兵。
_PREFETCH_MISS = object()


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

    # manual refinement が「指定 format でこのタグは直接有効な canonical ではない」と判定した
    # reason code (#993)。これらが付いた保存タグの翻訳をグローバルに引いて評価すると、manual が
    # 既に別タグへ誘導/構造問題を flag 済みなのに無関係な missing/wrong translation ⚠ を merge し、
    # recommendation を ignore/fix した後も残るため、翻訳品質評価をスキップする:
    #   - alias_tag / non_preferred_tag: manual は preferred タグへ誘導済み。alias 行は preferred が
    #     訳を持っていても自分は持たないことが多い。
    #   - missing_format_status: タグ行は存在するが指定 concrete format に status が無い (タグは
    #     その format のタグではない)。format scoping を外した存在判定が別 format 行を拾って
    #     missing_translation 偽陽性を出すのを防ぐ (Codex PR #999)。翻訳は tag_id 直下で format
    #     非依存なので search の format フィルタではなくこの manual signal で gate する。
    _SKIP_TRANSLATION_REASON_CODES = frozenset({"alias_tag", "non_preferred_tag", "missing_format_status"})

    def __init__(self) -> None:
        """TagManagementServiceを初期化します。

        base DB + user overlay を統合した merged reader を使用します。
        アノテーションパスが legacy 書き込みパス (scope なし) を使う間は
        merged reader が必要です。
        """
        self.reader: TagReaderProtocol = get_tag_reader()
        self.repository: TagWriterProtocol = get_user_repository()
        # prefetch_translations が投入する完全一致翻訳キャッシュ (#998)。
        # キー = タグの casefold、値 = 言語別翻訳候補 (完全一致行なしは None)。
        # thread-local にする理由: 複数の RefinementWorker が別 QThread で並行実行されると、
        # 後発 worker の prefetch_translations が先発 worker の投入分を clear() で消してしまい、
        # N+1 解消が無効化されるレースになる (Codex #999 P2)。スレッドごとに分離することで、
        # 各 worker の prefetch → 消費が他スレッドに干渉されないようにする。
        self._prefetch_local = threading.local()
        logger.info(
            "TagManagementService initialized with format_id={}",
            self.LORAIRO_FORMAT_ID,
        )

    @property
    def _translation_prefetch_cache(self) -> dict[str, tuple[dict[str, list[str]] | None, list[int]]]:
        """呼び出しスレッド専用の prefetch キャッシュ (#998)。

        thread-local にすることで、並行実行される複数 RefinementWorker (別 QThread) の
        prefetch_translations 呼び出しが互いのキャッシュを clear() で消し合わないようにする。
        """
        cache = getattr(self._prefetch_local, "cache", None)
        if cache is None:
            cache = {}
            self._prefetch_local.cache = cache
        return cache

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
        # 指定 format でこのタグが直接有効な canonical でない (alias / 非 preferred / format status
        # 無し) と manual が判定した場合、グローバルに引いた翻訳の評価は無関係な偽陽性 ⚠ になるため
        # スキップする (#993、_SKIP_TRANSLATION_REASON_CODES の docstring 参照)。
        if self._SKIP_TRANSLATION_REASON_CODES.intersection(reason.code for reason in manual.reasons):
            return manual
        translation_recs = self._evaluate_translation_quality(tag, repo=repo)
        if not translation_recs:
            return manual
        return self._merge_recommendations(manual, translation_recs)

    def _evaluate_translation_quality(
        self, tag: str, *, repo: object | None = None
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

        Returns:
            needs_refinement=True だった評価ごとの RefinementRecommendation。
        """
        translations, tag_ids = self._fetch_exact_match_entry(tag, repo=repo)
        if translations is None:
            # 完全一致行が無い → 翻訳品質評価をスキップ (素通し)。
            return []
        candidates = self._collect_ja_candidates(translations)
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
            recommendations = self._evaluate_ja_candidates(tag, candidates)
            if recommendations:
                # ユーザーが「翻訳を修正」(#1054) で登録した user overlay の値は、同一言語
                # キーの base 誤訳候補を supersede する。overlay は追加専用のため base の
                # 誤訳行は消せず、全候補評価のままだと修正直後も同じ ⚠ が再発し続ける
                # (PR #1086 Codex P2)。警告が出たタグに限り overlay を引いて再評価する。
                overrides = self._user_translation_overrides(tag_ids, repo=repo)
                if overrides:
                    superseded: dict[str, list[str]] = {
                        key: [overrides[key]] if key in overrides else translations.get(key, [])
                        for key in self._JAPANESE_TRANSLATION_KEYS
                    }
                    recommendations = self._evaluate_ja_candidates(
                        tag, self._collect_ja_candidates(superseded)
                    )
        if recommendations:
            logger.trace(
                f"翻訳品質の問題を検出: tag='{tag}', 候補数={len(candidates)}, 問題={len(recommendations)}"
            )
        return recommendations

    def _collect_ja_candidates(self, translations: dict[str, list[str]]) -> list[str]:
        """ja 系言語キー ("ja"/"japanese") の翻訳候補を順序保持で重複排除して集める (#976)。"""
        candidates: list[str] = []
        for key in self._JAPANESE_TRANSLATION_KEYS:
            for value in translations.get(key, []):
                if value not in candidates:
                    candidates.append(value)
        return candidates

    def _evaluate_ja_candidates(self, tag: str, candidates: list[str]) -> list[RefinementRecommendation]:
        """ja 翻訳候補を全評価し、問題が出たものだけ返す (#976)。"""
        recommendations: list[RefinementRecommendation] = []
        for candidate in candidates:
            rec = recommend_translation_quality(
                source_tag=tag,
                translation=candidate,
                language=self.TRANSLATION_QUALITY_LANGUAGE,
            )
            if rec.needs_refinement:
                recommendations.append(rec)
        return recommendations

    def _user_translation_overrides(
        self, tag_ids: list[int], *, repo: object | None = None
    ) -> dict[str, str]:
        """user overlay に登録済みの ja 系翻訳 (言語キーごとの最新値) を返す (#1054)。

        「翻訳を修正」で登録した値は、同一言語キーの base 候補を品質評価で supersede する
        ための provenance。overlay (`USER_TAG_TRANSLATION_PATCH`) は追加専用のため、同一
        言語キーに複数 patch がある場合は最新 (translation_id = patch_id 最大) を採用する。

        Args:
            tag_ids: 完全一致行の tag_id 集合。
            repo: user overlay を持つ merged reader。None なら self.reader。

        Returns:
            ``{言語キー: 最新のユーザー翻訳}``。overlay 未使用/取得失敗は空 dict
            (呼び出し元は全候補評価に fallback)。
        """
        reader = repo if repo is not None else self.reader
        user_repo = getattr(reader, "user_repo", None)
        if user_repo is None or not tag_ids:
            return {}
        latest: dict[str, str] = {}
        try:
            for tag_id in tag_ids:
                rows = sorted(user_repo.get_translations(tag_id), key=lambda r: r.translation_id)
                for row in rows:
                    if row.language in self._JAPANESE_TRANSLATION_KEYS and row.translation:
                        latest[row.language] = row.translation
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            logger.warning(f"user overlay 翻訳の取得に失敗 (全候補評価に fallback): {e}")
            return {}
        return latest

    def _fetch_exact_match_translations(
        self, tag: str, *, repo: object | None = None
    ) -> dict[str, list[str]] | None:
        """入力タグに完全一致する行の言語別翻訳候補のみ返す互換ラッパー (#976/#1054)。"""
        return self._fetch_exact_match_entry(tag, repo=repo)[0]

    def _fetch_exact_match_entry(
        self, tag: str, *, repo: object | None = None
    ) -> tuple[dict[str, list[str]] | None, list[int]]:
        """入力タグに完全一致する行の言語別翻訳候補を取得する (#976)。

        戻り値の第1要素で「完全一致行の有無」と「翻訳候補の中身」を区別する:
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

        翻訳は format に依存しない: tagdb の `TAG_TRANSLATIONS` は `tag_id` (タグ文字列の
        identity) への FK だけを持ち format_id を持たない。照合キーの `TAGS.tag` は UNIQUE
        なので 1 タグ文字列 = 1 tag_id = 1 翻訳セット。よって search を format で絞っても
        返る翻訳は変わらず (CLI 実測で format 有無同一を確認)、`format_names` は常に指定しない
        (#993、当初の format 整合案 #991 P2 は撤回)。

        prefetch_translations で事前一括取得済みならキャッシュを参照し (per-tag の
        search_tags を N 回呼ぶ N+1 を回避、#998)、未命中なら従来どおり単発 search_tags で
        fallback する。キャッシュ命中は consume-once (pop) で、prefetch した集合の外での
        stale 参照を避ける。

        Args:
            tag: 検索する canonical タグ文字列。
            repo: 検索に使う DB リーダー。None なら merged reader を使う。

        Returns:
            (翻訳マップ, 完全一致行の tag_id リスト)。完全一致行が無ければ (None, [])。
            tag_id は user overlay の provenance 照合 (#1054) に使う。
        """
        cached = self._translation_prefetch_cache.pop(tag.casefold(), _PREFETCH_MISS)
        if cached is not _PREFETCH_MISS:
            return cast("tuple[dict[str, list[str]] | None, list[int]]", cached)
        reader = cast("TagReaderProtocol", repo) if repo is not None else self.reader
        request = TagSearchRequest(
            query=tag,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=True,
            format_names=None,
        )
        try:
            result = search_tags(reader, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            # 既存 search_tags 呼び出し箇所 (trigger_vocab) と同じ search-failure クラスを
            # catch し、翻訳品質評価を非ブロッキングに縮退させる (#991 P2)。
            logger.warning(f"翻訳取得に失敗 (翻訳品質評価をスキップ): tag='{tag}': {e}")
            return None, []
        return self._extract_exact_entry(result, tag)

    def _extract_exact_entry(
        self, result: TagSearchResult, tag: str
    ) -> tuple[dict[str, list[str]] | None, list[int]]:
        """search 結果から入力タグに完全一致する行の言語別翻訳と tag_id をマージする (#976/#998)。

        `tag` / `source_tag` が入力へ casefold 一致した行のみ採用する (Codex #991 P2)。
        partial=False でも alias / 別タグの翻訳経由でマッチした行はその翻訳を借用せず、
        無関係な偽陽性 ⚠ を防ぐ。完全一致行があれば (翻訳マップ, tag_id リスト) を、
        無ければ (None, []) を返す。
        """
        normalized_query = tag.casefold()
        merged: dict[str, list[str]] = {}
        tag_ids: list[int] = []
        found_exact = False
        for item in result.items:
            is_exact_match = item.tag.casefold() == normalized_query or (
                item.source_tag is not None and item.source_tag.casefold() == normalized_query
            )
            if not is_exact_match:
                continue
            found_exact = True
            if item.tag_id is not None and item.tag_id not in tag_ids:
                tag_ids.append(item.tag_id)
            if not item.translations:
                continue
            for language, values in item.translations.items():
                bucket = merged.setdefault(language, [])
                for value in values:
                    if value not in bucket:
                        bucket.append(value)
        return (merged, tag_ids) if found_exact else (None, [])

    def resolve_usage_counts_for_tags(
        self, tags: "Iterable[str]", *, repo: object | None = None
    ) -> dict[str, dict[str, int]]:
        """タグ集合のサイト (format) 別使用カウントを 1 回の batch で解決する (#1052)。

        refinement 候補タグ (表示中タグとは別 canonical) の counts 併記用。
        per-tag ループの N+1 は禁止 (#998)。取得失敗は空 dict (名前のみ表示) に落とす。

        Returns:
            ``{タグ: {format_name: usage_count}}``。count が 0 の format は含めない。
        """
        unique = list(dict.fromkeys(tag for tag in tags if tag))
        if not unique:
            return {}
        reader = cast("TagReaderProtocol", repo) if repo is not None else self.reader
        try:
            batch = search_tags_batch(reader, unique, format_names=None, resolve_preferred=False)
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            logger.warning(f"候補タグの使用カウント解決に失敗 (名前のみ表示): {e}")
            return {}
        counts: dict[str, dict[str, int]] = {}
        for query, result in batch.items():
            query_key = query.casefold()
            for item in result.items:
                if (item.tag or "").casefold() != query_key and (
                    item.source_tag or ""
                ).casefold() != query_key:
                    continue
                per_format = {
                    format_name: int(status.get("usage_count") or 0)
                    for format_name, status in (item.format_statuses or {}).items()
                    if status and int(status.get("usage_count") or 0) > 0
                }
                if per_format:
                    counts[query] = per_format
                break
        return counts

    def prefetch_translations(self, tags: Iterable[str], *, repo: object | None = None) -> None:
        """タグ集合の完全一致翻訳を 1〜0 リポ往復で一括取得しキャッシュする (#998)。

        `RefinementService.recommend_for_tags` が per-tag 評価の前に 1 回だけ呼ぶ。以降の
        `_fetch_exact_match_translations` はキャッシュを参照し、per-tag の `search_tags` を
        N 回呼ぶ N+1 を解消する。翻訳は format 非依存 (#993) なので `format_names=None` で
        全タグを 1 回の `search_tags_batch` にまとめる。

        batch 取得が失敗しても例外は伝播させず、キャッシュを空のままにして per-tag fallback
        (単発 `search_tags`) に委ねる (翻訳品質は advisory な非ブロッキング情報)。

        Args:
            tags: 事前取得するタグ文字列。
            repo: 検索に使う DB リーダー。None なら merged reader を使う。
        """
        # 再 prefetch 時に前回分の stale entry を残さないようクリアしてから投入する。
        self._translation_prefetch_cache.clear()
        # 順序を保ったまま重複除去する。
        unique = list(dict.fromkeys(t for t in tags if t))
        if not unique:
            return
        reader = cast("TagReaderProtocol", repo) if repo is not None else self.reader
        try:
            batch = search_tags_batch(reader, unique, format_names=None, resolve_preferred=False)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            # batch 失敗は per-tag fallback に委ねる (キャッシュ未投入)。
            logger.warning(f"翻訳の batch 取得に失敗 (per-tag fallback に委譲): {e}")
            return
        cache = self._translation_prefetch_cache
        for tag in unique:
            result = batch.get(tag)
            if result is None:
                # マッチ無し = 完全一致行なし → (None, []) (呼び出し元は素通し)。
                cache[tag.casefold()] = (None, [])
            else:
                cache[tag.casefold()] = self._extract_exact_entry(result, tag)
        logger.debug(f"翻訳 prefetch: 対象={len(unique)}件")

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
        format は絞らず (全 format 横断) 完全一致検索を行い、`tag` または `source_tag` が
        casefold 一致した行の tag_id を返す (別タグの翻訳経由マッチは採用しない、#991 P2 と
        同方針)。danbooru に絞ると手動追加で `format_name="Lorairo"` / `type_name="unknown"`
        として登録された user タグ (annotation_record._register_new_tag) が解決できず、
        メタ編集を最も必要とするタグで翻訳追加・type 補正が無言スキップされるため絞らない
        (Codex #995 P2)。

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
            format_names=None,
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
        """タグへ言語別翻訳を user DB overlay として追加し、主訳にします (#989 / #1084)。

        書き込みは user DB の翻訳 overlay (`USER_TAG_TRANSLATION_PATCH`) にのみ行われ、
        base DB は書き換えない (公開 API `write_user_translation` が scope を tag_id から導出)。

        追加した訳はその言語の主訳 (優先翻訳) にする (#1084)。主訳化しないと、同一言語に
        既存訳があるとき TagMetadataWorker の畳み込みが従来訳を採用し、追加した訳が chip に
        現れず「追加したのに見えない」問題が残るため。tag_id は解決済み (二重解決を避ける)
        なので、主訳設定も同じ tag_id を渡す。

        Args:
            tag_id: 翻訳を付与する対象タグの tag_id。
            language: 言語コード (例: "ja")。
            translation: 翻訳文字列。

        Raises:
            Exception: 書き込みに失敗した場合。
        """
        try:
            write_user_translation(self.repository, tag_id, language, translation)
            # 追加した訳を自動的にその言語の主訳にする (#1084)。free function を呼ぶ
            # (同名の service メソッドではなく lib 公開 API、self. 無しで module global 解決)。
            set_preferred_translation(self.repository, tag_id, language, translation)
            logger.info(
                "Added translation overlay + set preferred: tag_id={}, language={}",
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

    def list_translation_candidates(self, canonical: str, language: str) -> tuple[list[str], str | None]:
        """canonical タグの指定言語の候補訳一覧と現在の主訳を返す (#1084)。

        翻訳管理ダイアログのラジオ一覧を組み立てるための読み取り窓口。1 回の
        `search_tags` (安定公開 API) で完全一致行の tag_id と全候補訳を取り、当該言語
        (エイリアス両表記) の候補訳を出現順で dedupe する。現在の主訳は
        `get_preferred_translations_batch` で引く。完全一致行なし (tag_id 未解決) なら
        ([], None)。翻訳読み出しは reader の内部メソッド `get_translations_batch`
        (安定 `TagReaderProtocol` 非公開) ではなく、翻訳品質評価と同じ search_tags 経路を
        使い型安全にする。

        取得失敗は空側へ縮退させる (ダイアログを開けなくしない): search 失敗は ([], None)、
        主訳取得の失敗は候補のみ + None。

        Args:
            canonical: 候補を列挙する canonical タグ文字列。
            language: 言語コード ("ja" / "en")。

        Returns:
            (候補訳リスト (順序保持・重複排除), 現在の主訳 or None)。
        """
        request = TagSearchRequest(
            query=canonical,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=True,
            format_names=None,
        )
        try:
            result = search_tags(self.reader, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"翻訳候補の取得に失敗 (候補なし): canonical='{canonical}': {e}")
            return [], None
        # 完全一致行の言語別翻訳と tag_id を集約する (#1052 リファクタ後の共通ヘルパー)。
        translations_map, tag_ids = self._extract_exact_entry(result, canonical)
        if not tag_ids:
            return [], None
        tag_id = tag_ids[0]
        # 当該言語のエイリアス両表記を順序保持で dedupe する。
        translations = translations_map or {}
        candidates: list[str] = []
        for key in language_alias_keys(language):
            for value in translations.get(key, []):
                if value not in candidates:
                    candidates.append(value)
        current: str | None = None
        try:
            preferred = get_preferred_translations_batch(self.reader, [tag_id])
            current = translation_for_language(preferred.get(tag_id, {}), language)
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            # worker 側の advisory 読みと同じ縮退契約 (Codex P2): 主訳読み取りの一時失敗で
            # ダイアログ自体を開けなくしない。候補一覧 + 未設定 (None) で続行する。
            logger.warning(f"主訳の取得に失敗 (未設定として続行): canonical='{canonical}': {e}")
        return candidates, current

    def set_preferred_translation(self, canonical: str, language: str, translation: str) -> bool:
        """canonical タグの指定言語の主訳 (優先翻訳) を設定します (#1084)。

        canonical→tag_id を解決して lib 公開 API へ委譲する。候補一覧から選ばれた既存訳を
        主訳へ切り替える用途 (追加時の自動主訳化は `add_translation` が担う)。

        Args:
            canonical: 対象 canonical タグ文字列。
            language: 言語コード ("ja" / "en")。
            translation: 主訳にする翻訳文字列。

        Returns:
            設定できたら True。canonical→tag_id が未解決なら False (書き込みなし)。

        Raises:
            Exception: 書き込みに失敗した場合 (予期しない DB エラーは伝播させる)。
        """
        tag_id = self.resolve_tag_id(canonical)
        if tag_id is None:
            logger.warning(f"主訳設定をスキップ (tag_id 未解決): canonical='{canonical}'")
            return False
        try:
            # free function (lib 公開 API)。同名の service メソッドではなく module global。
            set_preferred_translation(self.repository, tag_id, language, translation)
            # 選んだ訳を正規化キー ("ja"/"en") の翻訳行としても保証する (Codex P2)。
            # legacy キー ("english" 等) の行しか無い候補を主訳にした場合、正規化キーの
            # 行が無いと get_tag_languages() が当該言語を広告せず、再起動後のセレクタに
            # 言語項目が現れない。write_user_translation は同一行の重複を無視するため冪等。
            write_user_translation(self.repository, tag_id, language, translation)
            logger.info(
                "Set preferred translation: tag_id={}, language={}",
                tag_id,
                language,
            )
        except Exception as e:
            logger.error(
                "Error setting preferred translation: tag_id={}, language={}: {}",
                tag_id,
                language,
                e,
                exc_info=True,
            )
            raise
        return True
