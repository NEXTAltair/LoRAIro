"""
Rating/Score Edit Widget - Rating/Score編集ウィジェット

選択画像のRating/Scoreを編集するための専用ウィジェット。
MainWindow右パネルのタブとして配置され、単一画像の評価編集を担当。

主要機能:
- Rating (PG, PG-13, R, X, XXX) の選択
- Score (0-1000) の数値入力
- 保存ボタンによる即時更新

アーキテクチャ:
- QTabWidget の タブ2 (Rating/Score編集) に配置
- DatasetStateManager から画像データを受信
- 保存時に rating_changed/score_changed シグナルを発行
- MainWindow が ImageDBWriteService 経由で保存処理を実行
"""

from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...gui.designer.RatingScoreEditWidget_ui import Ui_RatingScoreEditWidget
from ...utils.log import logger


class RatingScoreEditWidget(QWidget):
    """
    Rating/Score編集ウィジェット

    選択画像の Rating/Score を専用フォームで編集。
    SelectedImageDetailsWidget から分離された編集専用コンポーネント。

    データフロー:
    1. populate_from_image_data() でフォームフィールドを入力
    2. ユーザーが編集
    3. Save クリック -> rating_changed/score_changed シグナル発行
    4. MainWindow が ImageDBWriteService 経由で DB 更新

    UI構成:
    - groupBoxRatingScore: Rating combobox + Score spinbox
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
        logger.debug("RatingScoreEditWidget.__init__() called")

        # 内部状態
        self._current_image_id: int | None = None
        self._selected_image_ids: list[int] = []  # 複数選択時のIDリスト
        self._is_batch_mode: bool = False  # バッチモードフラグ

        # UI設定
        self.ui = Ui_RatingScoreEditWidget()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]
        self._apply_compact_layout()

        # スライダーと値ラベルの連動
        self.ui.sliderScore.valueChanged.connect(self._on_slider_value_changed)

        logger.info("RatingScoreEditWidget initialized")

    @Slot(int)
    def _on_slider_value_changed(self, value: int) -> None:
        """
        スライダー値変更ハンドラー

        スライダーの値が変更されたときに、値表示ラベルを更新。

        Args:
            value: 新しいスコア値（内部値 0-1000）
        """
        self.ui.labelScoreValue.setText(f"{value / 100.0:.2f}")

    def _apply_compact_layout(self) -> None:
        """コンパクトで揃った配置に調整する。"""
        self.ui.verticalLayoutMain.setContentsMargins(0, 0, 0, 0)
        self.ui.verticalLayoutMain.setSpacing(6)
        self.ui.groupBoxRatingScore.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ui.groupBoxRatingScore.setMinimumWidth(0)

        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.ui.labelRating.setAlignment(align)
        self.ui.labelScore.setAlignment(align)

        label_width = max(
            self.ui.labelRating.fontMetrics().horizontalAdvance(self.ui.labelRating.text()),
            self.ui.labelScore.fontMetrics().horizontalAdvance(self.ui.labelScore.text()),
        )
        label_width += 8
        self.ui.labelRating.setMinimumWidth(label_width)
        self.ui.labelScore.setMinimumWidth(label_width)

        if hasattr(self.ui, "horizontalLayoutButtons"):
            self.ui.horizontalLayoutButtons.removeWidget(self.ui.pushButtonSave)
            if hasattr(self.ui, "horizontalSpacer"):
                self.ui.horizontalLayoutButtons.removeItem(self.ui.horizontalSpacer)
            self.ui.verticalLayoutMain.removeItem(self.ui.horizontalLayoutButtons)

        self.ui.gridLayoutRatingScore.addWidget(
            self.ui.pushButtonSave, 2, 1, 1, 1, alignment=Qt.AlignmentFlag.AlignRight
        )

        if hasattr(self.ui, "verticalSpacer"):
            self.ui.verticalLayoutMain.removeItem(self.ui.verticalSpacer)
            self.ui.verticalSpacer.changeSize(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

    @Slot(dict)
    def populate_from_image_data(self, image_data: dict[str, Any]) -> None:
        """
        画像データからフォームフィールドを入力

        指定された画像データをフォームに反映し、編集開始状態にする。

        Args:
            image_data: 画像メタデータ辞書
                - id: 画像ID (int)
                - rating: Rating 値 (str, optional)
                - score: Score 値 (DB値 0.0-10.0 または UI値 0-1000)
                - score_value: Score 値 (DB値 0.0-10.0、優先的に使用)

        処理:
            1. image_id の保存
            2. DB値（0.0-10.0）→ UI値（0-1000）の変換
            3. UI フィールドへの値設定
        """
        logger.debug(f"populate_from_image_data called with image_id={image_data.get('id')}")

        # image_id を保存
        self._current_image_id = image_data.get("id")

        # シグナルをブロックして UI を更新 (自動発火を防ぐ)
        self.ui.comboBoxRating.blockSignals(True)
        self.ui.sliderScore.blockSignals(True)

        # UI フィールドに値を設定
        rating = image_data.get("rating", "PG-13")
        if rating in ["PG", "PG-13", "R", "X", "XXX"]:
            index = self.ui.comboBoxRating.findText(rating)
            if index >= 0:
                self.ui.comboBoxRating.setCurrentIndex(index)

        # Score値の変換処理
        # Repository層からは "score_value" (DB値 0.0-10.0) が返される
        # UI層では 0-1000 の整数値で扱う
        score_db = image_data.get("score_value", image_data.get("score", 5.0))
        if isinstance(score_db, (int, float)):
            # DB値（0.0-10.0）→ UI値（0-1000）に変換
            if score_db <= 10.0:
                # DB値と判断（0.0-10.0範囲）
                score_ui = int(score_db * 100)
            else:
                # すでにUI値（0-1000範囲）
                score_ui = int(score_db)
        else:
            score_ui = 500  # デフォルト値

        self.ui.sliderScore.setValue(score_ui)
        self.ui.labelScoreValue.setText(f"{score_ui / 100.0:.2f}")

        # シグナルのブロックを解除
        self.ui.comboBoxRating.blockSignals(False)
        self.ui.sliderScore.blockSignals(False)

        # バッチモードを解除
        self._is_batch_mode = False
        self._selected_image_ids = []

        logger.debug(
            f"Form populated for image_id={self._current_image_id}: "
            f"DB score={score_db:.2f}, UI score={score_ui}"
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
            metadata = db_manager.repository.get_image_metadata(image_id)
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
            index = self.ui.comboBoxRating.findText(common_rating)
            if index >= 0:
                self.ui.comboBoxRating.setCurrentIndex(index)
        else:
            # 異なるRatingまたは値なし → プレースホルダー
            self.ui.comboBoxRating.setCurrentIndex(1)  # デフォルト: "PG-13"

        # 共通値判定: Score
        if len(scores) == 1:
            # 全画像が同じScore
            common_score_db = next(iter(scores))
            score_ui = int(common_score_db * 100)
            self.ui.sliderScore.setValue(score_ui)
            self.ui.labelScoreValue.setText(f"{score_ui / 100.0:.2f}")
        else:
            # 異なるScoreまたは値なし → デフォルト値
            self.ui.sliderScore.setValue(500)
            self.ui.labelScoreValue.setText("5.00")

        # シグナルのブロックを解除
        self.ui.comboBoxRating.blockSignals(False)
        self.ui.sliderScore.blockSignals(False)

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
        """
        rating = self.ui.comboBoxRating.currentText()
        score = self.ui.sliderScore.value()

        if self._is_batch_mode:
            # バッチモード: 複数画像を一括更新
            if not self._selected_image_ids:
                logger.warning("Save clicked in batch mode but no images selected")
                return

            logger.info(
                f"Batch save requested: {len(self._selected_image_ids)} images, "
                f"rating={rating}, score={score}"
            )

            # バッチシグナルを発行
            self.batch_rating_changed.emit(self._selected_image_ids, rating)
            self.batch_score_changed.emit(self._selected_image_ids, score)

        else:
            # 単一選択モード: 従来の動作
            if self._current_image_id is None:
                logger.warning("Save clicked but no image is loaded")
                return

            logger.info(
                f"Save requested for image_id={self._current_image_id}, rating={rating}, score={score}"
            )

            # 単一画像シグナルを発行
            self.rating_changed.emit(self._current_image_id, rating)
            self.score_changed.emit(self._current_image_id, score)
