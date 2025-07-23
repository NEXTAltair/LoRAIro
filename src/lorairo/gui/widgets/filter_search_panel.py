# src/lorairo/gui/widgets/filter_search_panel.py

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger
from ..state.dataset_state import DatasetStateManager
from .filter import CustomRangeSlider


class FilterSearchPanel(QScrollArea):
    """
    統合検索・フィルターパネル。
    タグ検索、キャプション検索、解像度フィルター、日付範囲フィルターを統合。
    """

    # シグナル
    filter_applied = Signal(dict)  # filter_conditions
    filter_cleared = Signal()
    search_requested = Signal(dict)  # search_conditions

    def __init__(self, parent=None, dataset_state: DatasetStateManager | None = None):
        super().__init__(parent)

        # 状態管理
        self.dataset_state = dataset_state

        # UI設定
        self.setup_ui()

        # 状態管理との連携
        if self.dataset_state:
            self._connect_dataset_state()

        logger.debug("FilterSearchPanel initialized")

    def setup_ui(self) -> None:
        """UI初期化"""
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # メインウィジェット
        main_widget = QWidget()
        self.setWidget(main_widget)

        # メインレイアウト
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(10)

        # 各セクションを作成
        self._create_search_section()
        self._create_filter_section()
        self._create_date_section()
        self._create_options_section()
        self._create_action_section()

        # 下部スペーサー
        spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.main_layout.addItem(spacer)

    def _create_search_section(self) -> None:
        """検索セクション作成"""
        search_group = QGroupBox("検索")
        search_layout = QVBoxLayout(search_group)

        # 検索タイプ選択
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("検索対象:"))

        self.radio_tags = QRadioButton("タグ")
        self.radio_caption = QRadioButton("キャプション")
        self.radio_tags.setChecked(True)

        # ラジオボタン変更時の処理を追加
        self.radio_tags.toggled.connect(self._on_search_type_changed)
        self.radio_caption.toggled.connect(self._on_search_type_changed)

        type_layout.addWidget(self.radio_tags)
        type_layout.addWidget(self.radio_caption)
        type_layout.addStretch()

        search_layout.addLayout(type_layout)

        # 検索テキスト入力
        self.line_edit_search = QLineEdit()
        self.line_edit_search.setPlaceholderText("検索キーワードを入力（複数タグの場合はカンマ区切り）...")
        self.line_edit_search.returnPressed.connect(self._on_search_requested)
        search_layout.addWidget(self.line_edit_search)

        # タグ検索オプション
        tag_options_layout = QHBoxLayout()
        self.radio_and = QRadioButton("すべて含む")
        self.radio_or = QRadioButton("いずれか含む")
        self.radio_and.setChecked(True)

        tag_options_layout.addWidget(QLabel("複数タグ:"))
        tag_options_layout.addWidget(self.radio_and)
        tag_options_layout.addWidget(self.radio_or)
        tag_options_layout.addStretch()

        search_layout.addLayout(tag_options_layout)

        # 検索結果プレビュー
        self.text_edit_preview = QTextEdit()
        self.text_edit_preview.setMaximumHeight(60)
        self.text_edit_preview.setReadOnly(True)
        self.text_edit_preview.setPlaceholderText("検索結果のプレビューがここに表示されます")
        search_layout.addWidget(self.text_edit_preview)

        self.main_layout.addWidget(search_group)

    def _create_filter_section(self) -> None:
        """フィルターセクション作成"""
        filter_group = QGroupBox("フィルター")
        filter_layout = QVBoxLayout(filter_group)

        # 解像度フィルター
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(QLabel("解像度:"))

        self.combo_resolution = QComboBox()
        self.combo_resolution.addItems(
            [
                "全て",
                "512x512",
                "1024x1024",
                "1024x768",
                "768x1024",
                "1920x1080",
                "1080x1920",
                "2048x2048",
                "カスタム...",
            ]
        )
        self.combo_resolution.currentTextChanged.connect(self._on_resolution_changed)

        resolution_layout.addWidget(self.combo_resolution)
        resolution_layout.addStretch()

        filter_layout.addLayout(resolution_layout)

        # カスタム解像度入力
        self.frame_custom_resolution = QFrame()
        custom_layout = QHBoxLayout(self.frame_custom_resolution)
        custom_layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit_width = QLineEdit()
        self.line_edit_width.setPlaceholderText("幅")
        self.line_edit_width.setMaximumWidth(60)

        self.line_edit_height = QLineEdit()
        self.line_edit_height.setPlaceholderText("高さ")
        self.line_edit_height.setMaximumWidth(60)

        custom_layout.addWidget(QLabel("カスタム:"))
        custom_layout.addWidget(self.line_edit_width)
        custom_layout.addWidget(QLabel("x"))
        custom_layout.addWidget(self.line_edit_height)
        custom_layout.addStretch()

        self.frame_custom_resolution.setVisible(False)
        filter_layout.addWidget(self.frame_custom_resolution)

        # アスペクト比フィルター
        aspect_layout = QHBoxLayout()
        aspect_layout.addWidget(QLabel("アスペクト比:"))

        self.combo_aspect_ratio = QComboBox()
        self.combo_aspect_ratio.addItems(
            [
                "全て",
                "正方形 (1:1)",
                "風景 (16:9)",
                "縦長 (9:16)",
                "風景 (4:3)",
                "縦長 (3:4)",
            ]
        )

        aspect_layout.addWidget(self.combo_aspect_ratio)
        aspect_layout.addStretch()

        filter_layout.addLayout(aspect_layout)

        self.main_layout.addWidget(filter_group)

    def _create_date_section(self) -> None:
        """日付セクション作成"""
        date_group = QGroupBox("日付範囲")
        date_layout = QVBoxLayout(date_group)

        # 日付範囲有効化チェックボックス
        self.checkbox_date_filter = QCheckBox("日付範囲でフィルター")
        self.checkbox_date_filter.toggled.connect(self._on_date_filter_toggled)
        date_layout.addWidget(self.checkbox_date_filter)

        # 日付範囲スライダー
        self.frame_date_range = QFrame()
        date_range_layout = QVBoxLayout(self.frame_date_range)
        date_range_layout.setContentsMargins(0, 0, 0, 0)

        # CustomRangeSlider を使用
        self.date_range_slider = CustomRangeSlider()
        self.date_range_slider.set_date_range()  # 日付モードに設定
        self.date_range_slider.valueChanged.connect(self._on_date_range_changed)

        date_range_layout.addWidget(self.date_range_slider)

        self.frame_date_range.setVisible(False)
        date_layout.addWidget(self.frame_date_range)

        self.main_layout.addWidget(date_group)

    def _create_options_section(self) -> None:
        """オプションセクション作成"""
        options_group = QGroupBox("オプション")
        options_layout = QVBoxLayout(options_group)

        # 検索モードオプション
        self.checkbox_only_untagged = QCheckBox("未タグ画像のみ検索")
        self.checkbox_only_untagged.setChecked(False)
        self.checkbox_only_untagged.toggled.connect(self._on_only_untagged_toggled)
        options_layout.addWidget(self.checkbox_only_untagged)

        # 未キャプション画像のみ検索
        self.checkbox_only_uncaptioned = QCheckBox("未キャプション画像のみ検索")
        self.checkbox_only_uncaptioned.setChecked(False)
        self.checkbox_only_uncaptioned.toggled.connect(self._on_only_uncaptioned_toggled)
        options_layout.addWidget(self.checkbox_only_uncaptioned)

        # 重複画像を除外
        self.checkbox_exclude_duplicates = QCheckBox("重複画像を除外")
        self.checkbox_exclude_duplicates.setChecked(False)
        options_layout.addWidget(self.checkbox_exclude_duplicates)

        self.main_layout.addWidget(options_group)

    def _create_action_section(self) -> None:
        """アクションセクション作成"""
        action_layout = QHBoxLayout()

        # 検索・フィルター適用ボタン（統合）
        self.button_apply = QPushButton("検索実行")
        self.button_apply.clicked.connect(self._on_search_requested)
        action_layout.addWidget(self.button_apply)

        # クリアボタン
        self.button_clear = QPushButton("クリア")
        self.button_clear.clicked.connect(self._on_clear_requested)
        action_layout.addWidget(self.button_clear)

        self.main_layout.addLayout(action_layout)

    def set_dataset_state(self, dataset_state: DatasetStateManager) -> None:
        """データセット状態管理を設定"""
        if self.dataset_state:
            self._disconnect_dataset_state()

        self.dataset_state = dataset_state
        self._connect_dataset_state()

    def _connect_dataset_state(self) -> None:
        """データセット状態管理との連携を設定"""
        if not self.dataset_state:
            return

        self.dataset_state.filter_applied.connect(self._on_state_filter_applied)
        self.dataset_state.filter_cleared.connect(self._on_state_filter_cleared)

    def _disconnect_dataset_state(self) -> None:
        """データセット状態管理との連携を解除"""
        if not self.dataset_state:
            return

        self.dataset_state.filter_applied.disconnect(self._on_state_filter_applied)
        self.dataset_state.filter_cleared.disconnect(self._on_state_filter_cleared)

    # === Event Handlers ===

    def _on_resolution_changed(self, text: str) -> None:
        """解像度選択変更処理"""
        is_custom = text == "カスタム..."
        self.frame_custom_resolution.setVisible(is_custom)

    def _on_date_filter_toggled(self, checked: bool) -> None:
        """日付フィルター有効化切り替え処理"""
        self.frame_date_range.setVisible(checked)

    def _on_date_range_changed(self, min_timestamp: int, max_timestamp: int) -> None:
        """日付範囲変更処理"""
        logger.debug(f"日付範囲変更: {min_timestamp} - {max_timestamp}")
        # 自動検索は行わず、ユーザーが検索ボタンを押すまで待つ

    def _on_only_untagged_toggled(self, checked: bool) -> None:
        """未タグ画像のみ検索トグル処理"""
        self._update_search_input_state()
        self._on_search_type_changed()

    def _on_only_uncaptioned_toggled(self, checked: bool) -> None:
        """未キャプション画像のみ検索トグル処理"""
        self._update_search_input_state()
        self._on_search_type_changed()

    def _on_search_type_changed(self) -> None:
        """検索タイプ変更時の処理"""
        # 入力フィールドの有効/無効を更新
        self._update_search_input_state()

        # プレースホルダーテキストを更新
        if self.radio_tags.isChecked():
            if self.checkbox_only_untagged.isChecked():
                self.line_edit_search.setPlaceholderText("未タグ画像検索中（タグ入力無効）")
            else:
                self.line_edit_search.setPlaceholderText(
                    "検索キーワードを入力（複数タグの場合はカンマ区切り）..."
                )
        else:  # caption
            if self.checkbox_only_uncaptioned.isChecked():
                self.line_edit_search.setPlaceholderText("未キャプション画像検索中（キャプション入力無効）")
            else:
                self.line_edit_search.setPlaceholderText("キャプション検索キーワードを入力...")

    def _update_search_input_state(self) -> None:
        """検索入力フィールドの有効/無効状態を更新"""
        # タグ検索で未タグ検索が有効、またはキャプション検索で未キャプション検索が有効の場合は無効化
        disabled = (self.radio_tags.isChecked() and self.checkbox_only_untagged.isChecked()) or (
            self.radio_caption.isChecked() and self.checkbox_only_uncaptioned.isChecked()
        )
        self.line_edit_search.setEnabled(not disabled)

    def _on_search_requested(self) -> None:
        """検索要求処理"""
        conditions = self._get_search_conditions()

        # 検索中表示
        self.text_edit_preview.setPlainText("検索中...")

        # MainWorkspaceWindow に検索条件を送信
        self.search_requested.emit(conditions)
        logger.info(f"検索要求: {conditions}")

    def _on_clear_requested(self) -> None:
        """クリア要求処理"""
        self._clear_all_inputs()

        # MainWorkspaceWindow にクリア要求を送信
        self.filter_cleared.emit()
        logger.info("フィルター・検索をクリア")

    @Slot(dict)
    def _on_state_filter_applied(self, filter_conditions: dict) -> None:
        """状態管理からのフィルター適用通知"""
        # UIに条件を反映（循環参照防止のため、シグナル発行は停止）
        self._update_ui_from_conditions(filter_conditions)

    @Slot()
    def _on_state_filter_cleared(self) -> None:
        """状態管理からのフィルタークリア通知"""
        self._clear_all_inputs()

    # === Private Methods ===

    def _get_search_conditions(self) -> dict[str, Any]:
        """検索・フィルター条件を取得（2段階分離版）"""
        # データベース条件とフロントエンド条件を分離
        db_conditions, frontend_conditions = self._separate_conditions()

        # 従来の互換性のため、統合した条件も返す
        all_conditions = {**db_conditions, **frontend_conditions}

        # 2段階処理用の情報を追加
        all_conditions["_db_conditions"] = db_conditions
        all_conditions["_frontend_conditions"] = frontend_conditions
        all_conditions["_use_two_stage"] = bool(frontend_conditions)

        return all_conditions

    def _separate_conditions(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """条件をデータベース用とフロントエンド用に分離"""
        db_conditions = {}
        frontend_conditions = {}

        # 検索条件（データベース処理）
        search_text = self.line_edit_search.text().strip()
        if search_text:
            if self.radio_tags.isChecked():
                # タグ検索: カンマ区切りでリスト化
                db_conditions["tags"] = [tag.strip() for tag in search_text.split(",") if tag.strip()]
                db_conditions["use_and"] = self.radio_and.isChecked()
            else:
                # キャプション検索
                db_conditions["caption"] = search_text

        # 解像度フィルター（データベース処理 - 効率的なINDEX使用）
        resolution_text = self.combo_resolution.currentText()
        if resolution_text != "全て":
            resolution_value = 0  # デフォルト
            if resolution_text.startswith("512"):
                resolution_value = 512
            elif resolution_text.startswith("1024"):
                resolution_value = 1024
            elif resolution_text.startswith("2048"):
                resolution_value = 2048
            elif resolution_text == "カスタム...":
                width = self.line_edit_width.text().strip()
                height = self.line_edit_height.text().strip()
                if width and height:
                    try:
                        # カスタム解像度は最大値を使用
                        resolution_value = max(int(width), int(height))
                    except ValueError:
                        resolution_value = 0

            if resolution_value > 0:
                db_conditions["resolution"] = resolution_value

        # 日付範囲フィルター（フロントエンド処理 - リアルタイム性重視）
        if self.checkbox_date_filter.isChecked():
            min_timestamp, max_timestamp = self.date_range_slider.get_range()
            frontend_conditions["date_range"] = (min_timestamp, max_timestamp)

        # オプション処理
        # 未タグ画像のみ検索オプション（データベース処理）
        if self.checkbox_only_untagged.isChecked():
            # 未タグ画像のみを検索
            db_conditions["include_untagged"] = True
            # タグ条件をクリア（未タグ検索時は矛盾するため）
            db_conditions.pop("tags", None)
            db_conditions.pop("use_and", None)
        elif db_conditions.get("tags") or db_conditions.get("caption"):
            # タグまたはキャプション検索時は未タグ画像を含めない（検索対象を明確化）
            db_conditions["include_untagged"] = False
        else:
            # 条件なし検索時のみ未タグ画像も含める
            db_conditions["include_untagged"] = True

        # 未キャプション画像のみ検索オプション（データベース処理）
        if self.checkbox_only_uncaptioned.isChecked():
            # キャプション条件をクリア（未キャプション検索時は矛盾するため）
            db_conditions.pop("caption", None)

        # include_nsfw は UI にないので False
        db_conditions["include_nsfw"] = False

        return db_conditions, frontend_conditions

    def _update_ui_from_conditions(self, conditions: dict) -> None:
        """条件からUIを更新"""
        # 検索テキスト
        if conditions.get("tags"):
            self.radio_tags.setChecked(True)
            self.line_edit_search.setText(", ".join(conditions["tags"]))
            self.radio_and.setChecked(conditions.get("use_and", True))
            self.radio_or.setChecked(not conditions.get("use_and", True))
        elif conditions.get("caption"):
            self.radio_caption.setChecked(True)
            self.line_edit_search.setText(conditions["caption"])

        # 解像度
        if "resolution" in conditions:
            resolution = conditions["resolution"]
            if resolution in [
                self.combo_resolution.itemText(i) for i in range(self.combo_resolution.count())
            ]:
                self.combo_resolution.setCurrentText(resolution)
            else:
                # カスタム解像度
                self.combo_resolution.setCurrentText("カスタム...")
                if "x" in resolution:
                    width, height = resolution.split("x", 1)
                    self.line_edit_width.setText(width)
                    self.line_edit_height.setText(height)

        # 日付範囲
        if "date_range" in conditions:
            start_timestamp, end_timestamp = conditions["date_range"]
            start_date = datetime.fromtimestamp(start_timestamp).date()
            end_date = datetime.fromtimestamp(end_timestamp).date()

            self.checkbox_date_filter.setChecked(True)
            self.date_edit_start.setDate(QDate.fromString(start_date.isoformat(), Qt.DateFormat.ISODate))
            self.date_edit_end.setDate(QDate.fromString(end_date.isoformat(), Qt.DateFormat.ISODate))

    def _clear_all_inputs(self) -> None:
        """全入力をクリア"""
        self.line_edit_search.clear()
        self.radio_tags.setChecked(True)
        self.radio_and.setChecked(True)

        self.combo_resolution.setCurrentIndex(0)
        self.combo_aspect_ratio.setCurrentIndex(0)
        self.line_edit_width.clear()
        self.line_edit_height.clear()
        self.frame_custom_resolution.setVisible(False)

        self.checkbox_date_filter.setChecked(False)
        self.frame_date_range.setVisible(False)
        # スライダーを全範囲にリセット
        self.date_range_slider.slider.setValue((0, 100))

        self.checkbox_only_untagged.setChecked(False)
        self.checkbox_only_uncaptioned.setChecked(False)
        self.checkbox_exclude_duplicates.setChecked(False)

        self.text_edit_preview.setPlainText("検索結果のプレビューがここに表示されます")

    # === Public Methods ===

    def set_search_text(self, text: str, search_type: str = "tags") -> None:
        """検索テキストを設定"""
        self.line_edit_search.setText(text)
        if search_type == "tags":
            self.radio_tags.setChecked(True)
        else:
            self.radio_caption.setChecked(True)

    def get_current_conditions(self) -> dict[str, Any]:
        """現在の条件を取得"""
        return self._get_search_conditions()

    def apply_conditions(self, conditions: dict[str, Any]) -> None:
        """条件を適用"""
        self._update_ui_from_conditions(conditions)

    def update_search_preview(self, result_count: int, preview_text: str = "") -> None:
        """検索結果プレビューを更新"""
        if result_count > 0:
            preview = f"検索結果: {result_count}件"
            if preview_text:
                preview += f"\n{preview_text}"
        else:
            preview = "検索結果がありません"

        self.text_edit_preview.setPlainText(preview)
        logger.debug(f"検索結果プレビュー更新: {result_count}件")

    def clear_search_preview(self) -> None:
        """検索結果プレビューをクリア"""
        self.text_edit_preview.clear()
        logger.debug("検索結果プレビューをクリア")
