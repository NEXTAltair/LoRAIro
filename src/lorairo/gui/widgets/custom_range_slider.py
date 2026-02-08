from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimeZone, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from superqt import QDoubleRangeSlider


class CustomRangeSlider(QWidget):
    """日付、スコア、または数値の範囲を選択するためのカスタムレンジスライダーウィジェット。

    superqt.QDoubleRangeSliderを活用した軽量実装。
    日付モード、スコアモード、数値モードをサポートし、ラベル表示機能を提供します。

    属性:
        valueChanged (Signal): 範囲変更時に発行されるシグナル (min_value, max_value)
    """

    valueChanged = Signal(int, int)

    def __init__(self, parent: QWidget | None = None, min_value: int = 0, max_value: int = 100000) -> None:
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value
        self.is_date_mode = False
        self.is_score_mode = False
        self.setup_ui()

    def setup_ui(self) -> None:
        """UIをセットアップし、superqtスライダーを直接使用"""
        layout = QVBoxLayout(self)

        # superqtのQDoubleRangeSliderを直接値範囲で使用
        self.slider = QDoubleRangeSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(self.min_value, self.max_value)
        self.slider.setValue((self.min_value, self.max_value))

        self.min_label = QLabel(f"{self.min_value:,}")
        self.max_label = QLabel(f"{self.max_value:,}")

        labels_layout = QHBoxLayout()
        labels_layout.addWidget(self.min_label)
        labels_layout.addStretch()
        labels_layout.addWidget(self.max_label)

        layout.addWidget(self.slider)
        layout.addLayout(labels_layout)

        self.slider.valueChanged.connect(self.update_labels)

    @Slot()
    def update_labels(self) -> None:
        """ラベルを更新してシグナルを発行"""
        min_val, max_val = self.slider.value()
        min_count = int(min_val)
        max_count = int(max_val)

        if self.is_date_mode:
            local_tz = QTimeZone.systemTimeZone()
            min_date = QDateTime.fromSecsSinceEpoch(min_count, local_tz)
            max_date = QDateTime.fromSecsSinceEpoch(max_count, local_tz)
            self.min_label.setText(min_date.toString("yyyy-MM-dd"))
            self.max_label.setText(max_date.toString("yyyy-MM-dd"))
        elif self.is_score_mode:
            # スコアモード: 内部値0-1000を0.00-10.00に変換して表示
            min_score = min_count / 100.0
            max_score = max_count / 100.0
            self.min_label.setText(f"{min_score:.2f}")
            self.max_label.setText(f"{max_score:.2f}")
        else:
            self.min_label.setText(f"{min_count:,}")
            self.max_label.setText(f"{max_count:,}")

        self.valueChanged.emit(min_count, max_count)

    def get_range(self) -> tuple[int, int]:
        """現在の選択範囲を取得"""
        min_val, max_val = self.slider.value()
        return (int(min_val), int(max_val))

    def set_range(self, min_value: int, max_value: int) -> None:
        """スライダーの範囲を設定"""
        self.min_value = min_value
        self.max_value = max_value
        self.slider.setRange(min_value, max_value)
        self.slider.setValue((min_value, max_value))

    def set_date_range(self) -> None:
        """日付モードを設定（2023/1/1から現在まで）"""
        start_date = QDateTime(QDate(2023, 1, 1), QTime(0, 0), QTimeZone.utc())
        end_date = QDateTime.currentDateTimeUtc()
        end_date.setTime(QTime(23, 59, 59))

        self.is_date_mode = True
        start_timestamp = int(start_date.toSecsSinceEpoch())
        end_timestamp = int(end_date.toSecsSinceEpoch())

        self.set_range(start_timestamp, end_timestamp)

    def set_score_mode(self) -> None:
        """スコアモードを設定（0.00-10.00、内部値0-1000）"""
        self.is_score_mode = True
        self.is_date_mode = False
        # 範囲は既に0-1000で初期化されている
        self.update_labels()


if __name__ == "__main__":
    # Tier2: set_date_range 後に valueChanged(min,max) の発火を最小確認
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow

    from ...utils.log import initialize_logging

    # ログはコンソール優先
    initialize_logging({"level": "DEBUG", "file": None})
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("CustomRangeSlider テスト (Tier2)")
    widget = CustomRangeSlider()
    window.setCentralWidget(widget)
    window.resize(520, 140)

    # シグナル受信確認
    def _on_value_changed(min_v: int, max_v: int) -> None:
        print(f"[Signal] valueChanged: min={min_v}, max={max_v}")

    widget.valueChanged.connect(_on_value_changed)

    # 日付モードを設定し、プログラムから一度値変更を発火させる
    widget.set_date_range()
    # 現在値を取得してわずかに動かし、valueChanged を確実に発火
    try:
        vmin: float
        vmax: float
        vmin, vmax = widget.slider.value()
        # 範囲 [0,100] 内で安全に少しだけ動かす
        new_vmin = max(0, min(100, int(vmin)))
        new_vmax = max(0, min(100, int(vmax) - 1)) if int(vmax) > 0 else int(vmax)
        if new_vmax == vmin:
            new_vmax = min(100, new_vmax + 1)
        widget.slider.setValue((new_vmin, new_vmax))
    except Exception:
        pass

    window.show()
    sys.exit(app.exec())
