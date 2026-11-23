"""クロップ子画像を注釈チェックの対象 ID 集合へ解決する Qt-free service (#1603, ADR 0092)。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorairo.public_api.exceptions import ImageNotFoundError

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager


def resolve_crop_child_image_ids(
    db_manager: ImageDatabaseManager, parent_image_id: int | None = None
) -> list[int]:
    """`crop_relations` から子画像 ID を重複なしで登録順に返す。

    親・無関係画像は含めない。上限 (作業集合 500 枚) の判定は呼び出し側の
    review 実行に委ね、ここでは解決した集合をそのまま返す。

    Args:
        db_manager: 対象プロジェクトの DB manager。
        parent_image_id: 直接の親画像 ID。None なら全クロップ子画像。

    Returns:
        子画像 ID のリスト。子が無ければ空リスト。

    Raises:
        ImageNotFoundError: 指定した親画像が存在しない場合。
        SQLAlchemyError: 予期しない DB エラー。
    """
    if parent_image_id is not None and not db_manager.image_repo.get_candidate_image_ids([parent_image_id]):
        raise ImageNotFoundError(parent_image_id)
    return list(dict.fromkeys(db_manager.crop_relation_repo.get_child_image_ids(parent_image_id)))
