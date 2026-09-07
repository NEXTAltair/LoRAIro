"""クロップ親子関係を詳細カラム表示用に取得する GUI サービス (#1346 / ADR 0092)。

``ImageDatabaseManager`` の ``get_crop_parent`` / ``get_crop_children`` を呼び、
ORM オブジェクトを表示用の :class:`~lorairo.gui.widgets.related_images_widget.RelatedImageEntry`
へ射影する。ウィジェット側を DB 非依存に保つための薄い変換層で、DB 例外は握り潰さず
呼び出し元 (詳細ウィジェット) へ伝播させる。
"""

from __future__ import annotations

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import CropRelation
from ...utils.log import logger
from ..widgets.related_images_widget import RelatedImageEntry


def _to_entry(relation: CropRelation, image_id: int) -> RelatedImageEntry:
    """関係行を表示用エントリへ射影する。

    Args:
        relation: `crop_relations` の 1 行。
        image_id: 表示対象となる相手側の画像 ID。

    Returns:
        表示用の :class:`RelatedImageEntry`。
    """
    return RelatedImageEntry(
        image_id=image_id,
        x=relation.x,
        y=relation.y,
        width=relation.width,
        height=relation.height,
        origin=relation.origin,
    )


class CropRelationService:
    """画像詳細カラムの「関連画像」セクションへ親子関係を供給するサービス。"""

    def __init__(self, db_manager: ImageDatabaseManager) -> None:
        """サービスを初期化する。

        Args:
            db_manager: クロップ親子関係を保持する DB マネージャー。
        """
        self._db_manager = db_manager
        logger.debug("CropRelationService initialized")

    def get_parent(self, image_id: int) -> RelatedImageEntry | None:
        """直接の親を返す。クロップ画像でなければ None。

        Args:
            image_id: 対象の画像 ID。

        Returns:
            親のエントリ。親が無ければ None。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播させる。
        """
        relation = self._db_manager.get_crop_parent(image_id)
        if relation is None:
            return None
        return _to_entry(relation, relation.parent_image_id)

    def get_children(self, image_id: int) -> list[RelatedImageEntry]:
        """この画像から切り出した子を登録順に返す。

        Args:
            image_id: 対象の画像 ID。

        Returns:
            子のエントリ一覧。子が無ければ空リスト。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播させる。
        """
        return [
            _to_entry(relation, relation.child_image_id)
            for relation in self._db_manager.get_crop_children(image_id)
        ]
