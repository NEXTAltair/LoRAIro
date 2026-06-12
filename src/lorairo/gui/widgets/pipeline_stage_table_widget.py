"""Wireframes v11 Frame 2A/2B のステージ中心パイプラインテーブル。

TAGS/CAPTION/SCORE/RATING の 4 ステージ行に、明示割当 (primary) チップと
multimodal 派生 (derived) チップを描画する (Phase 6a)。Phase 6b で各行の
「+ 追加」ボタンと primary チップの × ボタンを追加し、操作要求を Signal で
通知する (SSoT は ModelSelectionWidget のチェック状態のため、本 widget は
要求を emit するだけで状態を持たない)。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.services.pipeline_composition import DerivedChip, PipelineStage, StageModelInfo, StageRow

# 表示順 (Wireframes v11 Frame 2A の行順)
_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.TAGS,
    PipelineStage.CAPTION,
    PipelineStage.SCORE,
    PipelineStage.RATING,
)

_LEGEND_TEXT = (
    "MULTI model-name = 主割当 / ↝ model-name = 派生 = 同推論の副産物 · 操作不可（Results で却下）"
)

_DERIVED_TOOLTIP = (
    "派生 = 同一推論の副産物。構成時には外せません（外しても課金は同じ 1 推論）。"
    "不要なら Results で却下してください"
)

_RATING_NOTE_TEXT = "multimodal 派生なし †"
_RATING_NOTE_TOOLTIP = (
    "multimodal の 1 推論は tags+captions+score を返し rating には届きません。"
    "rating は rating 対応モデルか送信前プリフライト (OpenAI Moderations) 由来です"
)

_REMOVE_BUTTON_TOOLTIP = "選択から外す（このモデルは全ステージから外れます）"
_ADD_BUTTON_TEXT = "+ 追加"

# Theme v1 (Issue #760): 主割当 = info、multi-stage 強調 = accent、派生 = 点線 muted
_PRIMARY_CHIP_STYLE = theme.chip_qss("info")
_MULTI_CHIP_STYLE = theme.chip_qss("accent")
_DERIVED_CHIP_STYLE = (
    f"QLabel {{ border: 1px dashed {theme.LINE_STRONG}; border-radius: {theme.RADIUS_CHIP}px;"
    f" padding: 1px 9px; color: {theme.INK_FAINT}; font-style: italic; }}"
)


class PipelineStageTableWidget(QWidget):
    """Wireframes v11 Frame 2A/2B のステージテーブル (表示 + ステージ単位の操作要求)。"""

    # ステージ行の「+ 追加」が押された (引数: PipelineStage の value)
    add_model_requested = Signal(str)
    # primary チップの × が押された (引数: stage value, litellm_model_id)
    remove_model_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        legend = QLabel(_LEGEND_TEXT, self)
        legend.setObjectName("pipelineLegendLabel")
        legend_font = legend.font()
        legend_font.setPointSize(max(6, legend_font.pointSize() - 2))
        legend.setFont(legend_font)
        layout.addWidget(legend)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_layout)
        layout.addStretch(1)

        self.clear()

    def display(self, rows: list[StageRow]) -> None:
        """4 ステージ行を再描画する。"""
        rows_by_stage = {row.stage: row for row in rows}
        self._clear_rows()
        for stage in _STAGE_ORDER:
            self._rows_layout.addWidget(self._build_stage_row(stage, rows_by_stage.get(stage)))

    def clear(self) -> None:
        """全行を空表示にする。"""
        self.display([])

    def _clear_rows(self) -> None:
        """既存のステージ行 widget を layout から外して破棄する。"""
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # findChildren で前回チップが見えないよう、即時に親子関係を切る
                widget.setParent(None)
                widget.deleteLater()

    def _build_stage_row(self, stage: PipelineStage, row: StageRow | None) -> QWidget:
        """ステージ 1 行分の container widget を構築する。"""
        container = QWidget(self)
        container.setObjectName(f"stageRow_{stage.name}")
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 2, 0, 2)

        name_label = QLabel(stage.name, container)
        name_label.setObjectName(f"stageName_{stage.name}")
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setFixedWidth(72)
        row_layout.addWidget(name_label)

        primary_models = row.primary_models if row is not None else ()
        derived_chips = row.derived_chips if row is not None else ()

        count_text = str(len(primary_models))
        if derived_chips:
            count_text += f" + ↝{len(derived_chips)}"
        count_label = QLabel(count_text, container)
        count_label.setObjectName(f"stageCount_{stage.name}")
        row_layout.addWidget(count_label)

        for model in primary_models:
            row_layout.addWidget(self._build_primary_chip(model, stage, container))
        for derived in derived_chips:
            row_layout.addWidget(self._build_derived_chip(derived, container))

        if stage is PipelineStage.RATING:
            note = QLabel(_RATING_NOTE_TEXT, container)
            note.setObjectName("ratingNoDerivedNote")
            note.setToolTip(_RATING_NOTE_TOOLTIP)
            row_layout.addWidget(note)

        add_button = QToolButton(container)
        add_button.setObjectName("stageAddModelButton")
        add_button.setText(_ADD_BUTTON_TEXT)
        add_button.setToolTip(f"{stage.name} に出力を届けられるモデルを選択して追加します")
        add_button.clicked.connect(
            lambda _checked=False, value=stage.value: self.add_model_requested.emit(value)
        )
        row_layout.addWidget(add_button)

        row_layout.addStretch(1)
        return container

    def _build_primary_chip(self, model: StageModelInfo, stage: PipelineStage, parent: QWidget) -> QWidget:
        """明示割当チップ (multimodal は MULTI バッジ + 派生ファンアウト注記付き)。

        Phase 6b: チップ label と × ボタンを HBox で一体化した container を返す。
        × は「選択集合から外す」操作で、押すと全ステージから消える (モデル単位実行)。
        """
        if model.is_multimodal:
            fanout_stages = [s for s in _STAGE_ORDER if s in model.fill_stages() and s is not stage]
            text = f"MULTI {model.display_name}"
            if fanout_stages:
                letters = " ".join(s.name[0] for s in fanout_stages)
                text += f" +派生 {letters}"
            chip = QLabel(text, parent)
            chip.setStyleSheet(_MULTI_CHIP_STYLE)
            chip.setToolTip("multimodal: 1 推論で tags / caption / score を同時に出力します")
        else:
            chip = QLabel(model.display_name, parent)
            chip.setStyleSheet(_PRIMARY_CHIP_STYLE)
        chip.setObjectName("primaryChip")

        container = QWidget(parent)
        container.setObjectName("primaryChipContainer")
        chip_layout = QHBoxLayout(container)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(2)
        chip_layout.addWidget(chip)

        remove_button = QToolButton(container)
        remove_button.setObjectName("primaryChipRemoveButton")
        remove_button.setText("×")
        remove_button.setAutoRaise(True)
        remove_button.setToolTip(_REMOVE_BUTTON_TOOLTIP)
        remove_button.clicked.connect(
            lambda _checked=False, value=stage.value, model_id=model.litellm_model_id: (
                self.remove_model_requested.emit(value, model_id)
            )
        )
        chip_layout.addWidget(remove_button)
        return container

    def _build_derived_chip(self, derived: DerivedChip, parent: QWidget) -> QLabel:
        """派生チップ (↝、斜体グレー、操作不可)。"""
        chip = QLabel(
            f"↝ {derived.model.display_name} from {derived.origin_stage.name}",
            parent,
        )
        chip.setObjectName("derivedChip")
        chip.setStyleSheet(_DERIVED_CHIP_STYLE)
        chip.setToolTip(_DERIVED_TOOLTIP)
        return chip
