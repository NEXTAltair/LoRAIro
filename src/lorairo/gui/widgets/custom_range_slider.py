import datetime as dt
from collections.abc import Callable
from typing import Any, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from superqt import QDoubleRangeSlider

from ...domain.registration_date_range import LocalDayRange, local_today

# 日付モードの既定の下限 (登録日フィルタ)
DEFAULT_MIN_DAY = dt.date(2023, 1, 1)


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
        _DoubleRangeSlider = cast("Callable[..., Any]", QDoubleRangeSlider)
        self.slider = _DoubleRangeSlider(Qt.Orientation.Horizontal)
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
        min_val: float
        max_val: float
        min_val, max_val = self.slider.value()
        if self.is_date_mode:
            # 日付モードの値は暦日の序数 (date.toordinal)。ドラッグ中の小数は最寄りの日へ丸める
            min_count = round(min_val)
            max_count = round(max_val)
            # 序数は 1 以上 (モード切替の途中で 0 起点の範囲が入っても落ちないようにする)
            self.min_label.setText(dt.date.fromordinal(max(1, min_count)).isoformat())
            self.max_label.setText(dt.date.fromordinal(max(1, max_count)).isoformat())
        elif self.is_score_mode:
            # スコアモード: 内部値0-1000を0.00-10.00に変換して表示
            min_count = int(min_val)
            max_count = int(max_val)
            self.min_label.setText(f"{min_count / 100.0:.2f}")
            self.max_label.setText(f"{max_count / 100.0:.2f}")
        else:
            min_count = int(min_val)
            max_count = int(max_val)
            self.min_label.setText(f"{min_count:,}")
            self.max_label.setText(f"{max_count:,}")

        self.valueChanged.emit(min_count, max_count)

    def get_range(self) -> tuple[int, int]:
        """現在の選択範囲を取得"""
        min_val: float
        max_val: float
        min_val, max_val = self.slider.value()
        if self.is_date_mode:
            return (round(min_val), round(max_val))
        return (int(min_val), int(max_val))

    def set_range(self, min_value: int, max_value: int) -> None:
        """スライダーの範囲を設定"""
        self.min_value = min_value
        self.max_value = max_value
        self.slider.setRange(min_value, max_value)
        self.slider.setValue((min_value, max_value))

    def set_date_range(self, min_day: dt.date = DEFAULT_MIN_DAY, max_day: dt.date | None = None) -> None:
        """日付モード (暦日単位) を設定する。既定は 2023-01-01 からローカル時刻の今日まで。

        値は ``date.toordinal()`` の整数で、1 目盛り = 1 日 (ADR 0100)。

        Args:
            min_day: 下限の暦日。
            max_day: 上限の暦日。None はローカル時刻の今日。
        """
        self.is_date_mode = True
        self.is_score_mode = False
        upper = max_day or local_today()
        self.slider.setSingleStep(1)
        self.set_range(min_day.toordinal(), max(min_day, upper).toordinal())

    def get_day_range(self) -> LocalDayRange:
        """日付モードで選択中の暦日範囲 (両端を含む) を返す。"""
        min_ordinal, max_ordinal = self.get_range()
        low, high = sorted((min_ordinal, max_ordinal))
        return LocalDayRange(dt.date.fromordinal(low), dt.date.fromordinal(high))

    def set_day_range(self, day_range: LocalDayRange) -> None:
        """日付モードの選択を暦日範囲に設定する。範囲外なら目盛りの範囲を広げる。

        Args:
            day_range: 選択する暦日範囲。
        """
        low = min(round(self.slider.minimum()), day_range.start.toordinal())
        high = max(round(self.slider.maximum()), day_range.end.toordinal())
        if (low, high) != (round(self.slider.minimum()), round(self.slider.maximum())):
            self.min_value, self.max_value = low, high
            self.slider.setRange(low, high)
        self.slider.setValue((day_range.start.toordinal(), day_range.end.toordinal()))

    def full_day_range(self) -> LocalDayRange:
        """日付モードの目盛り全体 (絞り込みなし相当) の暦日範囲を返す。"""
        return LocalDayRange(
            dt.date.fromordinal(round(self.slider.minimum())),
            dt.date.fromordinal(round(self.slider.maximum())),
        )

    def is_full_range(self) -> bool:
        """選択が目盛りの全範囲 (絞り込みなし相当) かを返す。"""
        min_val, max_val = self.get_range()
        return (min_val, max_val) == (round(self.slider.minimum()), round(self.slider.maximum()))

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
