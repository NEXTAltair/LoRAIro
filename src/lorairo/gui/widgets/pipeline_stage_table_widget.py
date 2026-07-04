"""Wireframes v11 Frame 2A/2B のステージ中心パイプラインテーブル。

TAGS/CAPTION/SCORE/RATING の 4 ステージ行に、明示割当 (primary) チップと
multimodal 派生 (derived) チップを描画する (Phase 6a)。Phase 6b で各行の
「+ 追加」ボタンと primary チップの × ボタンを追加し、操作要求を Signal で
通知する (SSoT は ModelSelectionWidget のチェック状態のため、本 widget は
要求を emit するだけで状態を持たない)。

Issue #846: 各ステージ行を DsCard に収める。
Issue #847: preset chip 行と凡例を最上部の DsCard に収める（視覚リファクタ）。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from lorairo.gui import theme
from lorairo.gui.widgets.ds_card import DsCard
from lorairo.gui.widgets.tag_cloud_widget import FlowLayout
from lorairo.services.pipeline_composition import DerivedChip, PipelineStage, StageModelInfo, StageRow

# 表示順 (Wireframes v11 Frame 2A の行順)
_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.TAGS,
    PipelineStage.CAPTION,
    PipelineStage.SCORE,
    PipelineStage.RATING,
)


@dataclass(frozen=True)
class PipelinePreset:
    """パイプライン構成プリセット (DS v12 AnnotateScreen の preset chip)。

    Attributes:
        preset_id: プリセットの一意キー (Signal で emit する識別子)。
        label: chip に表示する名前。
        model_count: プリセットが割り当てるユニークモデル数 (chip 右肩の件数バッジ)。
    """

    preset_id: str
    label: str
    model_count: int


# DS v12 AnnotateScreen (Issue #838): パイプライン上部の組込みプリセット行。
# 件数は「そのプリセットが割り当てるユニークモデル数」を示す表示値で、
# 実際の割当切替・件数算出は preset_selected を受けた呼び出し元が担う
# (本 widget は状態を持たず要求を emit するだけ)。
_BUILTIN_PRESETS: tuple[PipelinePreset, ...] = (
    PipelinePreset("default", "Default", 5),
    PipelinePreset("tags_only", "Tags only", 1),
    PipelinePreset("full_caption", "Full caption", 3),
    PipelinePreset("score_rate", "Score·rate", 3),
)

# 初期アクティブプリセット (accent 強調される既定構成)
_DEFAULT_PRESET_ID = "default"

_SAVE_PRESET_TEXT = "+ 現状を保存"
_SAVE_PRESET_TOOLTIP = "現在のステージ構成を新しいプリセットとして名前付きで保存します"
_PRESET_ROW_LABEL_TEXT = "プリセット"


def _preset_chip_style(active: bool) -> str:
    """preset chip の QSS。アクティブは accent 地、非アクティブは card 地の mono チップ。"""
    if active:
        bg, border, color = theme.ACCENT_SOFT, theme.ACCENT_BORDER, theme.ACCENT_HOVER
        weight = theme.FONT_WEIGHT_SEMIBOLD
    else:
        bg, border, color = theme.CARD, theme.LINE, theme.INK_SOFT
        weight = theme.FONT_WEIGHT_MEDIUM
    return (
        f"QToolButton {{ font-family: {theme.FONT_MONO_CSS}; background-color: {bg};"
        f" border: {theme.BORDER_WIDTH}px solid {border};"
        f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 10px;"
        f" color: {color}; font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {weight}; }}"
    )


# 「+ 現状を保存」は点線 border の控えめなアクション (チップではなくボタン文法)
_SAVE_PRESET_STYLE = (
    f"QToolButton {{ font-family: {theme.FONT_SANS_CSS}; background-color: {theme.CARD};"
    f" border: {theme.BORDER_WIDTH}px dashed {theme.LINE_STRONG};"
    f" border-radius: {theme.RADIUS}px; padding: 1px 9px;"
    f" color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px; }}"
)

_LEGEND_TEXT = (
    "MULTI model-name = 主割当 / ↝ model-name = 派生 = 同推論の副産物"
    " · 操作不可（既定で採用 · 不要分は Results で外せる）"
)

_DERIVED_TOOLTIP = (
    "派生 = 同一推論の副産物。構成時には外せません（外しても課金は同じ 1 推論）。"
    "既定で採用され、不要なものだけ Results で外せます"
)

_RATING_NOTE_TEXT = "multimodal 派生なし †"
_RATING_NOTE_TOOLTIP = (
    "multimodal の 1 推論は tags+captions+score を返し rating には届きません。"
    "rating は rating 対応モデルか送信前プリフライト (OpenAI Moderations) 由来です"
)

_REMOVE_BUTTON_TOOLTIP = "選択から外す（このモデルは全ステージから外れます）"
_ADD_BUTTON_TEXT = "+ 追加"

# DS v12 AnnotateScreen (Issue #787): chip 文法 = borders-not-shadows / mono。
# 主割当 = card 地 + line-strong border の mono チップ、multimodal は accent border で強調、
# 派生 = 点線 border + 斜体 mono (操作不可)。
# #1105: 手書き QSS 定数を theme.chip_qss(kind, ...) の構造パラメータへ置換。
# 色は theme の palette (primary/multi/derived) が SSoT、意匠 (mono/dashed/italic) は
# 引数で再現する (見た目不変)。
_PRIMARY_CHIP_STYLE = theme.chip_qss("primary", mono=True, weight=None)
_MULTI_CHIP_STYLE = theme.chip_qss("multi", mono=True, weight=theme.FONT_WEIGHT_SEMIBOLD)
_DERIVED_CHIP_STYLE = theme.chip_qss("derived", mono=True, border_style="dashed", italic=True, weight=None)


class PipelineStageTableWidget(QWidget):
    """Wireframes v11 Frame 2A/2B のステージテーブル (表示 + ステージ単位の操作要求)。

    #846: 各ステージ行を DsCard で包み、Card surface (白地・hairline border) を付与。
    #847: プリセット chip 行と凡例を最上部の DsCard に集約。
    """

    # ステージ行の「+ 追加」が押された (引数: PipelineStage の value)
    add_model_requested = Signal(str)
    # primary チップの × が押された (引数: stage value, litellm_model_id)
    remove_model_requested = Signal(str, str)
    # preset chip が選択された (引数: PipelinePreset.preset_id)
    preset_selected = Signal(str)
    # 「+ 現状を保存」が押された (現在構成の名前付き保存要求)
    save_preset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._preset_buttons: dict[str, QToolButton] = {}
        self._active_preset_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACE_2)

        # プリセット chip 行 + 凡例を DsCard に収める (#847)
        layout.addWidget(self._build_preset_row())

        # ステージ行エリア (各行が DsCard で包まれる、#846)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(theme.SPACE_2)
        layout.addLayout(self._rows_layout)
        layout.addStretch(1)

        self.set_active_preset(_DEFAULT_PRESET_ID)
        self.clear()

    def _build_preset_row(self) -> DsCard:
        """プリセット chip 行と凡例を収めた DsCard を構築する (#847)。

        Returns:
            DsCard — preset chip ボタン群・「+ 現状を保存」ボタン・凡例ラベルを内包。
        """
        card = DsCard(parent=self)
        card.setObjectName("presetRow")

        # カード本体: プリセット chip 行 (HBox) + 凡例 (VBox で積む)
        body = QWidget(card)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(theme.SPACE_1)

        # ─── プリセット chip 行 (FlowLayout で折り返す) ───
        # ラベル + preset chip 群 + 保存ボタンを 1 行に固定すると ~574px の最小幅を握り、
        # 狭幅で横スクロールの一因になっていた (#1100 再オープン)。
        chip_row = QWidget(body)
        chip_row.setObjectName("presetChipRow")
        chip_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        row_layout = FlowLayout(chip_row, spacing=6)

        label = QLabel(_PRESET_ROW_LABEL_TEXT, chip_row)
        label.setObjectName("presetRowLabel")
        label.setStyleSheet(
            f"color: {theme.INK_SOFT}; letter-spacing: {theme.LETTER_CAPS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        row_layout.addWidget(label)

        for preset in _BUILTIN_PRESETS:
            button = QToolButton(chip_row)
            button.setObjectName("presetChip")
            button.setText(f"{preset.label} {preset.model_count}")
            button.setCheckable(True)
            button.setToolTip(
                f"プリセット「{preset.label}」を適用 (モデル {preset.model_count} 件をステージへ割当)"
            )
            button.clicked.connect(
                lambda _checked=False, pid=preset.preset_id: self._on_preset_clicked(pid)
            )
            self._preset_buttons[preset.preset_id] = button
            row_layout.addWidget(button)

        save_button = QToolButton(chip_row)
        save_button.setObjectName("savePresetButton")
        save_button.setText(_SAVE_PRESET_TEXT)
        save_button.setToolTip(_SAVE_PRESET_TOOLTIP)
        save_button.setStyleSheet(_SAVE_PRESET_STYLE)
        save_button.clicked.connect(lambda _checked=False: self.save_preset_requested.emit())
        row_layout.addWidget(save_button)

        body_layout.addWidget(chip_row)

        # ─── 凡例ラベル (カード内下部) ───
        legend = QLabel(_LEGEND_TEXT, body)
        legend.setObjectName("pipelineLegendLabel")
        # 長い凡例文は折り返す。折り返さないと ~594px の最小幅を握り、狭幅で横スクロールの
        # 一因になっていた (#1100 再オープン: 最小幅を握る子の排除)。
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_META}px; border: none;")
        body_layout.addWidget(legend)

        card.set_body(body)
        return card

    def _on_preset_clicked(self, preset_id: str) -> None:
        """preset chip クリック: アクティブ表示を更新し選択を通知する。"""
        self.set_active_preset(preset_id)
        self.preset_selected.emit(preset_id)

    def set_active_preset(self, preset_id: str | None) -> None:
        """アクティブな preset chip を accent 強調する (Signal は emit しない)。

        Args:
            preset_id: アクティブにする preset_id。未知 / None なら全 chip 非アクティブ。
        """
        self._active_preset_id = preset_id if preset_id in self._preset_buttons else None
        for pid, button in self._preset_buttons.items():
            active = pid == self._active_preset_id
            button.setChecked(active)
            button.setStyleSheet(_preset_chip_style(active))

    def display(self, rows: list[StageRow]) -> None:
        """4 ステージ行を再描画する。

        Args:
            rows: 表示するステージ行情報のリスト。
        """
        rows_by_stage = {row.stage: row for row in rows}
        self._clear_rows()
        for stage in _STAGE_ORDER:
            self._rows_layout.addWidget(self._build_stage_row(stage, rows_by_stage.get(stage)))

    def clear(self) -> None:
        """全行を空表示にする。"""
        self.display([])

    def _clear_rows(self) -> None:
        """既存のステージ行 DsCard を layout から外して破棄する。"""
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                # findChildren で前回チップが見えないよう、即時に親子関係を切る
                widget.setParent(None)
                widget.deleteLater()

    def _build_stage_row(self, stage: PipelineStage, row: StageRow | None) -> DsCard:
        """ステージ 1 行分の DsCard を構築する (#846)。

        DsCard の objectName を ``stageRow_{stage.name}`` に設定するため、
        既存の ``findChildren(QWidget, "stageRow_*")`` 系のテストはそのまま通る
        (DsCard は QFrame → QWidget のサブクラス)。

        Args:
            stage: 対象ステージ種別。
            row: ステージのモデル割当情報。None の場合は空行を描画。

        Returns:
            DsCard — ステージ名・カウント・チップ群・「+ 追加」ボタンを内包。
        """
        card = DsCard(parent=self)
        card.setObjectName(f"stageRow_{stage.name}")

        # カード本体: KEY ラベル + カウント + チップ群 + 追加ボタン
        body = QWidget(card)
        row_layout = QHBoxLayout(body)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(theme.SPACE_1)

        # DS: UPPERCASE ステージ見出し = ink-soft + letter-caps の字間
        name_label = QLabel(stage.name, body)
        name_label.setObjectName(f"stageName_{stage.name}")
        name_font = name_label.font()
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setFixedWidth(72)
        name_label.setStyleSheet(
            f"color: {theme.INK_SOFT}; letter-spacing: {theme.LETTER_CAPS};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; border: none;"
        )
        row_layout.addWidget(name_label)
        # ステージ名は固定左列。折り返すチップ群に対して上揃えにする。
        row_layout.setAlignment(name_label, Qt.AlignmentFlag.AlignTop)

        primary_models = row.primary_models if row is not None else ()
        derived_chips = row.derived_chips if row is not None else ()

        # DS: n / ↝N の件数は mono ・ ink-faint
        count_text = str(len(primary_models))
        if derived_chips:
            count_text += f" + ↝{len(derived_chips)}"
        count_label = QLabel(count_text, body)
        count_label.setObjectName(f"stageCount_{stage.name}")
        count_label.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; color: {theme.INK_FAINT};"
            f" font-size: {theme.FONT_SIZE_META}px; border: none;"
        )
        row_layout.addWidget(count_label)
        row_layout.setAlignment(count_label, Qt.AlignmentFlag.AlignTop)

        # チップ群 (primary / derived / rating note / 「+ 追加」) は FlowLayout で折り返す。
        # 1 行のままだとウィンドウ幅を超えて親コンテンツの最小幅を押し広げ、横スクロールと
        # 兄弟 (LEDGER) の折り返し無効化を招いていた (#1100 再オープン)。FlowLayout の
        # minimumSize は単一チップ幅なので、widgetResizable スクロール内でも最小幅を握らない。
        chips_container = QWidget(body)
        chips_container.setObjectName(f"stageChips_{stage.name}")
        chips_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        chips_flow = FlowLayout(chips_container, spacing=theme.SPACE_1)

        for model in primary_models:
            chips_flow.addWidget(self._build_primary_chip(model, stage, chips_container))
        for derived in derived_chips:
            chips_flow.addWidget(self._build_derived_chip(derived, chips_container))

        if stage is PipelineStage.RATING:
            note = QLabel(_RATING_NOTE_TEXT, chips_container)
            note.setObjectName("ratingNoDerivedNote")
            note.setToolTip(_RATING_NOTE_TOOLTIP)
            chips_flow.addWidget(note)

        add_button = QToolButton(chips_container)
        add_button.setObjectName("stageAddModelButton")
        add_button.setText(_ADD_BUTTON_TEXT)
        add_button.setToolTip(f"{stage.name} に出力を届けられるモデルを選択して追加します")
        add_button.clicked.connect(
            lambda _checked=False, value=stage.value: self.add_model_requested.emit(value)
        )
        chips_flow.addWidget(add_button)

        # チップ列が残り幅を占有して折り返す (stretch=1)。addStretch は使わない。
        row_layout.addWidget(chips_container, 1)

        card.set_body(body)
        return card

    def _build_primary_chip(self, model: StageModelInfo, stage: PipelineStage, parent: QWidget) -> QWidget:
        """明示割当チップ (multimodal は MULTI バッジ + 派生ファンアウト注記付き)。

        Phase 6b: チップ label と × ボタンを HBox で一体化した container を返す。
        × は「選択集合から外す」操作で、押すと全ステージから消える (モデル単位実行)。

        Args:
            model: 描画するモデル情報。
            stage: このチップが属するステージ。
            parent: 親ウィジェット (DsCard ボディ)。

        Returns:
            chip label + × ボタンを含む container widget。
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
        """派生チップ (↝、斜体グレー、操作不可)。

        Args:
            derived: 派生チップ情報。
            parent: 親ウィジェット (DsCard ボディ)。

        Returns:
            スタイル適用済みの派生チップ QLabel。
        """
        chip = QLabel(
            f"↝ {derived.model.display_name} from {derived.origin_stage.name}",
            parent,
        )
        chip.setObjectName("derivedChip")
        chip.setStyleSheet(_DERIVED_CHIP_STYLE)
        chip.setToolTip(_DERIVED_TOOLTIP)
        return chip
