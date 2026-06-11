"""Wireframes v11 Frame 2A のステージ中心パイプラインテーブル (Phase 6a: 表示専用)。

TAGS/CAPTION/SCORE/RATING の 4 ステージ行に、明示割当 (primary) チップと
multimodal 派生 (derived) チップを描画する。Phase 6a では remove 等の操作は
提供しない (Phase 6b で追加)。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

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

_PRIMARY_CHIP_STYLE = (
    "QLabel { border: 1px solid #5b8def; border-radius: 8px;"
    " padding: 2px 8px; background-color: #eef4ff; color: #1a3b6e; }"
)
_MULTI_CHIP_STYLE = (
    "QLabel { border: 2px solid #7b4fd8; border-radius: 8px;"
    " padding: 2px 8px; background-color: #f3edff; color: #3d2376; }"
)
_DERIVED_CHIP_STYLE = (
    "QLabel { border: 1px dashed #9aa0a6; border-radius: 8px;"
    " padding: 2px 8px; color: #6b7075; font-style: italic; }"
)


class PipelineStageTableWidget(QWidget):
    """Wireframes v11 Frame 2A のステージテーブル (Phase 6a: 表示専用)。"""

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

        row_layout.addStretch(1)
        return container

    def _build_primary_chip(self, model: StageModelInfo, stage: PipelineStage, parent: QWidget) -> QLabel:
        """明示割当チップ (multimodal は MULTI バッジ + 派生ファンアウト注記付き)。"""
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
        return chip

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
