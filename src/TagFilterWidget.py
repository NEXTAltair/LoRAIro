import numpy as np

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, Slot, QDateTime, QTimeZone, QDate, QTime
from superqt import QDoubleRangeSlider

from gui_file.TagFilterWidget_ui import Ui_TagFilterWidget

from module.log import get_logger

class CustomRangeSlider(QWidget):
    """日付または数値の範囲を選択するためのカスタムレンジスライダーウィジェット。

    このウィジェットは、日付または数値の範囲を選択するためのスライダーを提供します。
    現在の範囲の値をラベルとして表示します。

    属性:
        valueChanged (Signal): スライダーの値が変更されたときに発行されるシグナル。
            このシグナルは、選択された範囲の最小値と最大値を表す2つの整数値を発行します。

            日付範囲の場合、これらの整数値はローカルタイムゾーンでのUnixタイムスタンプ
            （エポックからの秒数）を表します。数値範囲の場合、実際に選択された値を表します。

            引数:
                min_value (int): 選択された範囲の最小値。
                max_value (int): 選択された範囲の最大値。

    """
    valueChanged = Signal(int, int)  # 最小値と最大値の変更を通知するシグナル

    def __init__(self, parent=None, min_value=0, max_value=100000):
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value
        self.is_date_mode = False
        self.setup_ui()

    def setup_ui(self):
        """CustomRangeSliderのユーザーインターフェースをセットアップします。

        このメソッドは、スライダーとラベルを初期化し、必要なシグナルを接続します。

        スライダーは0から100の範囲で設定され、後にユーザーが設定した実際の範囲
        （日付または数値）にマッピングされます。

        現在の範囲の最小値と最大値を表示するために2つのラベルが作成されます。
        これらのラベルは、スライダーの値が変更されるたびに更新されます。

        注意:
            このメソッドはクラスのコンストラクタ内部で呼び出されるため、
            ユーザーが直接呼び出す必要はありません。
        """
        layout = QVBoxLayout(self)

        self.slider = QDoubleRangeSlider(Qt.Orientation.Horizontal)
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
    def update_labels(self):
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

    def scale_to_value(self, value):
        if value == 0:
            return self.min_value
        if value == 100:
            return self.max_value
        log_min = np.log1p(self.min_value)
        log_max = np.log1p(self.max_value)
        log_value = log_min + (log_max - log_min) * (value / 100)
        return int(np.expm1(log_value))

    def get_range(self):
        min_val, max_val = self.slider.value()
        return (self.scale_to_value(min_val), self.scale_to_value(max_val))

    def set_range(self, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
        self.update_labels()

    def set_date_range(self):
        # 開始日を2023年1月1日の0時に設定（UTC）
        start_date = QDateTime(QDate(2023, 1, 1), QTime(0, 0), QTimeZone.UTC)

        # 終了日を現在の日付の23:59:59に設定（UTC）
        end_date = QDateTime.currentDateTimeUtc()
        end_date.setTime(QTime(23, 59, 59))

        # 日付モードをオンにする
        self.is_date_mode = True

        # UTCタイムスタンプを取得（秒単位の整数）
        start_timestamp = int(start_date.toSecsSinceEpoch())
        end_timestamp = int(end_date.toSecsSinceEpoch())

        # 範囲を設定
        self.set_range(start_timestamp, end_timestamp)

        # ラベルを更新
        self.update_labels()

class TagFilterWidget(QWidget, Ui_TagFilterWidget):
    filterApplied = Signal(dict)
    """{
        filter_type: str,
        filter_text: str,
        resolution: int,
        use_and: bool,
        count_range: tuple
    }
    """

    def __init__(self, parent=None):
        self.logger = get_logger(__class__.__name__)
        super().__init__(parent)
        self.setupUi(self)
        self.setup_slider()

    def setup_slider(self):
        # CustomLRangeSliderをcountRangeSlideウィジェットとして追加
        self.count_range_slider = CustomRangeSlider(self, min_value=0, max_value=100000)
        layout = self.countRangeWidget.layout()
        # 既存のcountRangeSlideウィジェットを削除（存在する場合）
        if self.countRangeSlide is not None:
            layout.removeWidget(self.countRangeSlide)
            self.countRangeSlide.deleteLater()
        # 新しいCustomLRangeSliderを追加
        layout.addWidget(self.count_range_slider)

    @Slot()
    def on_applyFilterButton_clicked(self):
        """フィルター条件を取得して、filterAppliedシグナルを発行"""
        resolution = self.resolutionComboBox.currentText()
        split_resolution = resolution.split('x')
        filter_conditions = {
            'filter_type': self.filterTypeComboBox.currentText().lower() if self.filterTypeComboBox.isVisible() else None,
            'filter_text': self.filterLineEdit.text(),
            'resolution': int(split_resolution[0]) if split_resolution else None,
            'use_and': self.andRadioButton.isChecked() if self.andRadioButton.isVisible() else False,
            'count_range': self.count_range_slider.get_range() if self.count_range_slider.isVisible() else None,
            'include_untagged': self.noTagscheckBox.isChecked(),  # タグ情報がない画像を含めるかどうか
            'include_nsfw': self.NSFWcheckBox.isChecked()  # NSFWコンテンツを含めるかどうか（デフォルトは除外）
        }
        self.logger.debug(f"Filter conditions: {filter_conditions}")
        self.filterApplied.emit(filter_conditions)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from module.config import get_config
    from module.log import setup_logger
    import sys

    app = QApplication(sys.argv)
    config = get_config()
    logconf = {'level': 'DEBUG', 'file': 'TagFilterWidget.log'}
    setup_logger(logconf)

    widget = TagFilterWidget()
    widget.show()
    sys.exit(app.exec())