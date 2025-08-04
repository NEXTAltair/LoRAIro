import numpy as np
from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimeZone, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from superqt import QDoubleRangeSlider


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


if __name__ == "__main__":
    # Tier1: 単体表示確認用の最小 __main__ ブロック
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    initialize_logging({"level": "DEBUG", "file": "CustomRangeSlider.log"})
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("CustomRangeSlider テスト")
    widget = CustomRangeSlider()
    widget.set_date_range()  # 日付モード確認
    window.setCentralWidget(widget)
    window.resize(520, 140)
    window.show()

    sys.exit(app.exec())
