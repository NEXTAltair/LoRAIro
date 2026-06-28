"""trigger word 語彙のユーザー DB 登録・補完サービス（Issue #946）。

ExportOverlayBar (#948) の trigger 補完リストへ語彙を供給する Qt-free サービス。
genai-tag-db-tools の安定 public API のみを使い、trigger word を
**ユーザー DB（USER_TAGS, tag_id >= 1_000_000_000）** の専用 format に隔離登録する。
canonical / danbooru タグ DB は汚染しない（ADR 0080 / Epic #942 の語彙レイヤー）。

trigger は ADR 0080 の通り **リテラル**（convert バイパス）なので、漢字を含む語を
``source_tag`` にそのまま保持し、補完候補もリテラル形で返す。USER_TAGS.tag には
正規化形（アンダースコア除去・空白整形）を格納して検索の一貫性を保つ。
"""

from __future__ import annotations

from dataclasses import dataclass

from genai_tag_db_tools import (
    TagCleaner,
    create_tag_register_service,
    get_user_tag_reader,
    register_tag,
    search_tags,
)
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from loguru import logger

# trigger 語彙を隔離するユーザー DB の専用 format / type。
# 専用 format に分離することで search を trigger のみへ絞り込み、
# 既存タグ（danbooru 等）が補完候補に混ざらないようにする。
_TRIGGER_FORMAT = "lorairo_trigger"
_TRIGGER_TYPE = "unknown"


@dataclass(frozen=True)
class VocabEntry:
    """trigger 語彙の1エントリ。

    Attributes:
        word: trigger word のリテラル文字列（漢字含む。補完候補に表示・挿入する形）。
        freq: 過去の使用回数（usage_count）。未集計なら 0。降順ソートに使う。
    """

    word: str
    freq: int


class TriggerVocabService:
    """trigger word 語彙のユーザー DB 登録・補完を担う Qt-free サービス。

    genai-tag-db-tools の安定 public API（``register_tag`` / ``search_tags`` /
    ``get_user_tag_reader`` / ``create_tag_register_service``）経由でユーザー DB の
    専用 format ``lorairo_trigger`` に trigger 語彙を出し入れする。

    reader / register service はユーザー DB 未初期化時に例外を投げ得るため、
    遅延初期化し、失敗時は graceful degradation（search→空リスト、register→no-op）。
    一度失敗したら同セッション中は再試行しない。
    """

    def __init__(
        self,
        reader: object | None = None,
        register_service: object | None = None,
    ) -> None:
        """TriggerVocabService を初期化する。

        Args:
            reader: ユーザー DB reader ハンドル（テスト注入用）。None なら遅延生成。
            register_service: タグ登録サービスハンドル（テスト注入用）。None なら遅延生成。
        """
        self._reader = reader
        self._reader_initialized = reader is not None
        self._register_service = register_service
        self._register_service_initialized = register_service is not None

    # ------------------------------------------------------------------
    # Public API（#948 が依存する契約）
    # ------------------------------------------------------------------

    def search(self, prefix: str) -> list[VocabEntry]:
        """prefix に前方/部分一致する trigger 語彙を freq 降順で返す。

        ユーザー DB のみを読むため、base / danbooru の canonical タグは候補に
        混ざらない。usage_count を freq として扱い、降順・同数は word 昇順。

        Args:
            prefix: 補完クエリ。空文字なら全 trigger 語彙を返す。

        Returns:
            VocabEntry のリスト（freq 降順・word 昇順、word 重複は初出優先）。
            reader 取得失敗時は空リスト（graceful degradation）。
        """
        reader = self._get_reader()
        if reader is None:
            return []

        query = TagCleaner.clean_format(prefix).strip()
        request = TagSearchRequest(
            query=query,
            partial=True,
            format_names=[_TRIGGER_FORMAT],
            resolve_preferred=False,
            include_aliases=False,
            include_deprecated=False,
        )
        try:
            result = search_tags(reader, request)
        except (ValueError, RuntimeError) as e:
            logger.warning(f"trigger 語彙検索に失敗（縮退、空リストで継続）: {e}")
            return []

        # word はリテラル（source_tag）優先、無ければ正規化形（tag）。
        # freq は usage_count（未集計なら 0）。重複 word は初出優先で畳む。
        seen: set[str] = set()
        entries: list[VocabEntry] = []
        for row in result.items:
            word = row.source_tag or row.tag
            if word in seen:
                continue
            seen.add(word)
            entries.append(VocabEntry(word=word, freq=row.usage_count or 0))

        entries.sort(key=lambda e: (-e.freq, e.word))
        return entries

    def register(self, word: str) -> None:
        """trigger word をユーザー DB の専用 format に登録する。

        リテラル形を ``source_tag`` に、正規化形（アンダースコア除去・空白整形）を
        ``tag`` に格納する。既存なら冪等（lib 側で重複は created=False）。

        Args:
            word: 登録する trigger word（リテラル。漢字可）。空文字は無視。
        """
        literal = word.strip()
        if not literal:
            logger.debug("trigger word が空のため登録をスキップ")
            return

        service = self._get_register_service()
        if service is None:
            return

        normalized = TagCleaner.clean_format(literal).strip()
        if not normalized:
            logger.debug(f"正規化後に空になったため登録をスキップ: {literal!r}")
            return

        request = TagRegisterRequest(
            tag=normalized,
            source_tag=literal,
            format_name=_TRIGGER_FORMAT,
            type_name=_TRIGGER_TYPE,
            scope="user",
        )
        try:
            result = register_tag(service, request)
        except (ValueError, RuntimeError) as e:
            logger.warning(f"trigger 語彙登録に失敗（縮退、no-op で継続）: {e}")
            return
        logger.debug(
            f"trigger 語彙を登録: word={literal!r} created={result.created} tag_id={result.tag_id}"
        )

    # ------------------------------------------------------------------
    # 遅延初期化（graceful degradation）
    # ------------------------------------------------------------------

    def _get_reader(self) -> object | None:
        """ユーザー DB reader を遅延生成して返す。失敗時は None（再試行しない）。"""
        if not self._reader_initialized:
            self._reader_initialized = True
            try:
                self._reader = get_user_tag_reader()
            except (RuntimeError, ValueError) as e:
                logger.warning(f"ユーザー DB reader 初期化に失敗（trigger 補完を無効化）: {e}")
                self._reader = None
        return self._reader

    def _get_register_service(self) -> object | None:
        """タグ登録サービスを遅延生成して返す。失敗時は None（再試行しない）。"""
        if not self._register_service_initialized:
            self._register_service_initialized = True
            try:
                self._register_service = create_tag_register_service()
            except (RuntimeError, ValueError) as e:
                logger.warning(f"タグ登録サービス初期化に失敗（trigger 登録を無効化）: {e}")
                self._register_service = None
        return self._register_service
