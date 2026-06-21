"""
Rating/Score Edit Widget - Rating/Score編集ウィジェット

選択画像のRating/Scoreを編集するための専用ウィジェット。
MainWindow右パネルのタブとして配置され、単一画像の評価編集を担当。

主要機能:
- AI セクション (読み取り専用): モデル推論の rating / score を併記
- 人間セクション (手動編集): Rating (PG, PG-13, R, X, XXX) の選択 + Score スライダー
- 保存ボタンによる即時更新

設計 SSoT:
- claude.ai/design 調整版 SearchScreen.jsx の「評価・スコア編集」カード (Issue #812)
- AI 値と手動値を source 分離して 1 枚のカードに 2 段併記する。
- AI と手動 score が異なる場合は accent で差分 (Δ) を表示する。

アーキテクチャ:
- QTabWidget の タブ2 (Rating/Score編集) に配置
- DatasetStateManager から画像データを受信
- 保存時に rating_changed/score_changed シグナルを発行
- MainWindow が ImageDBWriteService 経由で保存処理を実行
"""

from typing import Any, ClassVar

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.RatingScoreEditWidget_ui import Ui_RatingScoreEditWidget
from ...utils.log import logger
from .. import theme

# Rating の正準順序 (PG が最も穏当、XXX が最も露骨)
_RATING_ORDER: tuple[str, ...] = ("PG", "PG-13", "R", "X", "XXX")


def _segment_button_qss(active: bool) -> str:
    """人間レーティング SegmentedControl のセグメント 1 個分 QSS (ADR 0073)。

    active セグメントは accent-soft 塗り + accent border、非 active は CARD 地。

    Args:
        active: そのセグメントが選択中なら True。

    Returns:
        QPushButton に適用する QSS 文字列。
    """
    if active:
        return (
            f"QPushButton {{ background-color: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 2px 10px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
    return (
        f"QPushButton {{ background-color: {theme.CARD}; color: {theme.INK_SOFT};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; border-radius: {theme.RADIUS_BADGE}px;"
        f" padding: 2px 10px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
    )


def _ai_rating_chip_qss(active: bool) -> str:
    """AI セクションの読み取り専用 rating chip QSS。

    該当値のみ paper-shade 地 + line-strong border で強調し、非該当は ink-faint。

    Args:
        active: AI 推論値がそのレーティングなら True。

    Returns:
        QLabel に適用する QSS 文字列。
    """
    if active:
        return (
            f"QLabel {{ background-color: {theme.PAPER_SHADE}; color: {theme.INK};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE_STRONG};"
            f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 8px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD}; }}"
        )
    return (
        f"QLabel {{ background-color: transparent; color: {theme.INK_FAINT};"
        f" border: {theme.BORDER_WIDTH}px solid transparent;"
        f" border-radius: {theme.RADIUS_BADGE}px; padding: 1px 8px;"
        f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
    )


def _ai_score_bar_qss() -> str:
    """AI score の読み取り専用バー QSS (ink-faint fill)。"""
    return (
        f"QProgressBar {{ background-color: {theme.PAPER_SHADE};"
        f" border: {theme.BORDER_WIDTH}px solid {theme.LINE}; border-radius: {theme.RADIUS_BADGE}px; }}"
        f" QProgressBar::chunk {{ background-color: {theme.INK_FAINT};"
        f" border-radius: {theme.RADIUS_BADGE}px; }}"
    )


def _caption_qss() -> str:
    """補助キャプション (ink-soft / small) の QSS。"""
    return f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"


def _score_value_qss() -> str:
    """score 数値表示 (mono) の QSS。"""
    return (
        f"color: {theme.INK}; font-family: {theme.FONT_MONO_CSS};"
        f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_MEDIUM};"
    )


def _delta_qss() -> str:
    """手動 score と AI の差分 (Δ) 表示 (accent / mono) の QSS。"""
    return (
        f"color: {theme.ACCENT}; font-family: {theme.FONT_MONO_CSS};"
        f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: {theme.FONT_WEIGHT_SEMIBOLD};"
    )


