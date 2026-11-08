"""provider が返す矩形からクロップ画像を一括作成するサービス (Issue #1340 / ADR 0103)。

矩形の出所は :class:`~lorairo.domain.crop_rect_provider.CropRectProvider` に任せ、本モジュールは
「1 矩形 = 1 結果」の一括処理・部分失敗・再実行の契約だけを持つ。1 件の作成は
:func:`lorairo.services.crop_service.create_crop_image` をそのまま再利用する。

- 候補ごとに独立して処理し、失敗しても残りを続ける (結果は ``failed`` と理由)。
- 同じ親・矩形・由来の ``crop_relations`` が既にあれば ``skipped`` (``already_exists``)。
  切り出し結果が既存画像の pHash 重複なら ``skipped`` (``duplicate_image``)。
- ``dry_run`` では DB とファイル保存先へ書き込まず、範囲検証と重複判定 (pHash 重複を含む) だけを行う。
- DB 例外 (SQLAlchemyError) は個別の失敗にせず呼び出し元へ伝播させる (継続しても全件失敗するため)。

``PySide6`` / ``lorairo.gui`` は import しない。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.domain.crop_rect_provider import CropRectCandidate, CropRectProvider
from lorairo.domain.crop_request import CropCreateRequest
from lorairo.filesystem import FileSystemManager
from lorairo.public_api.exceptions import DuplicateImageError
from lorairo.services.crop_service import (
    CropSourceInfo,
    create_crop_image,
    find_duplicate_crop,
    get_crop_source_info,
    validate_crop_rect,
)

CropBatchStatus = Literal["created", "would_create", "skipped", "failed"]
CropBatchReason = Literal[
    "already_exists",
    "duplicate_image",
    "invalid_rect",
    "parent_not_found",
    "io_error",
    "registration_failed",
]

_RelationKey = tuple[int, int, int, int, str]


@dataclass(frozen=True, slots=True)
class CropBatchOutcome:
    """1 矩形候補の処理結果。

    Attributes:
        status: ``created`` / ``would_create`` (dry-run) / ``skipped`` / ``failed``。
        parent_image_id: 親画像 ID。
        candidate: 処理した矩形候補 (行番号・由来・スコアを含む)。
        child_image_id: 作成した子画像 ID。skipped では既存の子 (重複先) の ID。
        reason: skipped / failed の理由コード。
        message: 理由の詳細 (人間向け)。
    """

    status: CropBatchStatus
    parent_image_id: int
    candidate: CropRectCandidate
    child_image_id: int | None = None
    reason: CropBatchReason | None = None
    message: str | None = None

    @property
    def line(self) -> int | None:
        """候補の入力行番号 (検出器由来なら None)。"""
        return self.candidate.line


def run_crop_batch(
    provider: CropRectProvider,
    parent_image_ids: Iterable[int],
    *,
    db_manager: ImageDatabaseManager,
    fsm: FileSystemManager,
    dry_run: bool = False,
    on_outcome: Callable[[CropBatchOutcome], None] | None = None,
) -> list[CropBatchOutcome]:
    """親画像ごとに provider の候補を取り、クロップ画像を一括作成する。

    タグとレーティングは ``images crop`` の既定と同じく親からコピーする。

    Args:
        provider: 矩形候補の供給元。
        parent_image_ids: 処理する親画像 ID (この順に処理する)。
        db_manager: 画像 DB マネージャー。
        fsm: ファイル保存先を握る FileSystemManager (``initialize`` 済み)。
        dry_run: True なら書き込まず検証だけ行う。
        on_outcome: 結果を 1 件ずつ受け取るコールバック (逐次出力用)。

    Returns:
        処理順の結果リスト。

    Raises:
        SQLAlchemyError: DB 操作に失敗した場合 (それまでに作成した子画像は残る)。
    """
    outcomes: list[CropBatchOutcome] = []

    def record(outcome: CropBatchOutcome) -> None:
        outcomes.append(outcome)
        if on_outcome is not None:
            on_outcome(outcome)

    for parent_id in parent_image_ids:
        candidates = provider.candidates_for(parent_id)
        if not candidates:
            continue
        source = _load_source(parent_id, candidates, db_manager, record)
        if source is None:
            continue
        existing: dict[_RelationKey, int | None] = {
            (rel.x, rel.y, rel.width, rel.height, rel.origin): rel.child_image_id
            for rel in db_manager.get_crop_children(parent_id)
        }
        for candidate in candidates:
            record(_process_candidate(parent_id, candidate, source, existing, db_manager, fsm, dry_run))

    _log_summary(outcomes, dry_run)
    return outcomes


def _load_source(
    parent_id: int,
    candidates: Iterable[CropRectCandidate],
    db_manager: ImageDatabaseManager,
    record: Callable[[CropBatchOutcome], None],
) -> CropSourceInfo | None:
    """親画像情報を取得する。取れなければ全候補を failed として記録し None を返す。"""
    reason: CropBatchReason
    try:
        return get_crop_source_info(parent_id, db_manager=db_manager)
    except ValueError as exc:
        reason, message = "parent_not_found", str(exc)
    except OSError as exc:
        reason, message = "io_error", f"Cannot read parent image: {exc.strerror or exc}"
    for candidate in candidates:
        record(CropBatchOutcome("failed", parent_id, candidate, reason=reason, message=message))
    return None


def _process_candidate(
    parent_id: int,
    candidate: CropRectCandidate,
    source: CropSourceInfo,
    existing: dict[_RelationKey, int | None],
    db_manager: ImageDatabaseManager,
    fsm: FileSystemManager,
    dry_run: bool,
) -> CropBatchOutcome:
    """1 候補を検証・作成する。``existing`` は作成/予定の分だけ更新する。"""
    rect = candidate.rect
    key: _RelationKey = (rect.x, rect.y, rect.width, rect.height, candidate.origin)
    if key in existing:
        return CropBatchOutcome(
            "skipped",
            parent_id,
            candidate,
            child_image_id=existing[key],
            reason="already_exists",
            message="Same parent, rectangle and origin already exist",
        )
    try:
        validate_crop_rect(rect, source.width, source.height)
    except ValueError as exc:
        return CropBatchOutcome("failed", parent_id, candidate, reason="invalid_rect", message=str(exc))
    if dry_run:
        return _preview_candidate(parent_id, candidate, source, existing, db_manager)

    request = CropCreateRequest(
        parent_image_id=parent_id,
        rect=rect,
        tags=source.candidate_tags,
        rating=source.rating,
        origin=candidate.origin,
    )
    try:
        child_id = create_crop_image(request, db_manager=db_manager, fsm=fsm)
    except DuplicateImageError as exc:
        return CropBatchOutcome(
            "skipped",
            parent_id,
            candidate,
            child_image_id=exc.existing_id,
            reason="duplicate_image",
            message=f"Cropped pixels duplicate existing image_id={exc.existing_id}",
        )
    except ValueError as exc:
        return CropBatchOutcome("failed", parent_id, candidate, reason="invalid_rect", message=str(exc))
    except OSError as exc:
        return CropBatchOutcome(
            "failed", parent_id, candidate, reason="io_error", message=f"I/O error: {exc.strerror or exc}"
        )
    except RuntimeError as exc:
        return CropBatchOutcome(
            "failed", parent_id, candidate, reason="registration_failed", message=str(exc)
        )
    existing[key] = child_id
    return CropBatchOutcome("created", parent_id, candidate, child_image_id=child_id)


def _preview_candidate(
    parent_id: int,
    candidate: CropRectCandidate,
    source: CropSourceInfo,
    existing: dict[_RelationKey, int | None],
    db_manager: ImageDatabaseManager,
) -> CropBatchOutcome:
    """dry-run: 書き込まずに実行時と同じ ``would_create`` / ``skipped (duplicate_image)`` を判定する。

    既存画像との pHash 重複は切り出し結果を一時ファイルで判定する。同じ実行内で先に
    作成予定になった同一矩形 (由来違い) は、実行時に画素が重複するため skipped にする。
    """
    rect = candidate.rect
    same_rect = [
        child_id
        for (x, y, width, height, _origin), child_id in existing.items()
        if (x, y, width, height) == (rect.x, rect.y, rect.width, rect.height)
    ]
    if same_rect:
        return CropBatchOutcome(
            "skipped",
            parent_id,
            candidate,
            child_image_id=same_rect[0],
            reason="duplicate_image",
            message="Same rectangle is already created or planned under another origin",
        )
    try:
        duplicate_id = find_duplicate_crop(rect, source.image_path, db_manager=db_manager)
    except OSError as exc:
        return CropBatchOutcome(
            "failed", parent_id, candidate, reason="io_error", message=f"I/O error: {exc.strerror or exc}"
        )
    if duplicate_id is not None:
        return CropBatchOutcome(
            "skipped",
            parent_id,
            candidate,
            child_image_id=duplicate_id,
            reason="duplicate_image",
            message=f"Cropped pixels duplicate existing image_id={duplicate_id}",
        )
    existing[(rect.x, rect.y, rect.width, rect.height, candidate.origin)] = None
    return CropBatchOutcome("would_create", parent_id, candidate)


def _log_summary(outcomes: list[CropBatchOutcome], dry_run: bool) -> None:
    """一括処理のサマリーを INFO で 1 行だけ出す。"""
    counts = dict.fromkeys(("created", "would_create", "skipped", "failed"), 0)
    for outcome in outcomes:
        counts[outcome.status] += 1
    logger.info(
        "クロップ一括作成{}: 作成={}, 作成予定={}, スキップ={}, 失敗={}",
        " (dry-run)" if dry_run else "",
        counts["created"],
        counts["would_create"],
        counts["skipped"],
        counts["failed"],
    )
