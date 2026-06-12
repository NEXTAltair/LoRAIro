"""Wireframes v11 Frame 2B のステージ別モデルピッカー (Phase 6b)。

ステージ行の「+ 追加」から開き、そのステージに出力を届けられる未選択モデルを
チェック可能リストで提示する。OK 後の `selected_model_ids()` を呼び出し元
(MainWindow) が ModelSelectionWidget のチェック ON に変換する — SSoT は
あくまで「選択モデル集合」であり、本ダイアログは候補提示と選択結果の返却のみ。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_per_image_cost,
)
from lorairo.services.pipeline_composition import PipelineStage, StageModelInfo

_EMPTY_CANDIDATES_TEXT = "このステージに追加できる未選択モデルがありません"
_MULTIMODAL_NOTE = "· 1推論で T C S（R は preflight 由来）"

_cost_service = CostEstimationService()


class StageModelPickerDialog(QDialog):
    """ステージに追加可能なモデル候補を列挙するチェックリストダイアログ。"""

    def __init__(
        self,
        stage: PipelineStage,
        candidates: list[StageModelInfo],
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを構築する。

        Args:
            stage: 追加先のパイプラインステージ。
            candidates: このステージに出力を届けられる未選択モデルのリスト。
            parent: 親 widget。
        """
        super().__init__(parent)
        self.setWindowTitle(f"{stage.value.upper()} のモデルを選択")

        layout = QVBoxLayout(self)

        self._candidate_list = QListWidget(self)
        self._candidate_list.setObjectName("stageModelCandidateList")
        for info in candidates:
            item = QListWidgetItem(self._candidate_text(info))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, info.litellm_model_id)
            self._candidate_list.addItem(item)

        if candidates:
            layout.addWidget(self._candidate_list)
        else:
            self._candidate_list.hide()
            empty_label = QLabel(_EMPTY_CANDIDATES_TEXT, self)
            empty_label.setObjectName("emptyCandidatesLabel")
            layout.addWidget(empty_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None and not candidates:
            ok_button.setEnabled(False)
        layout.addWidget(button_box)

    @staticmethod
    def _candidate_text(info: StageModelInfo) -> str:
        """候補 1 件分の表示テキストを返す (Issue #747: コストをカード直載せ)。"""
        origin = f"API: {info.provider}" if info.is_api else "ローカル"
        cost = format_per_image_cost(_cost_service.per_image_usd(info), info.is_api)
        text = f"{info.display_name}（{origin}）· {cost}"
        if info.is_multimodal:
            text += f" {_MULTIMODAL_NOTE}"
        return text

    def selected_model_ids(self) -> list[str]:
        """チェック済み候補の litellm_model_id リストを返す。"""
        selected: list[str] = []
        for index in range(self._candidate_list.count()):
            item = self._candidate_list.item(index)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return selected
