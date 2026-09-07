"""クロップ画像 (親画像の一部を切り出した独立画像) を 1 件作成するサービス。

ADR 0092 のデータ層の上に立つ Qt 非依存レイヤー。**矩形の出所を知らない**のが本
モジュールの設計上の要点で、GUI の手動矩形選択 (#1345 / #1346) も物体検出 (#1340) も
:class:`~lorairo.domain.crop_request.CropCreateRequest` を組み立てて同じ関数を呼ぶ。

処理は **1 件単位**に閉じる。複数矩形をまとめて切り出す際の進捗・部分失敗の扱いは
#1340 で設計するため、本モジュールにはバッチ API を置かない。

``PySide6`` / ``lorairo.gui`` は import しない (テストがサブプロセスで検証する)。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from PIL import Image

from lorairo.database.db_core import resolve_stored_path
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import TagAnnotationData
from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.filesystem import FileSystemManager

CANONICAL_RATINGS: frozenset[str] = frozenset({"PG", "PG-13", "R", "X", "XXX"})
"""``normalized_rating`` として許容する Civitai 基準の正準値 (schema.py と同一)。"""

_MANUAL_RATING_SOURCE = "Manual"
"""``get_image_annotations`` の rating 行が手動編集由来であることを示す ``source`` 値。"""

_CROP_TEMP_SUBDIR = "crops"
"""一時ディレクトリ内のサブディレクトリ名。

