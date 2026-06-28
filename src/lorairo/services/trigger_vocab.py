"""trigger word 語彙のユーザー DB 登録・補完サービス（Issue #946）。

ExportOverlayBar (#948) の trigger 補完リストへ語彙を供給する Qt-free サービス。
genai-tag-db-tools の安定 public API のみを使い、trigger word を
**ユーザー DB（USER_TAGS, tag_id >= 1_000_000_000）** の専用 format に隔離登録する。
canonical / danbooru タグ DB は汚染しない（ADR 0080 / Epic #942 の語彙レイヤー）。

trigger は ADR 0080 の通り **リテラル**（convert バイパス）なので、入力された語を
そのまま ``tag`` / ``source_tag`` へ格納し、補完候補もリテラル形で返す。正規化はしない:
USER_TAGS は ``tag`` 列で dedup するため、正規化すると異なるリテラル
（例: ``my_trigger`` と ``my trigger``）が同一行に畳まれ、片方のリテラルが失われる。
リテラルをそのまま格納することで衝突を避け、literal trigger 契約を保つ。
"""

from __future__ import annotations

from dataclasses import dataclass

from genai_tag_db_tools import (
    create_tag_register_service,
    get_user_tag_reader,
    register_tag,
    search_tags,
)
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

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

    reader / register service はユーザー DB 未初期化時に例外を投げ得るため遅延初期化する。
    起動順序の都合で初回が失敗しても、後で DB が初期化されれば回復できるよう、
    **成功するまで初期化を再試行**する（失敗はキャッシュしない）。warning は1回だけ出す。
    DB I/O 失敗時は graceful degradation（search→空リスト、register→no-op）。
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
        self._register_service = register_service
        # 初期化失敗の warning を一度だけ出すためのフラグ（毎キーストロークの spam 防止）。
        self._reader_warned = False
        self._register_warned = False

    # ------------------------------------------------------------------
    # Public API（#948 が依存する契約）
    # ------------------------------------------------------------------

    def search(self, prefix: str) -> list[VocabEntry]:
        """prefix に前方/部分一致する trigger 語彙を freq 降順で返す。

        ユーザー DB のみを読むため、base / danbooru の canonical タグは候補に
        混ざらない。usage_count を freq として扱い、降順・同数は word 昇順。

        Args:
            prefix: 補完クエリ（リテラル。空文字なら全 trigger 語彙を返す）。

        Returns:
            VocabEntry のリスト（freq 降順・word 昇順、word 重複は初出優先）。
            reader 取得失敗・DB I/O エラー時は空リスト（graceful degradation）。
        """
        reader = self._get_reader()
        if reader is None:
            return []

        request = TagSearchRequest(
            query=prefix.strip(),
            partial=True,
            format_names=[_TRIGGER_FORMAT],
            resolve_preferred=False,
            include_aliases=False,
            include_deprecated=False,
        )
        try:
            result = search_tags(reader, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"trigger 語彙検索に失敗（縮退、空リストで継続）: {e}")
            return []

        # word はリテラル（source_tag）優先、無ければ tag（こちらもリテラル）。
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
        """trigger word をユーザー DB の専用 format にリテラルとして登録する。

        正規化せず、入力リテラルを ``tag`` / ``source_tag`` の両方に格納する
        （literal trigger 契約。異なるリテラルが正規化衝突で畳まれるのを防ぐ）。
        既存なら冪等（lib 側で同一 tag は created=False）。

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

        request = TagRegisterRequest(
            tag=literal,
            source_tag=literal,
            format_name=_TRIGGER_FORMAT,
            type_name=_TRIGGER_TYPE,
            scope="user",
        )
        try:
            result = register_tag(service, request)
        except (ValueError, RuntimeError, SQLAlchemyError) as e:
            logger.warning(f"trigger 語彙登録に失敗（縮退、no-op で継続）: {e}")
            return
        logger.debug(
            f"trigger 語彙を登録: word={literal!r} created={result.created} tag_id={result.tag_id}"
        )

    # ------------------------------------------------------------------
    # 遅延初期化（成功するまで再試行 / graceful degradation）
    # ------------------------------------------------------------------

    def _get_reader(self) -> object | None:
        """ユーザー DB reader を遅延生成して返す。

        成功するまで再試行する（失敗をキャッシュしない）ので、起動順序で初回が
        失敗しても後から DB が初期化されれば回復する。失敗 warning は1回だけ。
        """
        if self._reader is not None:
            return self._reader
        try:
            self._reader = get_user_tag_reader()
        except (RuntimeError, ValueError, SQLAlchemyError) as e:
            if not self._reader_warned:
                logger.warning(f"ユーザー DB reader 初期化に失敗（trigger 補完を一時無効化）: {e}")
                self._reader_warned = True
            return None
        return self._reader

    def _get_register_service(self) -> object | None:
        """タグ登録サービスを遅延生成して返す。

        reader と同様、成功するまで再試行する。失敗 warning は1回だけ。
        """
        if self._register_service is not None:
            return self._register_service
        try:
            self._register_service = create_tag_register_service()
        except (RuntimeError, ValueError, SQLAlchemyError) as e:
            if not self._register_warned:
                logger.warning(f"タグ登録サービス初期化に失敗（trigger 登録を一時無効化）: {e}")
                self._register_warned = True
            return None
        return self._register_service
