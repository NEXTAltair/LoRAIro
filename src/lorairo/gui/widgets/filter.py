from typing import Any

import numpy as np
from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimeZone, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from superqt import QDoubleRangeSlider

from ..designer.FilterSearchPanel_ui import Ui_FilterSearchPanel


class CustomRangeSlider(QWidget):
    """日付または数値の範囲を選択するためのカスタムレンジスライダーウィジェット。

    このウィジェットは、日付または数値の範囲を選択するためのスライダーを提供します。
    現在の範囲の値をラベルとして表示します。

    属性:
        valueChanged (Signal): スライダーの値が変更されたときに発行されるシグナル。
            このシグナルは、選択された範囲の最小値と最大値を表す2つの整数値を発行します。

            日付範囲の場合、これらの整数値はローカルタイムゾーンでのUnixタイムスタンプ
            (エポックからの秒数)を表します。数値範囲の場合、実際に選択された値を表します。

            引数:
                min_value (int): 選択された範囲の最小値。
                max_value (int): 選択された範囲の最大値。

    """

    valueChanged = Signal(int, int)  # 最小値と最大値の変更を通知するシグナル

    def __init__(self, parent: QWidget | None = None, min_value: int = 0, max_value: int = 100000) -> None:
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value
        self.is_date_mode = False
        self.setup_ui()

    def setup_ui(self) -> None:
        """CustomRangeSliderのユーザーインターフェースをセットアップします。

        このメソッドは、スライダーとラベルを初期化し、必要なシグナルを接続します。

        スライダーは0から100の範囲で設定され、後にユーザーが設定した実際の範囲
        (日付または数値)にマッピングされます。

        現在の範囲の最小値と最大値を表示するために2つのラベルが作成されます。
        これらのラベルは、スライダーの値が変更されるたびに更新されます。

        注意:
            このメソッドはクラスのコンストラクタ内部で呼び出されるため、
            ユーザーが直接呼び出す必要はありません。
        """
        layout = QVBoxLayout(self)

        self.slider = QDoubleRangeSlider(Qt.Orientation.Horizontal)  # type: ignore
        self.slider.setRange(0, 100)
        self.slider.setValue((0, 100))

        self.min_label = QLabel(f"{self.min_value:,}")
        self.max_label = QLabel(f"{self.max_value:,}+")

        labels_layout = QHBoxLayout()
        labels_layout.addWidget(self.min_label)
        labels_layout.addStretch()
        labels_layout.addWidget(self.max_label)

        layout.addWidget(self.slider)
        layout.addLayout(labels_layout)

        self.slider.valueChanged.connect(self.update_labels)

    @Slot()
    def update_labels(self) -> None:
        min_val, max_val = self.slider.value()
        min_count = self.scale_to_value(min_val)
        max_count = self.scale_to_value(max_val)

        if self.is_date_mode:
            local_tz = QTimeZone.systemTimeZone()
            min_date = QDateTime.fromSecsSinceEpoch(min_count, local_tz)
            max_date = QDateTime.fromSecsSinceEpoch(max_count, local_tz)
            self.min_label.setText(min_date.toString("yyyy-MM-dd"))
            self.max_label.setText(max_date.toString("yyyy-MM-dd"))
        else:
            self.min_label.setText(f"{min_count:,}")
            self.max_label.setText(f"{max_count:,}")

        self.valueChanged.emit(min_count, max_count)

    def scale_to_value(self, value: int) -> int:
        if value == 0:
            return self.min_value
        if value == 100:
            return self.max_value
        log_min = np.log1p(self.min_value)
        log_max = np.log1p(self.max_value)
        log_value = log_min + (log_max - log_min) * (value / 100)
        return int(np.expm1(log_value))

    def get_range(self) -> tuple[int, int]:
        min_val, max_val = self.slider.value()
        return (self.scale_to_value(min_val), self.scale_to_value(max_val))

    def set_range(self, min_value: int, max_value: int) -> None:
        self.min_value = min_value
        self.max_value = max_value
        self.update_labels()

    def set_date_range(self) -> None:
        # 開始日を2023年1月1日の0時に設定(UTC)
        start_date = QDateTime(QDate(2023, 1, 1), QTime(0, 0), QTimeZone.utc())

        # 終了日を現在の日付の23:59:59に設定(UTC)
        end_date = QDateTime.currentDateTimeUtc()
        end_date.setTime(QTime(23, 59, 59))

        # 日付モードをオンにする
        self.is_date_mode = True

        # UTCタイムスタンプを取得(秒単位の整数)
        start_timestamp = int(start_date.toSecsSinceEpoch())
        end_timestamp = int(end_date.toSecsSinceEpoch())

        # 範囲を設定
        self.set_range(start_timestamp, end_timestamp)

        # ラベルを更新
        self.update_labels()


