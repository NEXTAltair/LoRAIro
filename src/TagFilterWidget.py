import numpy as np

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGroupBox
from PySide6.QtCore import Qt, Signal, Slot
from superqt import QDoubleRangeSlider

from gui_file.TagFilterWidget_ui import Ui_TagFilterWidget

from module.log import get_logger

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, Slot
from superqt import QRangeSlider
import numpy as np

class CustomRangeSlider(QWidget):
    valueChanged = Signal(int, int)  # 最小値と最大値の変更を通知するシグナル

    def __init__(self, parent=None, min_value=0, max_value=100000):
        super().__init__(parent)
        self.min_value = min_value
        self.max_value = max_value
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # 余白を削除

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
        min_count = self.scale_to_count(min_val)
        max_count = self.scale_to_count(max_val)
        self.min_label.setText(f"{min_count:,}")
        self.max_label.setText(f"{max_count:,}")
        self.valueChanged.emit(min_count, max_count)

    def scale_to_count(self, value):
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
        return (self.scale_to_count(min_val), self.scale_to_count(max_val))

    def set_range(self, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
        self.update_labels()

class TagFilterWidget(QWidget, Ui_TagFilterWidget):
    filterApplied = Signal(dict)

    def __init__(self, parent=None):
        self.logger = get_logger(__class__.__name__)
        super().__init__(parent)
        self.setupUi(self)
        self.setup_slider()

    def setup_slider(self):
        # CustomLRangeSliderをcountRangeSlideウィジェットとして追加
        self.count_range_slider = CustomRangeSlider(self, min_value=0, max_value=100000)
        layout = self.countRangeGroupBox.layout()
        # 既存のcountRangeSlideウィジェットを削除（存在する場合）
        if self.countRangeSlide is not None:
            layout.removeWidget(self.countRangeSlide)
            self.countRangeSlide.deleteLater()
        # 新しいCustomLRangeSliderを追加
        layout.addWidget(self.count_range_slider)

    @Slot()
    def on_applyFilterButton_clicked(self):
        resolution = self.resolutionComboBox.currentText()
        split_resolution = resolution.split('x')
        filter_conditions = {
            'filter_type': self.filterTypeComboBox.currentText().lower() if self.filterTypeComboBox.isVisible() else None,
            'filter_text': self.filterLineEdit.text(),
            'resolution': (split_resolution[0], split_resolution[1]) if split_resolution else None,
            'use_and': self.andRadioButton.isChecked() if self.andRadioButton.isVisible() else False,
            'count_range': self.count_range_slider.get_range() if self.count_range_slider.isVisible() else None
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