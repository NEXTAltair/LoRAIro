"""ステージ別モデルピッカー (調整版 DS AnnotateScreen ModelPicker、Issue #839)。

ステージ行の「+ 追加」から開き、そのステージに出力を届けられる未選択モデルを
``実行環境 × アノテーション種類 × provider`` で絞り込みながらリッチに選択する
モーダル。OK 後の :meth:`selected_model_ids` を呼び出し元 (MainWindow) が
ModelSelectionWidget のチェック ON に変換する — SSoT はあくまで「選択モデル集合」
であり、本ダイアログは候補提示と選択結果の返却のみを担う。

レイアウト (DS ``AnnotateScreen.jsx`` の ``ModelPicker`` に準拠):

- ヘッダ: ステージ名 + 現在のフィルタ要約。
- presets 行: All installed / Multimodal only / Cheap (local) / High-fidelity API
  のワンクリック絞り込み chip。
- 左レール: ①アノテーション種類フィルタ (件数付き radio) ②Provider フィルタ
  (件数付き radio) ③候補の出どころ説明 (API キー + ローカルモデルから DB 自動生成、
  キー未設定は warn → Settings 誘導)。
- 実行環境セグメント (すべて / APIのみ / ローカルのみ) → 変更で provider をリセット。
- モデル行: チェック + 名前 + multimodal/種別バッジ + status chip + コスト +
  conf-min スライダー (タグ出力モデルのみ)。
- 全選択 / 全解除 / 推奨選択 ボタンと、選択数フッタ。

Issue #755 由来の挙動を維持する: API キー未設定の WebAPI モデルも非表示にせず
``○ needs key`` で可視化し、行クリックを :data:`configure_key_requested` で呼び出し元へ
通知して ConfigurationWindow の該当 provider 欄へ誘導する。キー保存後は
:meth:`refresh_key_status` で ``● API ready`` に解消される。

``StageModelInfo`` は per-tag confidence の統計 (avg 等) や廃止フラグを保持しない
(参照: AI タグの confidence は常に None)。そのため avg 表示や discontinued 行は
データが無いため描画せず、conf-min スライダーは「タグ出力を持つモデル」に限定し、
スライダー値は :meth:`confidence_thresholds` で取得できる (呼び出し元は無視可能)。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.cost_estimation_service import (
    CostEstimationService,
    format_per_image_cost,
)
from lorairo.services.model_route_service import required_provider_for
from lorairo.services.pipeline_composition import PipelineStage, StageModelInfo

# --- 表示テキスト -----------------------------------------------------------
_EMPTY_CANDIDATES_TEXT = "このステージに追加できる未選択モデルがありません"
_NO_MATCH_TEXT = "条件に一致するモデルがありません — フィルタを変更してください"
_MULTIMODAL_NOTE = "1推論で T C S（R は preflight 由来）"
_ORIGIN_NOTE = (
    "候補の出どころ: 設定済 API キー ＋ 利用可能なローカルモデルから DB が自動生成。"
    "キー未設定は needs key（→ Settings）。"
)

# Issue #755: モデルステータス表現 (DS の chip 文法)
_STATUS_INSTALLED = "● installed"
_STATUS_API_READY = "● API ready"
_STATUS_NEEDS_KEY = "○ needs key"
_NEEDS_KEY_TOOLTIP = "API キー未設定です。クリックすると設定画面の該当 provider 欄を開きます。"

# 実行環境セグメント
_ENV_ALL = "all"
_ENV_API = "api"
_ENV_LOCAL = "local"
_ENV_LABELS = {_ENV_ALL: "全環境", _ENV_API: "Web API", _ENV_LOCAL: "ローカル"}
_ENV_SEGMENTS: tuple[tuple[str, str], ...] = (
    (_ENV_ALL, "すべて"),
    (_ENV_API, "APIのみ"),
    (_ENV_LOCAL, "ローカルのみ"),
)

# アノテーション種類フィルタ (UI トークン → 表示名 / PipelineStage)
_TYPE_ALL = "all"
_TYPE_ORDER: tuple[str, ...] = ("tags", "caption", "score", "rating")
_TYPE_LABELS = {"tags": "タグ", "caption": "キャプション", "score": "スコア", "rating": "レーティング"}
_TYPE_TO_STAGE = {
    "tags": PipelineStage.TAGS,
    "caption": PipelineStage.CAPTION,
    "score": PipelineStage.SCORE,
    "rating": PipelineStage.RATING,
}
# PipelineStage → UI 種類トークン (ステージ既定の初期選択に使う)
_STAGE_TO_TYPE = {stage: token for token, stage in _TYPE_TO_STAGE.items()}

# conf-min スライダーの既定値 (タグ confidence の下限初期値)
_DEFAULT_CONF_MIN = 0.35
_CONF_SLIDER_STEPS = 100  # 0.00〜1.00 を 0.01 刻みで表現

_LOCAL_PROVIDER_LABEL = "local"

_cost_service = CostEstimationService()


def _provider_label(info: StageModelInfo) -> str:
    """フィルタ / 表示に使う provider ラベルを返す。ローカルは ``"local"``。"""
    if not info.is_api:
        return _LOCAL_PROVIDER_LABEL
    return info.provider or _LOCAL_PROVIDER_LABEL


def _model_types(info: StageModelInfo) -> list[str]:
    """モデルが出力できる UI 種類トークンを ``_TYPE_ORDER`` 順で返す。"""
    delivered = info.fill_stages()
    return [token for token in _TYPE_ORDER if _TYPE_TO_STAGE[token] in delivered]


def _badge_text(info: StageModelInfo) -> str:
    """種別バッジに出すテキストを返す (multimodal か先頭の出力種類)。"""
    if info.is_multimodal:
        return "multimodal"
    types = _model_types(info)
    return types[0] if types else ""


def _supports_conf_min(info: StageModelInfo) -> bool:
    """conf-min スライダー対象か (タグ confidence の閾値を持てるモデル)。"""
    return "tags" in info.capabilities


def _matches_filters(info: StageModelInfo, env: str, type_token: str, provider: str) -> bool:
    """実行環境 × アノテーション種類 × provider のフィルタに一致するか判定する。"""
    if env == _ENV_API and not info.is_api:
        return False
    if env == _ENV_LOCAL and info.is_api:
        return False
    if type_token != _TYPE_ALL and _TYPE_TO_STAGE[type_token] not in info.fill_stages():
        return False
    if provider != "all" and _provider_label(info) != provider:
        return False
    return True


class _ModelRow(QFrame):
    """モデル候補 1 件分の行ウィジェット (チェック + メタ + status + conf スライダー)。

    行全体のクリックで選択をトグルする。conf-min スライダーは ``QSlider`` が
    マウスイベントを消費するため、スライダー操作は行トグルに伝播しない。
    ``○ needs key`` 行はチェック不可とし、クリックで設定導線シグナルを通知する。

    Signals:
        toggle_requested: チェック可能行のクリックでトグルを要求する。
        configure_requested: needs key 行のクリックで設定導線を要求する。
    """

    toggle_requested = Signal()
    configure_requested = Signal()

    def __init__(self, info: StageModelInfo, parent: QWidget | None = None) -> None:
        """行ウィジェットを構築する。

        Args:
            info: 表示対象モデルのスナップショット。
            parent: 親 widget。
        """
        super().__init__(parent)
        self._info = info
        self._selected = False
        self._needs_key = False
        self.setObjectName("stageModelRow")

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(theme.SPACE_2, theme.SPACE_1, theme.SPACE_2, theme.SPACE_1)
        row_layout.setSpacing(theme.SPACE_2)

        # チェックインジケータ (選択状態で accent 表示)
        self._check_label = QLabel("", self)
        self._check_label.setObjectName("stageModelRowCheck")
        self._check_label.setFixedSize(16, 16)
        self._check_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(self._check_label, 0, Qt.AlignmentFlag.AlignTop)

        # メタ情報 (名前 + バッジ + status / provider・種類)
        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(2)

        head_layout = QHBoxLayout()
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(theme.SPACE_1)
        name_label = QLabel(info.display_name, self)
        name_label.setStyleSheet(f"font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
        head_layout.addWidget(name_label)

        badge_text = _badge_text(info)
        if badge_text:
            type_badge = QLabel(badge_text, self)
            type_badge.setStyleSheet(theme.badge_qss())
            head_layout.addWidget(type_badge)

        self._status_label = QLabel("", self)
        head_layout.addWidget(self._status_label)
        head_layout.addStretch(1)
        meta_layout.addLayout(head_layout)

        types_text = " ".join(_TYPE_LABELS[t] for t in _model_types(info))
        env_text = "Web API" if info.is_api else "ローカル"
        sub_label = QLabel(f"{_provider_label(info)} · {env_text} · {types_text}", self)
        sub_label.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
            f" color: {theme.INK_SOFT};"
        )
        meta_layout.addWidget(sub_label)
        if info.is_multimodal:
            fanout = QLabel(_MULTIMODAL_NOTE, self)
            fanout.setStyleSheet(
                f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
                f" color: {theme.INK_FAINT};"
            )
            meta_layout.addWidget(fanout)
        row_layout.addLayout(meta_layout, 1)

        # 右側: コスト + conf-min スライダー
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        cost_label = QLabel(format_per_image_cost(_cost_service.per_image_usd(info), info.is_api), self)
        cost_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        cost_label.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        right_layout.addWidget(cost_label)

        self._conf_label: QLabel | None = None
        self._conf_slider: QSlider | None = None
        if _supports_conf_min(info):
            self._conf_label = QLabel("", self)
            self._conf_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._conf_label.setStyleSheet(
                f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
                f" color: {theme.INK_SOFT};"
            )
            self._conf_slider = QSlider(Qt.Orientation.Horizontal, self)
            self._conf_slider.setObjectName("stageModelRowConf")
            self._conf_slider.setRange(0, _CONF_SLIDER_STEPS)
            self._conf_slider.setValue(round(_DEFAULT_CONF_MIN * _CONF_SLIDER_STEPS))
            self._conf_slider.setFixedWidth(140)
            self._conf_slider.valueChanged.connect(self._update_conf_label)
            self._update_conf_label()
            right_layout.addWidget(self._conf_label)
            right_layout.addWidget(self._conf_slider, 0, Qt.AlignmentFlag.AlignRight)
        row_layout.addLayout(right_layout, 0)

        self._refresh_style()

    @property
    def info(self) -> StageModelInfo:
        """この行が表すモデルのスナップショット。"""
        return self._info

    def _update_conf_label(self) -> None:
        """スライダー値に追従して conf-min 表示を更新する。"""
        value = self.confidence_value()
        if self._conf_label is not None and value is not None:
            self._conf_label.setText(f"conf min {value:.2f}")

    def confidence_value(self) -> float | None:
        """現在の conf-min 値 (0.0〜1.0)。スライダー非対応行は None。"""
        if self._conf_slider is None:
            return None
        return self._conf_slider.value() / _CONF_SLIDER_STEPS

    def is_selected(self) -> bool:
        """選択状態を返す。"""
        return self._selected

    def set_selected(self, selected: bool) -> None:
        """選択状態を設定して見た目を更新する。"""
        self._selected = selected and not self._needs_key
        self._refresh_style()

    def set_needs_key(self, needs_key: bool) -> None:
        """needs key 状態を設定する。needs key 行は選択不可で warn 表示。"""
        self._needs_key = needs_key
        if needs_key:
            self._selected = False
            self.setToolTip(_NEEDS_KEY_TOOLTIP)
        else:
            self.setToolTip("")
        self._refresh_style()

    def set_status(self, text: str, kind: theme.ChipKind) -> None:
        """status chip のテキストと配色を設定する。"""
        self._status_label.setText(text)
        self._status_label.setStyleSheet(theme.chip_qss(kind))

    def _refresh_style(self) -> None:
        """選択 / needs key 状態に応じて行の枠と背景を更新する。"""
        if self._selected:
            self.setStyleSheet(
                f"QFrame#stageModelRow {{ background-color: {theme.ACCENT_SOFT};"
                f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
                f" border-radius: {theme.RADIUS}px; }}"
            )
            self._check_label.setText("✓")
            self._check_label.setStyleSheet(
                f"background-color: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
                f" border-radius: {theme.RADIUS_BADGE}px;"
            )
        else:
            self.setStyleSheet(
                f"QFrame#stageModelRow {{ background-color: transparent;"
                f" border: {theme.BORDER_WIDTH}px solid transparent;"
                f" border-radius: {theme.RADIUS}px; }}"
            )
            self._check_label.setText("")
            border = theme.WARN_BORDER if self._needs_key else theme.LINE_STRONG
            self._check_label.setStyleSheet(
                f"background-color: {theme.CARD}; border: {theme.BORDER_WIDTH}px solid {border};"
                f" border-radius: {theme.RADIUS_BADGE}px;"
            )
        if self._conf_slider is not None:
            self._conf_slider.setVisible(self._selected and not self._needs_key)
        if self._conf_label is not None:
            self._conf_label.setVisible(self._selected and not self._needs_key)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """行クリックでトグル / 設定導線を要求する (スライダーは子が消費)。"""
        if self._needs_key:
            self.configure_requested.emit()
        else:
            self.toggle_requested.emit()
        super().mousePressEvent(event)


class StageModelPickerDialog(QDialog):
    """ステージに追加可能なモデル候補をリッチに絞り込み選択するモーダル。

    Signals:
        configure_key_requested (str): ``○ needs key`` 行クリック時に、API キーが
            必要な provider 名 (例 ``"anthropic"``) を通知する (Issue #755)。
    """

    configure_key_requested = Signal(str)

    def __init__(
        self,
        stage: PipelineStage,
        candidates: list[StageModelInfo],
        available_providers: set[str] | None = None,
        staged_count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを構築する。

        Args:
            stage: 追加先のパイプラインステージ。
            candidates: このステージに出力を届けられる未選択モデルのリスト。
            available_providers: API キー設定済み provider 集合。None の場合は
                全 provider をキー設定済み扱いにする (後方互換)。
            staged_count: ステージング中の画像枚数。> 0 のとき推定ジョブ数を
                フッタに表示する (未指定時はジョブ数を省略、後方互換)。
            parent: 親 widget。
        """
        super().__init__(parent)
        self._stage = stage
        self.setWindowTitle(f"{stage.value.upper()} のモデルを選択")

        self._candidates = list(candidates)
        self._available_providers: set[str] | None = (
            set(available_providers) if available_providers is not None else None
        )
        self._staged_count = max(0, staged_count)

        # フィルタ状態 (ステージ既定の種類を初期選択)
        self._env = _ENV_ALL
        self._provider = "all"
        self._type_token = _STAGE_TO_TYPE.get(stage, _TYPE_ALL)
        self._rec_mode = False

        # 選択集合 (litellm_model_id)。SSoT は呼び出し元だが本ダイアログ内で管理
        self._selected_ids: set[str] = set()
        self._rows: list[_ModelRow] = []

        # フィルタ UI 参照
        self._type_radios: dict[str, QRadioButton] = {}
        self._type_count_labels: dict[str, QLabel] = {}
        self._provider_buttons: dict[str, QRadioButton] = {}
        self._provider_count_labels: dict[str, QLabel] = {}
        self._env_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        if not self._candidates:
            self._build_empty_body(layout)
            return

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_presets_row())
        layout.addWidget(self._build_main_area(), 1)
        layout.addWidget(self._build_footer())

        self._rebuild_provider_radios()
        self._apply_filters()

    # --- 空候補 -------------------------------------------------------------

    def _build_empty_body(self, layout: QVBoxLayout) -> None:
        """候補ゼロ時のラベルと OK 無効化ボタンを配置する。"""
        empty_label = QLabel(_EMPTY_CANDIDATES_TEXT, self)
        empty_label.setObjectName("emptyCandidatesLabel")
        empty_label.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        layout.addWidget(empty_label)
        layout.addWidget(self._build_button_box(enable_ok=False))

    # --- ヘッダ / presets ---------------------------------------------------

    def _build_header(self) -> QWidget:
        """ステージ名とフィルタ要約を表示するヘッダ帯を構築する。"""
        header = QFrame(self)
        header.setObjectName("pickerHeader")
        header.setStyleSheet(
            f"QFrame#pickerHeader {{ background-color: {theme.PAPER_SHADE};"
            f" border-bottom: {theme.BORDER_WIDTH}px solid {theme.LINE}; }}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(theme.SPACE_4, theme.SPACE_2, theme.SPACE_4, theme.SPACE_2)
        title = QLabel(f"{self._stage.value.upper()} のモデル選択", header)
        title.setStyleSheet(f"font-weight: {theme.FONT_WEIGHT_SEMIBOLD};")
        hl.addWidget(title)
        hl.addStretch(1)
        self._filter_summary = QLabel("", header)
        self._filter_summary.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; color: {theme.INK_SOFT};"
        )
        hl.addWidget(self._filter_summary)
        return header

    def _build_presets_row(self) -> QWidget:
        """ワンクリック絞り込み preset chip 行を構築する。"""
        row = QFrame(self)
        row.setObjectName("pickerPresets")
        row.setStyleSheet(
            f"QFrame#pickerPresets {{ border-bottom: {theme.BORDER_WIDTH}px solid {theme.LINE}; }}"
        )
        hl = QHBoxLayout(row)
        hl.setContentsMargins(theme.SPACE_4, theme.SPACE_2, theme.SPACE_4, theme.SPACE_2)
        hl.setSpacing(theme.SPACE_2)
        caption = QLabel("presets:", row)
        caption.setStyleSheet(f"font-size: {theme.FONT_SIZE_SMALL}px; color: {theme.INK_SOFT};")
        hl.addWidget(caption)
        presets: tuple[tuple[str, str], ...] = (
            ("All installed", _ENV_LOCAL),
            ("Multimodal only", "multimodal"),
            ("Cheap (local)", _ENV_LOCAL),
            ("High-fidelity API", _ENV_API),
        )
        for label, action in presets:
            btn = QPushButton(label, row)
            btn.setObjectName("pickerPresetChip")
            btn.clicked.connect(lambda _checked=False, a=action: self._apply_preset(a))
            hl.addWidget(btn)
        hl.addStretch(1)
        return row

    def _apply_preset(self, action: str) -> None:
        """preset chip に応じてフィルタ + 選択を一括設定する。"""
        if action == "multimodal":
            # multimodal モデルだけを全環境から選択
            self._set_env(_ENV_ALL)
            self._rec_mode = False
            self._selected_ids = {c.litellm_model_id for c in self._candidates if c.is_multimodal}
        elif action == _ENV_LOCAL:
            self._set_env(_ENV_LOCAL)
        elif action == _ENV_API:
            self._set_env(_ENV_API)
        self._sync_selection_to_rows()
        self._apply_filters()

    # --- メインエリア -------------------------------------------------------

    def _build_main_area(self) -> QWidget:
        """左レール + モデル行リストの 2 カラム本体を構築する。"""
        container = QFrame(self)
        hl = QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self._build_left_rail(), 0)
        hl.addWidget(self._build_model_panel(), 1)
        return container

    def _build_left_rail(self) -> QWidget:
        """アノテーション種類 / Provider フィルタと出どころ説明のレールを構築する。"""
        rail = QFrame(self)
        rail.setObjectName("pickerRail")
        rail.setFixedWidth(230)
        rail.setStyleSheet(
            f"QFrame#pickerRail {{ border-right: {theme.BORDER_WIDTH}px solid {theme.LINE}; }}"
        )
        vl = QVBoxLayout(rail)
        vl.setContentsMargins(theme.SPACE_3, theme.SPACE_2, theme.SPACE_3, theme.SPACE_2)
        vl.setSpacing(theme.SPACE_1)

        vl.addWidget(self._rail_group_title("1", "アノテーション種類"))
        self._type_group = QButtonGroup(self)
        self._type_group.setExclusive(True)
        self._add_type_radio(vl, _TYPE_ALL, "すべて")
        for token in _TYPE_ORDER:
            self._add_type_radio(vl, token, _TYPE_LABELS[token])
        stage_type = _STAGE_TO_TYPE.get(self._stage, _TYPE_ALL)
        stage_type_label = "すべて" if stage_type == _TYPE_ALL else _TYPE_LABELS[stage_type]
        hint = QLabel(
            f"{self._stage.value} は既定で「{stage_type_label}」を出力できるモデルを候補に。", rail
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: {theme.FONT_SIZE_META}px; color: {theme.INK_FAINT};")
        vl.addWidget(hint)

        vl.addWidget(self._rail_group_title("2", "Provider"))
        self._provider_group = QButtonGroup(self)
        self._provider_group.setExclusive(True)
        self._provider_rail_layout = QVBoxLayout()
        self._provider_rail_layout.setContentsMargins(0, 0, 0, 0)
        self._provider_rail_layout.setSpacing(0)
        vl.addLayout(self._provider_rail_layout)

        origin = QLabel(_ORIGIN_NOTE, rail)
        origin.setObjectName("pickerOriginNote")
        origin.setWordWrap(True)
        origin.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_META}px; color: {theme.INK_SOFT};"
            f" border: {theme.BORDER_WIDTH}px dashed {theme.LINE_STRONG};"
            f" border-radius: {theme.RADIUS}px; padding: {theme.SPACE_2}px;"
            f" background-color: {theme.PAPER_SHADE};"
        )
        vl.addWidget(origin)
        vl.addStretch(1)
        return rail

    def _rail_group_title(self, number: str, title: str) -> QWidget:
        """レールのグループ見出し (番号バッジ + 大文字ラベル) を構築する。"""
        wrap = QWidget(self)
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, theme.SPACE_2, 0, theme.SPACE_1)
        hl.setSpacing(theme.SPACE_1)
        badge = QLabel(number, wrap)
        badge.setFixedSize(14, 14)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border-radius: {theme.RADIUS_CHIP}px; font-size: {theme.FONT_SIZE_META}px;"
        )
        hl.addWidget(badge)
        label = QLabel(title, wrap)
        label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_BOLD};"
            f" letter-spacing: {theme.LETTER_CAPS};"
        )
        hl.addWidget(label)
        hl.addStretch(1)
        return wrap

    def _add_type_radio(self, layout: QVBoxLayout, token: str, label: str) -> None:
        """アノテーション種類フィルタの radio 1 行を追加する。"""
        wrap = QWidget(self)
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(theme.SPACE_1)
        radio = QRadioButton(label, wrap)
        radio.setChecked(token == self._type_token)
        radio.toggled.connect(lambda checked, t=token: self._on_type_toggled(t, checked))
        self._type_group.addButton(radio)
        hl.addWidget(radio)
        hl.addStretch(1)
        count = QLabel("", wrap)
        count.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
            f" color: {theme.INK_SOFT};"
        )
        hl.addWidget(count)
        layout.addWidget(wrap)
        self._type_radios[token] = radio
        self._type_count_labels[token] = count

    def _rebuild_provider_radios(self) -> None:
        """現在の実行環境に存在する provider の radio を作り直す。"""
        for radio in self._provider_buttons.values():
            self._provider_group.removeButton(radio)
        while self._provider_rail_layout.count():
            item = self._provider_rail_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._provider_buttons.clear()
        self._provider_count_labels.clear()

        providers = ["all"]
        seen: set[str] = set()
        for info in self._candidates:
            if self._env != _ENV_ALL and not _matches_filters(info, self._env, _TYPE_ALL, "all"):
                continue
            label = _provider_label(info)
            if label not in seen:
                seen.add(label)
                providers.append(label)

        if self._provider not in providers:
            self._provider = "all"
        for provider in providers:
            self._add_provider_radio(provider)

    def _add_provider_radio(self, provider: str) -> None:
        """Provider フィルタの radio 1 行を追加する。"""
        wrap = QWidget(self)
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(theme.SPACE_1)
        radio = QRadioButton(provider, wrap)
        radio.setChecked(provider == self._provider)
        radio.toggled.connect(lambda checked, p=provider: self._on_provider_toggled(p, checked))
        self._provider_group.addButton(radio)
        hl.addWidget(radio)
        hl.addStretch(1)
        count = QLabel("", wrap)
        count.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
            f" color: {theme.INK_SOFT};"
        )
        hl.addWidget(count)
        self._provider_rail_layout.addWidget(wrap)
        self._provider_buttons[provider] = radio
        self._provider_count_labels[provider] = count

    def _build_model_panel(self) -> QWidget:
        """ツールバー + ステータス + モデル行スクロールの右パネルを構築する。"""
        panel = QFrame(self)
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        toolbar = QFrame(panel)
        toolbar.setStyleSheet(f"border-bottom: {theme.BORDER_WIDTH}px solid {theme.LINE};")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(theme.SPACE_4, theme.SPACE_2, theme.SPACE_4, theme.SPACE_2)
        tl.setSpacing(theme.SPACE_2)
        select_all_btn = QPushButton("全選択", toolbar)
        select_all_btn.clicked.connect(self._select_all_visible)
        tl.addWidget(select_all_btn)
        deselect_all_btn = QPushButton("全解除", toolbar)
        deselect_all_btn.clicked.connect(self._deselect_all_visible)
        tl.addWidget(deselect_all_btn)
        rec_btn = QPushButton("推奨選択", toolbar)
        rec_btn.setObjectName("pickerRecButton")
        rec_btn.clicked.connect(self._select_recommended)
        tl.addWidget(rec_btn)
        tl.addStretch(1)
        env_caption = QLabel("実行環境", toolbar)
        env_caption.setStyleSheet(f"font-size: {theme.FONT_SIZE_SMALL}px; color: {theme.INK_SOFT};")
        tl.addWidget(env_caption)
        tl.addWidget(self._build_env_segment(toolbar))
        vl.addWidget(toolbar)

        status = QFrame(panel)
        status.setStyleSheet(
            f"background-color: {theme.PAPER_SHADE};"
            f" border-bottom: {theme.BORDER_WIDTH}px solid {theme.LINE};"
        )
        sl = QHBoxLayout(status)
        sl.setContentsMargins(theme.SPACE_4, theme.SPACE_1, theme.SPACE_4, theme.SPACE_1)
        self._count_label = QLabel("", status)
        self._count_label.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        sl.addWidget(self._count_label)
        sl.addStretch(1)
        vl.addWidget(status)

        self._scroll = QScrollArea(panel)
        self._scroll.setObjectName("pickerScroll")
        self._scroll.setWidgetResizable(True)
        rows_host = QWidget(self._scroll)
        self._rows_layout = QVBoxLayout(rows_host)
        self._rows_layout.setContentsMargins(theme.SPACE_2, theme.SPACE_2, theme.SPACE_2, theme.SPACE_2)
        self._rows_layout.setSpacing(theme.SPACE_1)
        for info in self._candidates:
            row = _ModelRow(info, rows_host)
            row.toggle_requested.connect(lambda r=row: self._toggle_row(r))
            row.configure_requested.connect(lambda r=row: self._on_row_configure(r))
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        self._no_match_label = QLabel(_NO_MATCH_TEXT, rows_host)
        self._no_match_label.setObjectName("noMatchLabel")
        self._no_match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_match_label.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_SMALL}px; color: {theme.INK_FAINT}; padding: {theme.SPACE_4}px;"
        )
        self._no_match_label.hide()
        self._rows_layout.addWidget(self._no_match_label)
        self._rows_layout.addStretch(1)
        self._scroll.setWidget(rows_host)
        vl.addWidget(self._scroll, 1)
        return panel

    def _build_env_segment(self, parent: QWidget) -> QWidget:
        """実行環境のセグメントコントロール (排他チェック可能ボタン) を構築する。"""
        wrap = QFrame(parent)
        hl = QHBoxLayout(wrap)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        group = QButtonGroup(wrap)
        group.setExclusive(True)
        for value, label in _ENV_SEGMENTS:
            btn = QPushButton(label, wrap)
            btn.setObjectName("pickerEnvSegment")
            btn.setCheckable(True)
            btn.setChecked(value == self._env)
            btn.clicked.connect(lambda _checked=False, v=value: self._set_env(v))
            btn.setStyleSheet(
                f"QPushButton#pickerEnvSegment {{ border-radius: 0; }}"
                f" QPushButton#pickerEnvSegment:checked {{ background-color: {theme.ACCENT};"
                f" color: {theme.TEXT_ON_ACCENT}; border-color: {theme.ACCENT}; }}"
            )
            group.addButton(btn)
            hl.addWidget(btn)
            self._env_buttons[value] = btn
        return wrap

    def _build_footer(self) -> QWidget:
        """選択サマリと適用 / キャンセルボタンのフッタを構築する。"""
        footer = QFrame(self)
        footer.setStyleSheet(
            f"background-color: {theme.PAPER_SHADE}; border-top: {theme.BORDER_WIDTH}px solid {theme.LINE};"
        )
        hl = QHBoxLayout(footer)
        hl.setContentsMargins(theme.SPACE_4, theme.SPACE_2, theme.SPACE_4, theme.SPACE_2)
        self._summary_label = QLabel("", footer)
        self._summary_label.setStyleSheet(f"font-size: {theme.FONT_SIZE_SMALL}px;")
        hl.addWidget(self._summary_label)
        hl.addStretch(1)
        hl.addWidget(self._build_button_box(enable_ok=True))
        return footer

    def _build_button_box(self, enable_ok: bool) -> QDialogButtonBox:
        """適用 (Ok) / キャンセル ボタンボックスを構築する。"""
        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        ok_button = box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("適用")
            ok_button.setEnabled(enable_ok)
        cancel_button = box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("キャンセル")
        return box

    # --- フィルタ / 選択ハンドラ -------------------------------------------

    def _on_type_toggled(self, token: str, checked: bool) -> None:
        """アノテーション種類フィルタの切替を反映する。"""
        if checked and token != self._type_token:
            self._type_token = token
            self._apply_filters()

    def _on_provider_toggled(self, provider: str, checked: bool) -> None:
        """Provider フィルタの切替を反映する。"""
        if checked and provider != self._provider:
            self._provider = provider
            self._apply_filters()

    def _set_env(self, env: str) -> None:
        """実行環境を変更し、provider をリセットして radio を作り直す。"""
        if env == self._env:
            return
        self._env = env
        self._provider = "all"
        button = self._env_buttons.get(env)
        if button is not None:
            button.setChecked(True)
        self._rebuild_provider_radios()
        self._apply_filters()

    def _visible_candidates(self) -> list[StageModelInfo]:
        """現在のフィルタに一致する候補を返す。"""
        return [
            info
            for info in self._candidates
            if _matches_filters(info, self._env, self._type_token, self._provider)
        ]

    def _toggle_row(self, row: _ModelRow) -> None:
        """行の選択をトグルする (needs key 行は対象外)。"""
        if self._needs_key(row.info):
            return
        self._rec_mode = False
        model_id = row.info.litellm_model_id
        if model_id in self._selected_ids:
            self._selected_ids.discard(model_id)
        else:
            self._selected_ids.add(model_id)
        row.set_selected(model_id in self._selected_ids)
        self._update_status_and_footer()

    def _select_all_visible(self) -> None:
        """表示中の選択可能な候補をすべて選択する。"""
        self._rec_mode = False
        for info in self._visible_candidates():
            if not self._needs_key(info):
                self._selected_ids.add(info.litellm_model_id)
        self._sync_selection_to_rows()
        self._update_status_and_footer()

    def _deselect_all_visible(self) -> None:
        """表示中の候補の選択をすべて解除する。"""
        self._rec_mode = False
        for info in self._visible_candidates():
            self._selected_ids.discard(info.litellm_model_id)
        self._sync_selection_to_rows()
        self._update_status_and_footer()

    def _select_recommended(self) -> None:
        """推奨モデルを全候補から選択する。

        推奨基準: キー設定済みで選択可能なモデルのうち、ローカル ML
        (無料・常時利用可) か multimodal WebAPI (1 推論で複数ステージを充足) のもの。
        単機能の有料 API モデルはコストを考慮し自動推奨に含めない。
        """
        self._rec_mode = True
        self._selected_ids = {
            info.litellm_model_id for info in self._candidates if self._is_recommended(info)
        }
        self._sync_selection_to_rows()
        self._update_status_and_footer()

    def _is_recommended(self, info: StageModelInfo) -> bool:
        """推奨選択の対象かを判定する (:meth:`_select_recommended` 参照)。"""
        if self._needs_key(info):
            return False
        if not info.is_api:
            return True
        return info.is_multimodal

    def _on_row_configure(self, row: _ModelRow) -> None:
        """needs key 行クリックで設定導線シグナルを emit する (Issue #755)。"""
        info = row.info
        if self._needs_key(info):
            provider = required_provider_for(info.litellm_model_id, info.provider)
            self.configure_key_requested.emit(provider)

    # --- 描画更新 -----------------------------------------------------------

    def _apply_filters(self) -> None:
        """フィルタ結果を行表示・件数・status・フッタへ反映する。"""
        visible = {info.litellm_model_id for info in self._visible_candidates()}
        any_visible = False
        for row in self._rows:
            show = row.info.litellm_model_id in visible
            row.setVisible(show)
            any_visible = any_visible or show
            self._update_row_status(row)
        self._no_match_label.setVisible(not any_visible)
        self._update_counts()
        self._update_status_and_footer()

    def _update_counts(self) -> None:
        """種類フィルタ / provider フィルタの件数ラベルを更新する。"""
        for token, label in self._type_count_labels.items():
            count = sum(
                1 for info in self._candidates if _matches_filters(info, self._env, token, self._provider)
            )
            label.setText(str(count))
            radio = self._type_radios.get(token)
            if radio is not None:
                radio.setEnabled(count > 0 or token == self._type_token)
        for provider, label in self._provider_count_labels.items():
            count = sum(
                1
                for info in self._candidates
                if _matches_filters(info, self._env, self._type_token, provider)
            )
            label.setText(str(count))

    def _update_row_status(self, row: _ModelRow) -> None:
        """1 行の status chip と needs key 状態を現在のキー状況で更新する。"""
        info = row.info
        needs_key = self._needs_key(info)
        row.set_needs_key(needs_key)
        if needs_key:
            self._selected_ids.discard(info.litellm_model_id)
            row.set_status(_STATUS_NEEDS_KEY, "warn")
        elif not info.is_api:
            row.set_status(_STATUS_INSTALLED, "ok")
        else:
            row.set_status(_STATUS_API_READY, "ok")
        row.set_selected(info.litellm_model_id in self._selected_ids)

    def _sync_selection_to_rows(self) -> None:
        """選択集合を全行の見た目へ反映する。"""
        for row in self._rows:
            row.set_selected(row.info.litellm_model_id in self._selected_ids)

    def _update_status_and_footer(self) -> None:
        """選択数・フィルタ要約・フッタサマリを更新する。"""
        selected = len(self._selected_ids)
        visible = len(self._visible_candidates())
        rec_suffix = " (推奨)" if self._rec_mode else ""
        self._count_label.setText(f"選択数: {selected}{rec_suffix} · 候補 {visible} 件")
        type_label = "全種類" if self._type_token == _TYPE_ALL else _TYPE_LABELS[self._type_token]
        self._filter_summary.setText(f"フィルタ: {_ENV_LABELS[self._env]} / {type_label}")
        summary = f"{self._stage.value.upper()} に {selected} モデル選択中"
        if self._staged_count > 0:
            summary += f" · {selected} × {self._staged_count} = {selected * self._staged_count} jobs"
        self._summary_label.setText(summary)

    # --- キー状態 -----------------------------------------------------------

    def _needs_key(self, info: StageModelInfo) -> bool:
        """API キー未設定で実行できない WebAPI モデルか判定する (Issue #755)。"""
        if not info.is_api:
            return False
        if self._available_providers is None:
            return False
        provider = required_provider_for(info.litellm_model_id, info.provider)
        return provider not in self._available_providers

    def refresh_key_status(self, available_providers: set[str]) -> None:
        """API キー設定状況を再評価して全行の status を更新する (Issue #755)。

        キー保存後に呼び出すと ``○ needs key`` 行が ``● API ready`` に変わり、
        選択可能になる (アプリ再起動不要)。

        Args:
            available_providers: 最新の API キー設定済み provider 集合。
        """
        self._available_providers = set(available_providers)
        if self._rows:
            self._apply_filters()

    # --- 結果取得 -----------------------------------------------------------

    def selected_model_ids(self) -> list[str]:
        """選択済み候補の litellm_model_id を候補順で返す。"""
        return [c.litellm_model_id for c in self._candidates if c.litellm_model_id in self._selected_ids]

    def confidence_thresholds(self) -> dict[str, float]:
        """選択済みかつ conf-min 対応モデルの閾値 (0.0〜1.0) を返す。

        呼び出し元が conf 閾値を必要としない場合は無視してよい (後方互換)。

        Returns:
            ``{litellm_model_id: conf_min}`` の辞書。スライダー非対応 / 未選択の
            モデルは含まない。
        """
        thresholds: dict[str, float] = {}
        for row in self._rows:
            if not row.is_selected():
                continue
            value = row.confidence_value()
            if value is not None:
                thresholds[row.info.litellm_model_id] = value
        return thresholds