def _footnote_qss() -> str:
    """カード末尾の注記 (mono / faint) の QSS。"""
    return (
        f"color: {theme.INK_FAINT}; font-family: {theme.FONT_MONO_CSS};"
        f" font-size: {theme.FONT_SIZE_SMALL}px;"
    )


class _RatingSegmentedControl(QWidget):
    """人間レーティング用 SegmentedControl (ADR 0073)。

    PG/PG-13/R/X/XXX を排他選択する checkable ``QPushButton`` 行。内部状態を
    持たず、選択変更を ``rating_selected`` シグナルで通知する。SSoT は呼び出し側
    (RatingScoreEditWidget の comboBoxRating) に委ねる。
    """

    rating_selected = Signal(str)  # ユーザーがセグメントを選択した

    def __init__(self, ratings: tuple[str, ...], parent: QWidget | None = None) -> None:
        """セグメント行を構築する。

        Args:
            ratings: セグメントに並べるレーティング値の順序付きタプル。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for rating in ratings:
            button = QPushButton(rating, self)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(_segment_button_qss(False))
            button.clicked.connect(lambda _checked=False, value=rating: self.rating_selected.emit(value))
            self._group.addButton(button)
            self._buttons[rating] = button
            layout.addWidget(button)
        layout.addStretch(1)

    def set_active(self, rating: str | None) -> None:
        """選択状態を更新する (シグナルは発行しない)。

        Args:
            rating: 強調するレーティング値。None なら全て非選択。
        """
        for value, button in self._buttons.items():
            active = value == rating
            blocked = button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(blocked)
            button.setStyleSheet(_segment_button_qss(active))


class RatingScoreEditWidget(QWidget):
    """
    Rating/Score編集ウィジェット

    選択画像の Rating/Score を AI (読み取り専用) と人間 (手動編集) の 2 段で併記。
    SelectedImageDetailsWidget から分離された編集専用コンポーネント。

    データフロー:
    1. populate_from_image_data() でフォームフィールドを入力
    2. ユーザーが編集
    3. Save クリック -> rating_changed/score_changed シグナル発行
    4. MainWindow が ImageDBWriteService 経由で DB 更新

    UI構成:
    - groupBoxRatingScore: AI セクション + 区切り線 + 人間セクション + 注記
    - comboBoxRating: 人間レーティングの SSoT (非表示、SegmentedControl が駆動)
    - sliderScore / labelScoreValue: 人間スコア編集
    - pushButtonSave: 保存ボタン

    型安全性:
    - int | None による画像ID管理
    - シグナルは (image_id, value) の型安全なペイロード
    """

    # シグナル
    rating_changed = Signal(int, str)  # (image_id, rating) - 単一選択時
    score_changed = Signal(int, int)  # (image_id, score) - 単一選択時
    batch_rating_changed = Signal(list, str)  # (image_ids, rating) - 複数選択時
    batch_score_changed = Signal(list, int)  # (image_ids, score) - 複数選択時

    _NO_RATING_TEXT = "----"
    _VALID_RATINGS: ClassVar[set[str]] = set(_RATING_ORDER)

    def __init__(self, parent: QWidget | None = None):
        """
        RatingScoreEditWidget 初期化

        UIコンポーネントの初期化、内部状態の設定。

        Args:
            parent: 親ウィジェット

        初期状態:
            - _current_image_id: None
            - UI: 空表示状態
        """
        super().__init__(parent)

        # 内部状態
        self._current_image_id: int | None = None
        self._selected_image_ids: list[int] = []  # 複数選択時のIDリスト
        self._is_batch_mode: bool = False  # バッチモードフラグ
        # AI 推論値 (read-only セクション用)。manual との差分計算に使う
        self._ai_rating: str | None = None
        self._ai_score_ui: int | None = None
        # 手動スコアが設定済みか (Issue #825)。未設定 (None) のときは slider が中立位置でも
        # 「AI と差分あり」と誤判定しないよう、Δ/MANUAL_EDIT 判定をスキップする。
        self._manual_score_set: bool = False

        # UI設定
        self.ui = Ui_RatingScoreEditWidget()
        self.ui.setupUi(self)
        self._initialize_rating_items()
        self._build_two_tier_card()

        # スライダーと値ラベルの連動 (セクション構築後に接続)
        self.ui.sliderScore.valueChanged.connect(self._on_slider_value_changed)
        self._rating_segmented.rating_selected.connect(self._on_segment_rating_selected)

        # 初期表示は空 (AI 値なし)
        self._render_ai_section(None, None)
        self._update_manual_edit_state()

        logger.info("RatingScoreEditWidget initialized")

    @Slot(int)
    def _on_slider_value_changed(self, value: int) -> None:
        """
        スライダー値変更ハンドラー

        スライダーの値が変更されたときに、値表示ラベルと AI との差分表示を更新。

        Args:
            value: 新しいスコア値（内部値 0-1000）
        """
        # ユーザーがスライダーを動かした = 手動スコアが設定された (Issue #825)
        self._manual_score_set = True
        self.ui.labelScoreValue.setText(f"{value / 100.0:.2f}")
        self._update_manual_edit_state()

    @Slot(str)
    def _on_segment_rating_selected(self, rating: str) -> None:
        """人間レーティングのセグメント選択を SSoT (comboBoxRating) へ反映する。"""
        index = self.ui.comboBoxRating.findText(rating)
        if index >= 0:
            self.ui.comboBoxRating.setCurrentIndex(index)
        # チップ QSS は :checked を持たない静的スタイルのため、選択ハイライトを
        # 明示的に再適用する (#829: クリックしても見た目が変わらない問題)。
        self._rating_segmented.set_active(rating)
        # 手動でレーティングを付けたら手動スコア扱いにはしないが、手動編集状態を更新
        self._update_manual_edit_state()

    def _build_two_tier_card(self) -> None:
        """AI / 人間の 2 段カードを groupBox 内に再構築する。

        既存 .ui の grid レイアウトは使わず、既存 widget (combo/slider/value/save)
        は新レイアウトへ移送して SSoT を保つ。combo は SegmentedControl の裏に
        隠す。labelRating / labelScore など未使用 widget は破棄する。
        """
        group = self.ui.groupBoxRatingScore

        # 残す widget を旧レイアウトから取り外し group 直下へ退避する
        self.ui.horizontalLayoutScore.removeWidget(self.ui.sliderScore)
        self.ui.horizontalLayoutScore.removeWidget(self.ui.labelScoreValue)
        self.ui.gridLayoutRatingScore.removeWidget(self.ui.comboBoxRating)
        self.ui.horizontalLayoutButtons.removeWidget(self.ui.pushButtonSave)
        for widget in (
            self.ui.comboBoxRating,
            self.ui.sliderScore,
            self.ui.labelScoreValue,
            self.ui.pushButtonSave,
        ):
            widget.setParent(group)

        # 未使用ラベルを破棄
        self.ui.labelRating.deleteLater()
        self.ui.labelScore.deleteLater()

        # 旧トップレベルレイアウトの残骸 (ボタン行 / 余白) を撤去
        self.ui.verticalLayoutMain.removeItem(self.ui.horizontalLayoutButtons)
        if hasattr(self.ui, "verticalSpacer"):
            self.ui.verticalLayoutMain.removeItem(self.ui.verticalSpacer)

        # 旧 grid レイアウトを group から切り離す (子の未使用 widget ごと破棄)
        old_layout = group.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)

        # combo は SegmentedControl が SSoT を駆動するため非表示
        self.ui.comboBoxRating.setVisible(False)

        # 新しいカード本体
        content = QVBoxLayout(group)
        content.setContentsMargins(10, 6, 10, 8)
        content.setSpacing(6)
        content.addLayout(self._build_ai_section())
        content.addWidget(self._build_divider())
        content.addLayout(self._build_human_section())
        content.addWidget(self._build_footnote())

        self.ui.verticalLayoutMain.setContentsMargins(0, 0, 0, 0)
        self.ui.verticalLayoutMain.setSpacing(6)
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        group.setMinimumWidth(0)

    def _build_ai_section(self) -> QVBoxLayout:
        """AI (読み取り専用) セクションを構築して返す。"""
        section = QVBoxLayout()
        section.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        ai_badge = QLabel("AI", self)
        ai_badge.setStyleSheet(theme.badge_qss())
        ai_caption = QLabel("モデル推論値 · 読み取り専用", self)
        ai_caption.setStyleSheet(_caption_qss())
        header.addWidget(ai_badge)
        header.addWidget(ai_caption)
        header.addStretch(1)
        section.addLayout(header)

        rating_row = QHBoxLayout()
        rating_row.setSpacing(4)
        self._ai_rating_chips: dict[str, QLabel] = {}
        for rating in _RATING_ORDER:
            chip = QLabel(rating, self)
            chip.setStyleSheet(_ai_rating_chip_qss(False))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ai_rating_chips[rating] = chip
            rating_row.addWidget(chip)
        rating_row.addStretch(1)
        section.addLayout(rating_row)

        score_row = QHBoxLayout()
        score_row.setSpacing(8)
        self._ai_score_bar = QProgressBar(self)
        self._ai_score_bar.setMinimum(0)
        self._ai_score_bar.setMaximum(1000)
        self._ai_score_bar.setValue(0)
        self._ai_score_bar.setTextVisible(False)
        self._ai_score_bar.setFixedHeight(8)
        self._ai_score_bar.setStyleSheet(_ai_score_bar_qss())
        self._ai_score_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ai_score_value = QLabel("--", self)
        self._ai_score_value.setStyleSheet(_score_value_qss())
        self._ai_score_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._ai_score_value.setMinimumWidth(40)
        score_row.addWidget(self._ai_score_bar)
        score_row.addWidget(self._ai_score_value)
        section.addLayout(score_row)

        return section

    def _build_divider(self) -> QFrame:
        """AI / 人間セクションを分ける区切り線を返す。"""
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {theme.LINE}; border: none;")
        return divider

    def _build_human_section(self) -> QVBoxLayout:
        """人間 (手動編集) セクションを構築して返す。"""
        section = QVBoxLayout()
        section.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        human_badge = QLabel("✎ 人間", self)
        human_badge.setStyleSheet(theme.badge_qss())
        human_caption = QLabel("手動レーティング・スコア", self)
        human_caption.setStyleSheet(_caption_qss())
        header.addWidget(human_badge)
        header.addWidget(human_caption)
        header.addStretch(1)
        self._manual_edit_chip = QLabel("MANUAL_EDIT", self)
        self._manual_edit_chip.setStyleSheet(theme.chip_qss("accent"))
        self._manual_edit_chip.setVisible(False)
        header.addWidget(self._manual_edit_chip)
        section.addLayout(header)

        # 人間レーティング: SegmentedControl (comboBoxRating を駆動)
        self._rating_segmented = _RatingSegmentedControl(_RATING_ORDER, self)
        section.addWidget(self._rating_segmented)

        score_row = QHBoxLayout()
        score_row.setSpacing(8)
        self.ui.sliderScore.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ui.labelScoreValue.setStyleSheet(_score_value_qss())
        self._delta_label = QLabel("", self)
        self._delta_label.setStyleSheet(_delta_qss())
        self._delta_label.setVisible(False)
        score_row.addWidget(self.ui.sliderScore)
        score_row.addWidget(self.ui.labelScoreValue)
        score_row.addWidget(self._delta_label)
        section.addLayout(score_row)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(self.ui.pushButtonSave)
        section.addLayout(save_row)

        return section

    def _build_footnote(self) -> QLabel:
        """カード末尾の注記ラベルを構築して返す。"""
        footnote = QLabel(
            "quality_score 0–10（ADR 0029）· AI と source 分離 · 手動補正は is_edited_manually",
            self,
        )
        footnote.setStyleSheet(_footnote_qss())
        footnote.setWordWrap(True)
        return footnote

    def _render_ai_section(self, ai_rating: str | None, ai_score_ui: int | None) -> None:
        """AI セクションの読み取り専用表示を更新する。

        Args:
            ai_rating: AI 推論レーティング (PG/PG-13/R/X/XXX)。未取得は None。
            ai_score_ui: AI スコアの UI 値 (0-1000)。未取得は None。
        """
        self._ai_rating = ai_rating if ai_rating in self._VALID_RATINGS else None
        self._ai_score_ui = ai_score_ui

        for rating, chip in self._ai_rating_chips.items():
            chip.setStyleSheet(_ai_rating_chip_qss(rating == self._ai_rating))

        if ai_score_ui is not None:
            self._ai_score_bar.setValue(ai_score_ui)
            self._ai_score_value.setText(f"{ai_score_ui / 100.0:.2f}")
        else:
            self._ai_score_bar.setValue(0)
            self._ai_score_value.setText("--")

    def _update_manual_edit_state(self) -> None:
        """手動値が AI と異なるかを判定し MANUAL_EDIT chip と Δ 表示を更新する。"""
        manual_rating = self.ui.comboBoxRating.currentText()
        manual_score_ui = self.ui.sliderScore.value()

        rating_edited = manual_rating in self._VALID_RATINGS and manual_rating != self._ai_rating
        # 手動スコア未設定 (Issue #825) のときは slider が中立位置でも「編集済み」扱いしない
        score_edited = (
            self._manual_score_set
            and self._ai_score_ui is not None
            and manual_score_ui != self._ai_score_ui
        )
        self._manual_edit_chip.setVisible(rating_edited or score_edited)

        if self._manual_score_set and self._ai_score_ui is not None:
            delta = (manual_score_ui - self._ai_score_ui) / 100.0
            if abs(delta) >= 0.005:
                self._delta_label.setText(f"Δ {delta:+.2f} vs AI")
                self._delta_label.setVisible(True)
            else:
                self._delta_label.setVisible(False)
        else:
            self._delta_label.setVisible(False)

    @staticmethod
    def _ai_score_db_to_ui(value: Any) -> int | None:
        """AI スコアの DB 値 (0.0-10.0 または 0-1000) を UI 値 (0-1000) に変換する。

        Args:
            value: DB から渡されたスコア値。数値でなければ None を返す。

        Returns:
            UI 値 (0-1000)。変換不能なら None。
        """
        if not isinstance(value, (int, float)):
            return None
        return int(value * 100) if value <= 10.0 else int(value)

    def _initialize_rating_items(self) -> None:
        """rating comboboxに未設定用プレースホルダを先頭に追加する。"""
        if self.ui.comboBoxRating.findText(self._NO_RATING_TEXT) == -1:
            self.ui.comboBoxRating.insertItem(0, self._NO_RATING_TEXT)

        # 既定表示は未設定
        index = self.ui.comboBoxRating.findText(self._NO_RATING_TEXT)
        if index >= 0:
            self.ui.comboBoxRating.setCurrentIndex(index)

    def _set_rating_text(self, rating: Any) -> None:
        """コンボボックスへRating値を反映（未設定/不正値は`----`にフォールバック）。

        SSoT である comboBoxRating を更新後、SegmentedControl の選択状態も同期する。
        """
        normalized = rating if isinstance(rating, str) and rating.strip() else self._NO_RATING_TEXT
        if normalized in self._VALID_RATINGS:
            index = self.ui.comboBoxRating.findText(normalized)
            if index >= 0:
                self.ui.comboBoxRating.setCurrentIndex(index)
                self._rating_segmented.set_active(normalized)
                return

        index = self.ui.comboBoxRating.findText(self._NO_RATING_TEXT)
        if index >= 0:
            self.ui.comboBoxRating.setCurrentIndex(index)
        self._rating_segmented.set_active(None)

    @Slot(dict)
    def populate_from_image_data(self, image_data: dict[str, Any]) -> None:
        """
        画像データからフォームフィールドを入力

        指定された画像データをフォームに反映し、編集開始状態にする。

        Args:
            image_data: 画像メタデータ辞書
                - id: 画像ID (int)
                - rating: 手動編集の初期 Rating 値 (str, optional)
                - score: Score 値 (DB値 0.0-10.0 または UI値 0-1000)
                - score_value: Score 値 (DB値 0.0-10.0、優先的に使用)
                - ai_rating: AI 推論 Rating 値 (str, optional)
                - ai_score_value: AI 推論 Score 値 (DB値 0.0-10.0, optional)

        処理:
            1. image_id の保存
            2. DB値（0.0-10.0）→ UI値（0-1000）の変換
            3. UI フィールドへの値設定
            4. AI セクション (read-only) の描画と手動差分判定
        """
        logger.trace(f"populate_from_image_data called with image_id={image_data.get('id')}")

        # image_id を保存
        self._current_image_id = image_data.get("id")

        # シグナルをブロックして UI を更新 (自動発火を防ぐ)
        self.ui.comboBoxRating.blockSignals(True)
        self.ui.sliderScore.blockSignals(True)

        # UI フィールドに値を設定
        self._set_rating_text(image_data.get("rating"))

        # Score値の変換処理
        # Repository層からは "score_value" (DB値 0.0-10.0) が返される
        # UI層では 0-1000 の整数値で扱う
        # Issue #825: 人間 (手動) スコアが None のときは未設定として "--" 表示にする
        # (slider は中立位置に置き、ユーザーがドラッグして初めて手動値が確定する)。
        score_db = image_data.get("score_value", image_data.get("score"))
        if isinstance(score_db, (int, float)):
            # DB値（0.0-10.0）→ UI値（0-1000）に変換
            if score_db <= 10.0:
                # DB値と判断（0.0-10.0範囲）
                score_ui = int(score_db * 100)
            else:
                # すでにUI値（0-1000範囲）
                score_ui = int(score_db)
            self._manual_score_set = True
            self.ui.sliderScore.setValue(score_ui)
            self.ui.labelScoreValue.setText(f"{score_ui / 100.0:.2f}")
        else:
            self._manual_score_set = False
            score_ui = 500  # 中立位置 (未設定)
            self.ui.sliderScore.setValue(score_ui)
            self.ui.labelScoreValue.setText("--")

        # シグナルのブロックを解除
        self.ui.comboBoxRating.blockSignals(False)
        self.ui.sliderScore.blockSignals(False)

        # AI セクション (read-only) の描画。未指定時は手動値と同じソースへフォールバック
        ai_rating = image_data.get("ai_rating", image_data.get("rating"))
        ai_score_db = image_data.get("ai_score_value", image_data.get("score_value"))
        ai_normalized = (
            ai_rating if isinstance(ai_rating, str) and ai_rating in self._VALID_RATINGS else None
        )
        self._render_ai_section(ai_normalized, self._ai_score_db_to_ui(ai_score_db))
        self._update_manual_edit_state()

        # バッチモードを解除
        self._is_batch_mode = False
        self._selected_image_ids = []

        logger.trace(
            f"Form populated for image_id={self._current_image_id}: "
            f"DB score={score_db}, UI score={score_ui}"
        )

    def populate_from_selection(self, image_ids: list[int], db_manager: Any) -> None:
        """
        複数選択時のフォームフィールドを入力（バッチモード）

        全選択画像のRating/Scoreを取得し、共通値のみ表示、異なる場合は「--」。

        Args:
            image_ids: 選択画像IDリスト
            db_manager: ImageDatabaseManager インスタンス（メタデータ取得用）

        処理:
            1. 全画像のメタデータを取得
            2. Rating/Scoreの共通値を判定
            3. 共通値があれば表示、なければプレースホルダー「--」
            4. 「X件選択中」ラベル表示
            5. バッチモードフラグを有効化
        """
        logger.debug(f"populate_from_selection called with {len(image_ids)} images")

        if not image_ids:
            logger.warning("Empty image_ids for populate_from_selection")
            return

        self._is_batch_mode = True
        self._selected_image_ids = image_ids.copy()
        self._current_image_id = None  # バッチモードでは単一IDなし

        # シグナルをブロックして UI を更新
        self.ui.comboBoxRating.blockSignals(True)
        self.ui.sliderScore.blockSignals(True)

        # 全画像のメタデータを取得
        ratings: set[str] = set()
        scores: set[float] = set()

        for image_id in image_ids:
            metadata = db_manager.image_repo.get_image_metadata(image_id)
            if metadata:
                rating = metadata.get("rating")
                if rating:
                    ratings.add(rating)

                score_value = metadata.get("score_value")
                if score_value is not None:
                    scores.add(float(score_value))

        # 共通値判定: Rating
        if len(ratings) == 1:
            # 全画像が同じRating
            common_rating = next(iter(ratings))
            self._set_rating_text(common_rating)
        else:
            # 異なるRatingまたは値なし → プレースホルダー
            self._set_rating_text(None)

        # 共通値判定: Score
        if len(scores) == 1:
            # 全画像が同じScore
            common_score_db = next(iter(scores))
            score_ui = int(common_score_db * 100)
            self._manual_score_set = True
            self.ui.sliderScore.setValue(score_ui)
            self.ui.labelScoreValue.setText(f"{score_ui / 100.0:.2f}")
        else:
            # 異なるScoreまたは値なし → デフォルト値
            self._manual_score_set = True
            self.ui.sliderScore.setValue(500)
            self.ui.labelScoreValue.setText("5.00")

        # シグナルのブロックを解除
        self.ui.comboBoxRating.blockSignals(False)
        self.ui.sliderScore.blockSignals(False)

        # バッチでは AI 推論値は単一に定まらないため AI セクションを空表示にする
        self._render_ai_section(None, None)
        self._update_manual_edit_state()

        logger.info(
            f"Batch mode activated: {len(image_ids)} images, "
            f"common_rating={'Yes' if len(ratings) == 1 else 'No'}, "
            f"common_score={'Yes' if len(scores) == 1 else 'No'}"
        )

    @Slot()
    def _on_save_clicked(self) -> None:
        """
        Save ボタンクリックハンドラ (Qt Designer 自動接続スロット)

        バッチモードかどうかで分岐し、適切なシグナルを発行。

        単一選択時: rating_changed/score_changed シグナル発行
        複数選択時: batch_rating_changed/batch_score_changed シグナル発行

        Rating が未設定プレースホルダ (`----`) の場合は「Rating 変更なし」と
        みなし、rating シグナルを発行しない。意図しない Rating 書き込みと
        書き込み層での無効値リジェクト (偽の ERROR ログ) を防ぐ。
        """
        rating = self.ui.comboBoxRating.currentText()
        score = self.ui.sliderScore.value()
        # プレースホルダ選択時は Rating 変更なし扱い
        rating_changed = rating in self._VALID_RATINGS

        if self._is_batch_mode:
            # バッチモード: 複数画像を一括更新
            if not self._selected_image_ids:
                logger.warning("Save clicked in batch mode but no images selected")
                return

            logger.info(
                f"Batch save requested: {len(self._selected_image_ids)} images, "
                f"rating={rating if rating_changed else '(unchanged)'}, score={score}"
            )

            # バッチシグナルを発行
            if rating_changed:
                self.batch_rating_changed.emit(self._selected_image_ids, rating)
            self.batch_score_changed.emit(self._selected_image_ids, score)

        else:
            # 単一選択モード: 従来の動作
            if self._current_image_id is None:
                logger.warning("Save clicked but no image is loaded")
                return

            logger.info(
                f"Save requested for image_id={self._current_image_id}, "
                f"rating={rating if rating_changed else '(unchanged)'}, score={score}"
            )

            # 単一画像シグナルを発行
            if rating_changed:
                self.rating_changed.emit(self._current_image_id, rating)
            self.score_changed.emit(self._current_image_id, score)
