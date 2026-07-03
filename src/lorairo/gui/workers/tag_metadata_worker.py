# src/lorairo/gui/workers/tag_metadata_worker.py
"""詳細パネル表示用のタグ付随メタデータ (翻訳/使用頻度/type) を非同期解決する worker (#1046)。

従来は `SelectedImageDetailsWidget._build_image_details_from_metadata` が GUI スレッドで
`get_translations_batch` / `get_usage_counts_batch` / type 解決 (`search_tags_batch`) を
同期実行しており、tag DB (SQLite) が他スレッド/他プロセスのアクセスで渋滞していると
メインスレッドがその後ろに並んで GUI が応答停止した (#1024 推定原因1、実測56秒)。

本 worker は 3 クエリを background で解決し、結果を Signal で返す。表示は
「即時 (原文のみ) → worker 完了で翻訳/counts/type 反映」の2段階描画になる。
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from ...utils.language_keys import language_alias_keys
from ...utils.log import logger
from .base import LoRAIroWorkerBase


@dataclass
class TagMetadataResult:
    """タグ付随メタデータの解決結果。

    Attributes:
        image_id: 解決対象だった画像 ID (受信側のレース照合用)。
        generation: 起動時の世代番号 (A→B→A 再選択でも古い結果を弾く)。
        translations: ``{tag_id: {language: translation}}``。
        usage_counts: ``{tag_id: {format_name: count}}`` (#990)。
        tag_types: ``{canonical: type名(小文字)}`` (#1056)。
    """

    image_id: int
    generation: int
    translations: dict[int, dict[str, str]] = field(default_factory=dict)
    usage_counts: dict[int, dict[str, int]] = field(default_factory=dict)
    tag_types: dict[str, str] = field(default_factory=dict)


def _extract_type_name(item: Any) -> str | None:
    """TagRecordPublic から type 名 (小文字) を取り出す (#1056)。

    format 非依存検索では ``type_name`` が空になり、format ごとの type は
    ``format_statuses`` 側に入る。ユーザーの type 修正は LoRAIro user format へ
    書かれるため danbooru より優先し、手動追加初期値の "unknown" は採用しない。
    """
    if item.type_name:
        return str(item.type_name).lower()
    statuses = item.format_statuses or {}
    for format_name in ("Lorairo", "danbooru"):
        type_name = (statuses.get(format_name) or {}).get("type_name")
        if type_name and str(type_name).lower() != "unknown":
            return str(type_name).lower()
    for status in statuses.values():
        candidate = (status or {}).get("type_name")
        if candidate and str(candidate).lower() != "unknown":
            return str(candidate).lower()
    return None


def resolve_tag_types(reader: Any, canonicals: list[str]) -> dict[str, str]:
    """canonical -> tagdb type 名 (小文字) を batch で解決する (#1056)。

    per-tag ループの N+1 は禁止 (#998)。取得失敗は空 dict (未分類扱い) に落とし、
    呼び出し側の表示を壊さない。
    """
    unique = list(dict.fromkeys(c for c in canonicals if c))
    if not unique or reader is None:
        return {}
    from genai_tag_db_tools import search_tags_batch

    try:
        batch = search_tags_batch(reader, unique, format_names=None, resolve_preferred=False)
    except (SQLAlchemyError, ValueError, RuntimeError) as e:
        logger.warning(f"タグ type の batch 解決に失敗 (未分類として表示): {e}")
        return {}
    tag_types: dict[str, str] = {}
    for query, result in batch.items():
        query_key = query.casefold()
        for item in result.items:
            tag_match = (item.tag or "").casefold() == query_key
            source_match = (item.source_tag or "").casefold() == query_key
            if not tag_match and not source_match:
                continue
            type_name = _extract_type_name(item)
            if type_name:
                tag_types[query] = type_name
                break
    return tag_types


class TagMetadataWorker(LoRAIroWorkerBase[TagMetadataResult]):
    """タグ付随メタデータ (翻訳/使用頻度/type) を非同期解決するワーカー (#1046)。"""

    _OPERATION_TYPE = "tag_metadata"

    def __init__(
        self,
        reader: Any,
        image_id: int,
        tags_list: list[dict[str, Any]],
        generation: int = 0,
    ) -> None:
        """TagMetadataWorker を初期化する。

        Args:
            reader: MergedTagReader (tag DB リーダー)。
            image_id: 表示対象の画像 ID (レース照合用)。
            tags_list: Repository 層形式のタグ行 (``tag`` / ``tag_id`` キーを使う)。
            generation: 起動世代 (受信側のレース照合用)。
        """
        super().__init__()
        self._reader = reader
        self._image_id = image_id
        self._tags_list = list(tags_list)
        self._generation = generation

    def _apply_preferred_translations(
        self, valid_tag_ids: list[int], translations: dict[int, dict[str, str]]
    ) -> None:
        """主訳 (優先翻訳) を畳み込み済み翻訳へ上書き適用する (#1084)。

        ユーザーが選んだ言語別の主訳を、DB 行順の後勝ちで決まる従来訳より優先させる。
        preference は "ja"/"en" 正規化キーで保存されるが、既存 DB 行の翻訳は
        "japanese"/"ja" 混在なので、当該言語の全エイリアスキーを上書きしないと表示側
        (`_translation_for_language`) がエイリアス順で古い訳を拾ってしまう。よって
        `language_alias_keys` の全キーへ主訳を書き込む。

        preference は advisory: 取得に失敗 (SQLAlchemyError 等) しても preference なしで
        続行し、従来の畳み込み結果をそのまま使う。

        Args:
            valid_tag_ids: 主訳を問い合わせる tag_id リスト。
            translations: 畳み込み済みの ``{tag_id: {language: translation}}`` (in-place 更新)。
        """
        try:
            preferred = self._reader.get_preferred_translations_batch(valid_tag_ids)
        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            logger.warning(f"主訳の取得に失敗 (優先適用をスキップ): {e}")
            return
        for tag_id, prefs in preferred.items():
            bucket = translations.setdefault(tag_id, {})
            for language, translation in prefs.items():
                if not translation:
                    continue
                # 当該言語の全エイリアスキーへ主訳を書き込み、表示側が古い訳を拾わないようにする。
                for key in language_alias_keys(language):
                    bucket[key] = translation

    def execute(self) -> TagMetadataResult:
        """3 つの batch クエリを実行し TagMetadataResult を返す。

        クエリの合間で協調キャンセルを効かせる (#1024 と同型)。
        """
        valid_tag_ids = [
            tag_dict["tag_id"]
            for tag_dict in self._tags_list
            if isinstance(tag_dict, dict) and tag_dict.get("tag_id") is not None
        ]
        canonicals = [
            str(tag_dict["tag"])
            for tag_dict in self._tags_list
            if isinstance(tag_dict, dict) and tag_dict.get("tag")
        ]

        translations: dict[int, dict[str, str]] = {}
        usage_counts: dict[int, dict[str, int]] = {}
        if valid_tag_ids:
            for tag_id, trs in self._reader.get_translations_batch(valid_tag_ids).items():
                for tr in trs:
                    if tr.language and tr.translation:
                        translations.setdefault(tag_id, {})[tr.language] = tr.translation
            self._check_cancellation()
            self._apply_preferred_translations(valid_tag_ids, translations)
            self._check_cancellation()
            # format 名解決は format_map の 1 回参照のみで N+1 にならない (#990)
            format_map = self._reader.get_format_map()
            for tag_id, counts_by_fid in self._reader.get_usage_counts_batch(valid_tag_ids).items():
                named = {
                    format_map[fid]: count for fid, count in counts_by_fid.items() if fid in format_map
                }
                if named:
                    usage_counts[tag_id] = named
            self._check_cancellation()

        tag_types = resolve_tag_types(self._reader, canonicals)

        logger.debug(
            f"tag metadata worker 完了: image_id={self._image_id}, gen={self._generation}, "
            f"translations={len(translations)}, counts={len(usage_counts)}, types={len(tag_types)}"
        )
        return TagMetadataResult(
            image_id=self._image_id,
            generation=self._generation,
            translations=translations,
            usage_counts=usage_counts,
            tag_types=tag_types,
        )
