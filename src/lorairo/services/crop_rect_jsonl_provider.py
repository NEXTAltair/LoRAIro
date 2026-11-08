"""外部で用意した矩形 JSONL を読む CropRectProvider 実装 (Issue #1340 / ADR 0103)。

1 行 = 1 矩形の JSON object::

    {"image_id": 42, "x": 10, "y": 20, "width": 512, "height": 512, "origin": "yolo", "score": 0.9}

``image_id`` / ``x`` / ``y`` / ``width`` / ``height`` は必須の整数、``origin`` (空文字不可) と
``score`` (有限の数値) は任意。未知のキーは誤記の検出のため拒否する。空行は無視する。
不正な行は処理全体を止めず、行番号付きの :class:`CropRectLineError` として保持する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from lorairo.domain.crop_rect_provider import CropRectCandidate
from lorairo.domain.crop_request import CropRect
from lorairo.public_api.exceptions import ResultSetTooLargeError


@dataclass(frozen=True, slots=True)
class CropRectLineError:
    """JSONL の 1 行を矩形として解釈できなかったことを表す。

    Attributes:
        line: 1 始まりの行番号。
        message: 不正内容 (人間・エージェント向け)。
        image_id: 行から読み取れた親画像 ID。読めなければ None。
    """

    line: int
    message: str
    image_id: int | None = None


class _CropRectRow(BaseModel):
    """JSONL 1 行のスキーマ。型変換はせず (strict)、未知キーは拒否する。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    image_id: int = Field(ge=1)
    x: int
    y: int
    width: int
    height: int
    origin: str | None = Field(default=None, min_length=1)
    score: float | None = Field(default=None, allow_inf_nan=False)


class JsonlCropRectProvider:
    """JSONL ファイルの矩形を親画像 ID ごとに返す provider。"""

    def __init__(
        self,
        candidates: dict[int, tuple[CropRectCandidate, ...]],
        line_errors: tuple[CropRectLineError, ...],
        row_count: int,
    ) -> None:
        self._candidates = candidates
        self.line_errors = line_errors
        self.row_count = row_count

    @property
    def parent_image_ids(self) -> tuple[int, ...]:
        """候補を持つ親画像 ID (ファイル内の初出順)。"""
        return tuple(self._candidates)

    def candidates_for(self, parent_image_id: int) -> tuple[CropRectCandidate, ...]:
        """親画像 1 枚分の候補を行順で返す。"""
        return self._candidates.get(parent_image_id, ())

    @classmethod
    def from_path(cls, path: Path, *, default_origin: str, max_rows: int) -> JsonlCropRectProvider:
        """JSONL ファイルを読み込む。

        行数 (空行を除く) を先に数え、``max_rows`` を超えれば解釈せずに拒否する
        (count-first、ADR 0060)。

        Args:
            path: JSONL ファイル。
            default_origin: ``origin`` を省略した行に使う由来。
            max_rows: 1 回で受け付ける最大行数。

        Returns:
            読み込んだ provider。

        Raises:
            ResultSetTooLargeError: 行数が ``max_rows`` を超えた場合。
            OSError: ファイルを読めない場合。
            UnicodeDecodeError: UTF-8 として読めない場合。
        """
        rows = [
            (number, text)
            for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if text.strip()
        ]
        if len(rows) > max_rows:
            raise ResultSetTooLargeError(len(rows), max_rows)

        grouped: dict[int, list[CropRectCandidate]] = {}
        errors: list[CropRectLineError] = []
        for number, text in rows:
            parsed = _parse_row(number, text, default_origin)
            if isinstance(parsed, CropRectLineError):
                errors.append(parsed)
                continue
            image_id, candidate = parsed
            grouped.setdefault(image_id, []).append(candidate)
        return cls(
            {image_id: tuple(items) for image_id, items in grouped.items()},
            tuple(errors),
            len(rows),
        )


def _parse_row(
    number: int, text: str, default_origin: str
) -> tuple[int, CropRectCandidate] | CropRectLineError:
    """1 行を解釈する。不正なら行番号付きのエラーを返す。"""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return CropRectLineError(number, f"invalid JSON: {exc.msg} (column {exc.colno})")
    if not isinstance(raw, dict):
        return CropRectLineError(number, "each line must be a JSON object")
    raw_id = raw.get("image_id")
    image_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else None
    try:
        row = _CropRectRow.model_validate(raw)
    except PydanticValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'row'}: {error['msg']}"
            for error in exc.errors()
        )
        return CropRectLineError(number, f"invalid row: {details}", image_id)
    candidate = CropRectCandidate(
        rect=CropRect(x=row.x, y=row.y, width=row.width, height=row.height),
        origin=row.origin or default_origin,
        score=row.score,
        line=number,
    )
    return row.image_id, candidate
