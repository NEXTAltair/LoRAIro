"""選択モデル集合の状態マネージャ (Epic #867 / #884, ADR 0076)。

選択モデル集合 (アノテーション構成の SSoT, ADR 0075) を保持する単一信頼源。
従来 ``ModelSelectionWidget`` の checkbox state が事実上の SSoT だったが、本マネージャへ
hoist し、各 ``ModelSelectionWidget`` は本マネージャを購読する view へ降格する
(ADR 0076、ADR 0074 ``StagingStateManager`` の前例に倣う)。

順序保持・重複排除を担い、変更を Signal で通知する。
"""

from collections import OrderedDict

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger


class ModelSelectionStateManager(QObject):
    """選択モデル集合 (litellm_model_id) の単一信頼源 (SSoT)。

    選択された ``litellm_model_id`` を追加順に保持し、置換・単件トグル・クリアを
    提供する。複数の ``ModelSelectionWidget`` が本インスタンスを共有することで、
    タブ間のモデル選択状態を一元化する (#884)。

    Signals:
        selection_changed: 選択集合が変化したとき、現在の選択 ``list[str]`` を載せて発行。
    """

    selection_changed = Signal(list)  # list[str] - 選択 litellm_model_id (追加順)

    def __init__(self, parent: QObject | None = None) -> None:
        """選択モデル状態マネージャを初期化する。

        Args:
            parent: 親 QObject。
        """
        super().__init__(parent)
        # 順序保持 + 重複排除のため OrderedDict の key を集合として使う
        self._selected: OrderedDict[str, None] = OrderedDict()

    def get_selected(self) -> list[str]:
        """選択中の litellm_model_id を追加順で返す。"""
        return list(self._selected.keys())

    def count(self) -> int:
        """選択中のモデル数を返す。"""
        return len(self._selected)

    def is_selected(self, litellm_model_id: str) -> bool:
        """指定モデルが選択中かを返す。"""
        return litellm_model_id in self._selected

    def set_selected(self, litellm_model_ids: list[str]) -> None:
        """選択集合を置換する (重複排除・順序保持)。変化時のみ発行する。

        Args:
            litellm_model_ids: 新しい選択集合。
        """
        new_selected: OrderedDict[str, None] = OrderedDict()
        for litellm_model_id in litellm_model_ids:
            new_selected[litellm_model_id] = None
        if list(new_selected.keys()) == list(self._selected.keys()):
            return
        self._selected = new_selected
        logger.debug(f"選択モデル集合を更新: {len(self._selected)} 件")
        self.selection_changed.emit(self.get_selected())

    def set_model_selected(self, litellm_model_id: str, selected: bool) -> None:
        """単一モデルの選択を ON/OFF する。変化時のみ発行する。

        Args:
            litellm_model_id: 対象モデルの litellm_model_id。
            selected: True で選択追加、False で解除。
        """
        present = litellm_model_id in self._selected
        if selected and not present:
            self._selected[litellm_model_id] = None
        elif not selected and present:
            del self._selected[litellm_model_id]
        else:
            return
        self.selection_changed.emit(self.get_selected())

    def clear(self) -> None:
        """選択集合を空にする。元が非空のときのみ発行する。"""
        if not self._selected:
            return
        self._selected.clear()
        logger.info("選択モデル集合をクリア")
        self.selection_changed.emit([])