``FileSystemManager.save_original_image`` は入力ファイルの **親ディレクトリ名**を
保存先のサブディレクトリ名に使うため、ランダムな一時ディレクトリ名がそのまま
``original_images`` 配下に露出しないよう固定名のサブディレクトリを噛ませる。
"""


@dataclass(frozen=True, slots=True)
class CropSourceInfo:
    """クロップ元 (親画像) の GUI 初期表示に必要な情報。

    Attributes:
        image_path: 親画像の実ファイルパス (解決済み)。
        width: 親画像の幅 (px)。
        height: 親画像の高さ (px)。
        candidate_tags: 子へコピーする候補タグ (soft-reject 除外・重複除去・安定順)。
        rating: 親の手動レーティング。未設定なら None。
    """

    image_path: Path
    width: int
    height: int
    candidate_tags: tuple[str, ...]
    rating: str | None


def get_crop_source_info(
    parent_image_id: int,
    *,
    db_manager: ImageDatabaseManager,
) -> CropSourceInfo:
    """クロップ元となる親画像の情報を取得する。

    GUI (#1346) が矩形選択ダイアログの初期状態 (画像・候補タグ・レーティング) を
    組み立てるために使う。DB を読むだけで書き込みは行わない。

    Args:
        parent_image_id: 親となる画像 ID (``images.id``)。
        db_manager: 画像 DB マネージャー。

    Returns:
        親画像のパス・寸法・候補タグ・手動レーティング。

    Raises:
        ValueError: 親画像が存在しない、またはメタデータに寸法が無い場合。
        SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播させる。
    """
    metadata = _require_parent_metadata(parent_image_id, db_manager=db_manager)
    width, height = _parent_size(parent_image_id, metadata)
    annotations = db_manager.get_image_annotations(parent_image_id)
    return CropSourceInfo(
        image_path=resolve_stored_path(str(metadata["stored_image_path"])),
        width=width,
        height=height,
        candidate_tags=_candidate_tags(annotations["tags"]),
        rating=_latest_manual_rating(annotations["ratings"]),
    )


def create_crop_image(
    request: CropCreateRequest,
    *,
    db_manager: ImageDatabaseManager,
    fsm: FileSystemManager,
) -> int:
    """親画像から矩形を切り出し、独立した画像として登録して子画像 ID を返す。

    矩形の出所 (GUI の手動選択か物体検出か) は関知しない。呼び出し側が組み立てた
    request の値をそのまま保存する。1 件単位で完結し、バッチは #1340 の担当。

    処理順は「事前検証 → 切り出し → ファイル保存 → 画像登録 → タグコピー →
    レーティングコピー → 親子関係保存」。事前検証はファイル・DB へ触れる前に
    すべて済ませるため、検証失敗時は副作用が残らない。元画像のファイル・タグ・
    レーティングは一切変更しない。

    Args:
        request: 親画像 ID・切り出し矩形・採用タグ・レーティング・由来。
        db_manager: 画像 DB マネージャー。
        fsm: ファイル保存先を握る FileSystemManager (``initialize`` 済みであること)。

    Returns:
        作成された子画像の ``images.id``。

    Raises:
        ValueError: 親画像が存在しない、矩形の幅/高さが 0 以下、矩形が親画像の
            範囲外、レーティングが正準値外のいずれかの場合。
        RuntimeError: 切り出し画像の登録が成立しなかった場合 (登録失敗、または
            既存画像と重複判定され新規 ID が発行されなかった場合)。
        OSError: 切り出し画像の読み書きに失敗した場合。
        SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播させる。
    """
    metadata = _require_parent_metadata(request.parent_image_id, db_manager=db_manager)
    parent_width, parent_height = _parent_size(request.parent_image_id, metadata)
    _validate_rect(request.rect, parent_width, parent_height)
    _validate_rating(request.rating)

    parent_path = resolve_stored_path(str(metadata["stored_image_path"]))
    child_id = _register_cropped_file(request, parent_path, db_manager=db_manager, fsm=fsm)

    _copy_tags(request, child_id, db_manager=db_manager)
    if request.rating is not None:
        db_manager.annotation_repo.update_manual_rating(child_id, request.rating)

    rect = request.rect
    db_manager.add_crop_relation(
        parent_image_id=request.parent_image_id,
        child_image_id=child_id,
        x=rect.x,
        y=rect.y,
        width=rect.width,
        height=rect.height,
        origin=request.origin,
    )
    logger.debug(
        "クロップ画像を作成: parent_image_id={}, child_image_id={}, "
        "rect=({}, {}, {}, {}), tags={}, origin={}",
        request.parent_image_id,
        child_id,
        rect.x,
        rect.y,
        rect.width,
        rect.height,
        len(request.tags),
        request.origin,
    )
    return child_id


def _require_parent_metadata(
    parent_image_id: int,
    *,
    db_manager: ImageDatabaseManager,
) -> dict[str, Any]:
    """親画像のメタデータを取得する。存在しなければ ValueError。"""
    metadata = db_manager.get_image_metadata(parent_image_id)
    if metadata is None or not metadata.get("stored_image_path"):
        raise ValueError(
            f"Parent image not found: image_id={parent_image_id}\n"
            f"親画像が見つかりません: image_id={parent_image_id}"
        )
    return metadata


def _parent_size(parent_image_id: int, metadata: dict[str, Any]) -> tuple[int, int]:
    """親画像の寸法をメタデータから取り出す。欠落していれば ValueError。"""
    width = metadata.get("width")
    height = metadata.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError(
            f"Parent image has no usable dimensions: image_id={parent_image_id}\n"
            f"親画像の寸法が取得できません: image_id={parent_image_id}"
        )
    return width, height


def _validate_rect(rect: CropRect, parent_width: int, parent_height: int) -> None:
    """矩形の妥当性を検証する (幅/高さ 0 以下・親画像範囲外は ValueError)。"""
    if not rect.has_positive_size():
        raise ValueError(
            f"Crop rectangle must have positive size, got {rect.width}x{rect.height}\n"
            f"クロップ矩形の幅と高さは 1px 以上にしてください (指定: {rect.width}x{rect.height})"
        )
    if not rect.fits_within(parent_width, parent_height):
        raise ValueError(
            f"Crop rectangle ({rect.x}, {rect.y}, {rect.width}, {rect.height}) is outside "
            f"the parent image {parent_width}x{parent_height}\n"
            f"クロップ矩形 ({rect.x}, {rect.y}, {rect.width}, {rect.height}) が"
            f"親画像 {parent_width}x{parent_height} の範囲外です"
        )


def _validate_rating(rating: str | None) -> None:
    """レーティングが正準値かを検証する (None は未設定として許容)。"""
    if rating is None or rating in CANONICAL_RATINGS:
        return
    valid = ", ".join(sorted(CANONICAL_RATINGS))
    raise ValueError(
        f"Invalid rating {rating!r}; expected one of: {valid}\n"
        f"レーティングの値が不正です ({rating!r})。有効な値: {valid}"
    )


def _register_cropped_file(
    request: CropCreateRequest,
    parent_path: Path,
    *,
    db_manager: ImageDatabaseManager,
    fsm: FileSystemManager,
) -> int:
    """切り出し画像を一時ファイル経由で登録し、子画像 ID を返す。

    一時ディレクトリは ``with`` を抜ける際に必ず削除されるため、登録の成否に
    かかわらず切り出し中間ファイルは残らない。
    """
    rect = request.rect
    suffix = parent_path.suffix or ".png"
    filename = f"{parent_path.stem}_crop_{rect.x}_{rect.y}_{rect.width}_{rect.height}{suffix}"

    with tempfile.TemporaryDirectory(prefix="lorairo_crop_") as temp_dir:
        crop_dir = Path(temp_dir) / _CROP_TEMP_SUBDIR
        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / filename
        with Image.open(parent_path) as source:
            cropped = source.crop((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height))
            cropped.save(crop_path)

        result = db_manager.register_original_image(crop_path, fsm)

    if result is None:
        raise RuntimeError(
            f"Failed to register cropped image for parent image_id={request.parent_image_id}\n"
            f"クロップ画像の登録に失敗しました (parent image_id={request.parent_image_id})"
        )
    child_id, child_metadata = result
    if child_metadata.get("phash_classification") == "duplicate":
        raise RuntimeError(
            f"Cropped image was classified as a duplicate of image_id={child_id}; "
            f"no new image was registered\n"
            f"切り出し画像が既存画像 (image_id={child_id}) の重複と判定されたため、"
            f"新しい画像は登録されませんでした"
        )
    return child_id


def _copy_tags(
    request: CropCreateRequest,
    child_id: int,
    *,
    db_manager: ImageDatabaseManager,
) -> None:
    """採用タグを子画像へコピーする (親のタグ属性を引き継ぐ)。

    親に同名タグがあれば ``model_id`` / ``confidence_score`` / ``existing`` /
    ``is_edited_manually`` を引き継ぎ、無ければ手動由来の既存タグ扱いで登録する。
    親のタグ自体は変更しない。
    """
    if not request.tags:
        return
    parent_annotations = db_manager.get_image_annotations(request.parent_image_id)
    parent_tags = {str(tag["tag"]): tag for tag in parent_annotations["tags"]}

    tags_data: list[TagAnnotationData] = []
    for tag in request.tags:
        source = parent_tags.get(tag)
        if source is None:
            tags_data.append(
                {
                    "tag": tag,
                    "tag_id": None,
                    "model_id": None,
                    "existing": True,
                    "is_edited_manually": False,
                    "confidence_score": None,
                }
            )
            continue
        tags_data.append(
            {
                "tag": tag,
                "tag_id": source.get("tag_id"),
                "model_id": source.get("model_id"),
                "existing": bool(source.get("existing")),
                "is_edited_manually": bool(source.get("is_edited_manually")),
                "confidence_score": source.get("confidence_score"),
            }
        )
    db_manager.save_tags(child_id, tags_data)


def _candidate_tags(tag_rows: list[dict[str, Any]]) -> tuple[str, ...]:
    """タグ行から候補タグ文字列を安定順・重複除去で取り出す。

    ``get_image_annotations`` は既定で soft-reject 済みタグを除外するため、
    ここでは順序保持の重複除去だけを行う。
    """
    seen: dict[str, None] = {}
    for row in tag_rows:
        tag = str(row["tag"])
        if tag:
            seen.setdefault(tag, None)
    return tuple(seen)


def _latest_manual_rating(rating_rows: list[dict[str, Any]]) -> str | None:
    """手動編集レーティングのうち最新の ``normalized_rating`` を返す。

    手動レーティングが無い、または値が空なら None を返す。
    """
    manual = [row for row in rating_rows if row.get("source") == _MANUAL_RATING_SOURCE]
    if not manual:
        return None
    latest = max(manual, key=lambda row: row["created_at"])
    normalized = latest.get("normalized_rating")
    return str(normalized) if normalized else None