class FilterSearchPanel(QWidget, Ui_FilterSearchPanel):
    """統合されたフィルター・検索パネルウィジェット。

    このウィジェットは以下の機能を統合しています:
    - タグ/キャプション検索（AND/OR検索対応）
    - 解像度フィルター（カスタム解像度対応）
    - アスペクト比フィルター
    - 日付範囲フィルター
    - オプション（未タグ、未キャプション、重複除外、NSFW）

    旧来のTagFilterWidget、filterBoxWidgetの機能を統合した包括的なフィルターパネルです。
    """

    filterApplied = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)  # type: ignore
        self.setup_date_range_slider()  # type: ignore
        self.setup_connections()  # type: ignore

    def setup_date_range_slider(self) -> None:
        """日付範囲スライダーをセットアップします。"""
        # プレースホルダーラベルを実際のCustomRangeSliderに置き換え
        self.date_range_slider = CustomRangeSlider(self, min_value=0, max_value=100000)
        self.date_range_slider.set_date_range()  # type: ignore

        layout = self.frameDateRange.layout()
        if layout is not None and self.dateRangeSliderPlaceholder:
            layout.removeWidget(self.dateRangeSliderPlaceholder)
            self.dateRangeSliderPlaceholder.deleteLater()
        if layout is not None:
            layout.addWidget(self.date_range_slider)

    def setup_connections(self) -> None:
        """シグナル・スロット接続をセットアップします。"""
        # カスタム解像度表示の切り替え
        self.comboResolution.currentTextChanged.connect(self.toggle_custom_resolution)
        # 日付フィルター表示の切り替え
        self.checkboxDateFilter.toggled.connect(self.frameDateRange.setVisible)
        # ボタン接続
        self.buttonApply.clicked.connect(self.on_apply_filter)
        self.buttonClear.clicked.connect(self.on_clear_filter)

    def toggle_custom_resolution(self, text: str) -> None:
        """カスタム解像度フレームの表示を切り替えます。"""
        self.frameCustomResolution.setVisible(text == "カスタム...")

    def on_apply_filter(self) -> None:
        """フィルター条件を取得してシグナルを発行します。"""
        conditions = self.get_filter_conditions()
        self.filterApplied.emit(conditions)

    def on_clear_filter(self) -> None:
        """すべてのフィルター条件をクリアします。"""
        self.lineEditSearch.clear()
        self.radioTags.setChecked(True)
        self.radioAnd.setChecked(True)
        self.comboResolution.setCurrentIndex(0)
        self.comboAspectRatio.setCurrentIndex(0)
        self.checkboxDateFilter.setChecked(False)
        self.checkboxOnlyUntagged.setChecked(False)
        self.checkboxOnlyUncaptioned.setChecked(False)
        self.checkboxExcludeDuplicates.setChecked(False)
        self.checkboxIncludeNSFW.setChecked(False)
        self.textEditPreview.clear()

    def get_filter_conditions(self) -> dict[str, Any]:
        """現在のフィルター条件を辞書として返します。"""
        # 解像度処理
        resolution_text = self.comboResolution.currentText()
        if resolution_text == "カスタム...":
            width = self.lineEditWidth.text()
            height = self.lineEditHeight.text()
            resolution = f"{width}x{height}" if width and height else None
        elif resolution_text != "全て":
            resolution = resolution_text
        else:
            resolution = None

        # 日付範囲処理
        date_range = None
        if self.checkboxDateFilter.isChecked():
            date_range = self.date_range_slider.get_range()

        return {
            "search_text": self.lineEditSearch.text(),
            "search_type": "tags" if self.radioTags.isChecked() else "caption",
            "search_mode": "and" if self.radioAnd.isChecked() else "or",
            "resolution": resolution,
            "aspect_ratio": self.comboAspectRatio.currentText()
            if self.comboAspectRatio.currentIndex() > 0
            else None,
            "date_range": date_range,
            "only_untagged": self.checkboxOnlyUntagged.isChecked(),
            "only_uncaptioned": self.checkboxOnlyUncaptioned.isChecked(),
            "exclude_duplicates": self.checkboxExcludeDuplicates.isChecked(),
            "include_nsfw": self.checkboxIncludeNSFW.isChecked(),
        }


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 統合フィルター・検索パネルをテスト
    widget = FilterSearchPanel()  # type: ignore
    widget.setWindowTitle("統合フィルター・検索パネル")
    widget.show()

    sys.exit(app.exec())
