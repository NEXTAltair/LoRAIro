"""2 枚の画像の現在の注釈を比べる (Issue #1399 / #1484, Qt-free)。

比較画面 (``gui/widgets/image_comparison_dialog.py``) の差分計算と左右の選択状態を持つ。
DB は読むだけで、タグや採用状態は変更しない。

- タグは左右の集合差分 (共通 / 左だけ / 右だけ) を、それぞれの元の並びで返す。
- キャプションは原文を整形せずにトークン単位の差分を返す。各差分区間の左側を連結すると
  左の原文、右側を連結すると右の原文に戻る。
- 片側に情報が無いとき (タグ 0 件・キャプション未登録・画像が見つからない) は比較せず、
  ``Availability`` で欠けている側を返す。空と空を「同じ」とは言わない。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import PurePath
from typing import Any, Protocol


class Side(StrEnum):
    """比較の左右。"""

    LEFT = "left"
    RIGHT = "right"

    @property
    def other(self) -> Side:
        """反対側。"""
        return Side.RIGHT if self is Side.LEFT else Side.LEFT


class Availability(StrEnum):
    """比較項目が左右のどちらにあるか。"""

    BOTH = "both"
    LEFT_MISSING = "left_missing"
    RIGHT_MISSING = "right_missing"
    BOTH_MISSING = "both_missing"


def _availability(has_left: bool, has_right: bool) -> Availability:
    if has_left and has_right:
        return Availability.BOTH
    if has_right:
        return Availability.LEFT_MISSING
    if has_left:
        return Availability.RIGHT_MISSING
    return Availability.BOTH_MISSING


class DiffKind(StrEnum):
    """キャプション差分の区間の種類。"""

    EQUAL = "equal"
    DELETE = "delete"
    INSERT = "insert"
    REPLACE = "replace"


@dataclass(frozen=True)
class TagDiff:
    """タグの集合差分。``availability`` が BOTH 以外のときは各タプルが空になる。"""

    availability: Availability
    common: tuple[str, ...] = ()
    left_only: tuple[str, ...] = ()
    right_only: tuple[str, ...] = ()

    @property
    def identical(self) -> bool:
        """両側にタグがあり、集合が一致するか。"""
        return self.availability is Availability.BOTH and not self.left_only and not self.right_only


@dataclass(frozen=True)
class DiffSegment:
    """キャプション差分の 1 区間。``left`` / ``right`` は原文の部分文字列。"""

    kind: DiffKind
    left: str
    right: str


@dataclass(frozen=True)
class CaptionDiff:
    """キャプションのテキスト差分。``availability`` が BOTH のときだけ ``segments`` を持つ。"""

    availability: Availability
    segments: tuple[DiffSegment, ...] = ()

    @property
    def identical(self) -> bool:
        """両側にキャプションがあり、原文が一致するか。"""
        return self.availability is Availability.BOTH and all(
            seg.kind is DiffKind.EQUAL for seg in self.segments
        )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def diff_tags(left: list[str] | tuple[str, ...], right: list[str] | tuple[str, ...]) -> TagDiff:
    """左右のタグを共通 / 左だけ / 右だけに分ける。

    タグは原文のまま (大文字小文字も区別して) 比べる。重複は 1 つにまとめる。

    Args:
        left: 左の画像のタグ。
        right: 右の画像のタグ。

    Returns:
        片側のタグが 0 件なら比較せず、欠けている側を示す ``TagDiff``。
    """
    left_tags = _unique(list(left))
    right_tags = _unique(list(right))
    availability = _availability(bool(left_tags), bool(right_tags))
    if availability is not Availability.BOTH:
        return TagDiff(availability=availability)
    right_set = set(right_tags)
    left_set = set(left_tags)
    return TagDiff(
        availability=availability,
        common=tuple(t for t in left_tags if t in right_set),
        left_only=tuple(t for t in left_tags if t not in right_set),
        right_only=tuple(t for t in right_tags if t not in left_set),
    )


# ASCII の語・空白の連続はまとめ、それ以外 (日本語・記号) は 1 文字ずつに分ける。
# どの文字もちょうど 1 つのトークンに入るため、連結すると原文に戻る。
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|\s+|.", re.DOTALL)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text)


def _normalize_caption(text: str | None) -> str | None:
    return text if text else None


def diff_caption(left: str | None, right: str | None) -> CaptionDiff:
    """キャプションの原文どうしのテキスト差分を返す。

    改行や空白も整形せずに比べる。``None`` と空文字は「キャプション未登録」として扱う。

    Args:
        left: 左の画像のキャプション。
        right: 右の画像のキャプション。

    Returns:
        片側が未登録なら比較せず、欠けている側を示す ``CaptionDiff``。
    """
    left_text = _normalize_caption(left)
    right_text = _normalize_caption(right)
    availability = _availability(left_text is not None, right_text is not None)
    if left_text is None or right_text is None:
        return CaptionDiff(availability=availability)

    left_tokens = _tokenize(left_text)
    right_tokens = _tokenize(right_text)
    matcher = SequenceMatcher(a=left_tokens, b=right_tokens, autojunk=False)
    segments: list[DiffSegment] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        segments.append(
            DiffSegment(
                kind=DiffKind(tag),
                left="".join(left_tokens[i1:i2]),
                right="".join(right_tokens[j1:j2]),
            )
        )
    return CaptionDiff(availability=availability, segments=tuple(segments))


@dataclass(frozen=True)
class ComparisonTag:
    """比較用のタグ 1 件と、その出所 (``モデル名 (AI)`` / ``手動`` 等)。"""

    tag: str
    origins: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonSnapshot:
    """比較の片側に表示する、画像 1 枚の現在の注釈。

    Attributes:
        image_id: 画像 ID。
        found: DB に画像が見つかったか。
        stored_image_path: 表示に使う保存先パス (DB の値のまま)。
        original_file_name: 登録元のファイル名。
        image_size: (幅, 高さ)。不明なら None。
        tags: 採用中のタグ (重複をまとめた並び順)。0 件なら空。
        caption: 採用中の最新キャプション。未登録なら None。
        caption_origin: キャプションの出所。未登録なら None。
    """

    image_id: int
    found: bool
    stored_image_path: str | None = None
    original_file_name: str = ""
    image_size: tuple[int, int] | None = None
    tags: tuple[ComparisonTag, ...] = ()
    caption: str | None = None
    caption_origin: str | None = None
    _tag_origin_counts: tuple[tuple[str, int], ...] = field(default=(), repr=False)

    @property
    def tag_names(self) -> tuple[str, ...]:
        """タグ名の並び。"""
        return tuple(t.tag for t in self.tags)

    def provenance_lines(self) -> list[str]:
        """表示中の情報の出所を、人が読む行の並びで返す。"""
        if not self.found:
            return [f"画像 ID: {self.image_id}", "DB に画像が見つかりません"]
        lines = [f"画像 ID: {self.image_id}"]
        if self.original_file_name:
            lines.append(f"ファイル: {self.original_file_name}")
        if self.stored_image_path:
            lines.append(f"保存先: {self.stored_image_path}")
        if self.image_size is not None:
            lines.append(f"解像度: {self.image_size[0]} × {self.image_size[1]} px")
        if self.tags:
            sources = ", ".join(f"{origin} ×{count}" for origin, count in self._tag_origin_counts)
            lines.append(f"タグ: {len(self.tags)} 件 ({sources})")
        else:
            lines.append("タグ: なし")
        if self.caption is not None:
            lines.append(f"キャプション: {self.caption_origin or '出所不明'}")
        else:
            lines.append("キャプション: なし")
        return lines


def _origin_label(annotation: dict[str, Any]) -> str:
    """タグ / キャプション 1 件の出所の表示名。"""
    model_name = annotation.get("model_name")
    has_model = bool(model_name) and model_name != "Unknown"
    manual = bool(annotation.get("is_edited_manually")) or annotation.get("source") == "Manual"
    if has_model:
        return f"{model_name} ({'手動編集' if manual else 'AI'})"
    return "手動" if manual else "出所不明"


def _caption_entry(metadata: dict[str, Any]) -> tuple[str | None, str | None]:
    """表示する最新キャプションと出所を返す (詳細ペインと同じく created_at 最新を採る)。"""
    captions = [c for c in metadata.get("captions") or [] if isinstance(c, dict) and c.get("caption")]
    if captions:
        latest = max(captions, key=lambda c: c.get("created_at") or datetime.min)
        return str(latest["caption"]), _origin_label(latest)
    caption_text = metadata.get("caption_text")
    if caption_text:
        return str(caption_text), None
    return None, None


def snapshot_from_metadata(image_id: int, metadata: dict[str, Any] | None) -> ComparisonSnapshot:
    """``ImageRepository.get_image_metadata`` の辞書から比較用スナップショットを作る。

    Args:
        image_id: 要求した画像 ID。
        metadata: 画像メタデータ。画像が見つからなければ None。

    Returns:
        比較の片側に表示するスナップショット。
    """
    if metadata is None:
        return ComparisonSnapshot(image_id=image_id, found=False)

    origins_by_tag: dict[str, list[str]] = {}
    origin_counter: Counter[str] = Counter()
    for entry in metadata.get("tags") or []:
        if not isinstance(entry, dict) or not entry.get("tag"):
            continue
        tag = str(entry["tag"])
        origin = _origin_label(entry)
        origin_counter[origin] += 1
        origins = origins_by_tag.setdefault(tag, [])
        if origin not in origins:
            origins.append(origin)

    caption, caption_origin = _caption_entry(metadata)
    width = metadata.get("width")
    height = metadata.get("height")
    image_size = (int(width), int(height)) if width and height else None
    original_path = metadata.get("original_image_path") or ""
    stored_path = metadata.get("stored_image_path")

    return ComparisonSnapshot(
        image_id=image_id,
        found=True,
        stored_image_path=str(stored_path) if stored_path else None,
        original_file_name=PurePath(str(original_path)).name if original_path else "",
        image_size=image_size,
        tags=tuple(ComparisonTag(tag=t, origins=tuple(o)) for t, o in origins_by_tag.items()),
        caption=caption,
        caption_origin=caption_origin,
        _tag_origin_counts=tuple(origin_counter.most_common()),
    )


@dataclass(frozen=True)
class ComparisonResult:
    """左右の比較結果。"""

    left_id: int
    right_id: int
    tags: TagDiff
    caption: CaptionDiff


def compare_snapshots(left: ComparisonSnapshot, right: ComparisonSnapshot) -> ComparisonResult:
    """左右のスナップショットのタグとキャプションを比べる。"""
    return ComparisonResult(
        left_id=left.image_id,
        right_id=right.image_id,
        tags=diff_tags(left.tag_names, right.tag_names),
        caption=diff_caption(left.caption, right.caption),
    )


class ImageMetadataSource(Protocol):
    """画像メタデータの取得元 (``ImageDatabaseManager`` が満たす)。"""

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """画像 1 枚のメタデータ。見つからなければ None。"""
        ...


class ImageComparisonService:
    """比較画面のための読み取り専用サービス。"""

    def __init__(self, source: ImageMetadataSource) -> None:
        """取得元を受け取る。

        Args:
            source: 画像メタデータの取得元。
        """
        self._source = source

    def load_snapshot(self, image_id: int) -> ComparisonSnapshot:
        """画像 1 枚の現在の注釈を読む (書き込みはしない)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播する。
        """
        return snapshot_from_metadata(image_id, self._source.get_image_metadata(image_id))


class ComparisonSelection:
    """比較の左右に表示する画像と、片側固定の状態。

    候補は重複を除いた順序付きの画像 ID。左右に同じ画像は置かない。
    """

    def __init__(self, candidates: list[int]) -> None:
        """候補の先頭 2 枚を左右に置く。

        Raises:
            ValueError: 重複を除いた候補が 2 枚未満のとき。
        """
        unique = tuple(dict.fromkeys(candidates))
        if len(unique) < 2:
            raise ValueError("比較には異なる画像が 2 枚以上必要です")
        self._candidates = unique
        self._ids: dict[Side, int] = {Side.LEFT: unique[0], Side.RIGHT: unique[1]}
        self._pinned: dict[Side, bool] = {Side.LEFT: False, Side.RIGHT: False}

    @property
    def candidates(self) -> tuple[int, ...]:
        """候補の画像 ID。"""
        return self._candidates

    @property
    def left_id(self) -> int:
        """左の画像 ID。"""
        return self._ids[Side.LEFT]

    @property
    def right_id(self) -> int:
        """右の画像 ID。"""
        return self._ids[Side.RIGHT]

    def image_id(self, side: Side) -> int:
        """指定した側の画像 ID。"""
        return self._ids[side]

    def is_pinned(self, side: Side) -> bool:
        """指定した側が固定されているか。"""
        return self._pinned[side]

    def set_pinned(self, side: Side, pinned: bool) -> None:
        """指定した側の固定を切り替える。"""
        self._pinned[side] = pinned

    def swap(self) -> None:
        """左右を入れ替える。固定は画像と一緒に移る。"""
        self._ids[Side.LEFT], self._ids[Side.RIGHT] = self._ids[Side.RIGHT], self._ids[Side.LEFT]
        self._pinned[Side.LEFT], self._pinned[Side.RIGHT] = (
            self._pinned[Side.RIGHT],
            self._pinned[Side.LEFT],
        )

    def set_side(self, side: Side, image_id: int) -> bool:
        """指定した側の画像を変える。

        Returns:
            変えたら True。固定中・候補外・反対側と同じ画像のときは False。
        """
        if self._pinned[side] or image_id not in self._candidates:
            return False
        if image_id == self._ids[side.other]:
            return False
        changed = self._ids[side] != image_id
        self._ids[side] = image_id
        return changed

    def step(self, side: Side, delta: int) -> bool:
        """指定した側を候補の前後に送る (反対側の画像は飛ばし、端で一周する)。

        Returns:
            変えたら True。固定中や他に候補が無いときは False。
        """
        if self._pinned[side] or delta == 0:
            return False
        count = len(self._candidates)
        index = self._candidates.index(self._ids[side])
        direction = 1 if delta > 0 else -1
        for offset in range(1, count):
            candidate = self._candidates[(index + direction * offset) % count]
            if candidate != self._ids[side.other]:
                self._ids[side] = candidate
                return True
        return False
