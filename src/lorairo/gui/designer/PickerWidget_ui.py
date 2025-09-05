################################################################################
## Form generated from reading UI file 'PickerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTime,
    QUrl,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class Ui_PickerWidget:
    def setupUi(self, PickerWidget):
        if not PickerWidget.objectName():
            PickerWidget.setObjectName("PickerWidget")
        PickerWidget.resize(540, 210)
        PickerWidget.setMinimumSize(QSize(80, 0))
        PickerWidget.setAcceptDrops(True)
        self.horizontalLayout = QHBoxLayout(PickerWidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.labelPicker = QLabel(PickerWidget)
        self.labelPicker.setObjectName("labelPicker")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelPicker.sizePolicy().hasHeightForWidth())
        self.labelPicker.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.labelPicker)

        self.lineEditPicker = QLineEdit(PickerWidget)
        self.lineEditPicker.setObjectName("lineEditPicker")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lineEditPicker.sizePolicy().hasHeightForWidth())
        self.lineEditPicker.setSizePolicy(sizePolicy1)

        self.horizontalLayout.addWidget(self.lineEditPicker)

        self.comboBoxHistory = QComboBox(PickerWidget)
        self.comboBoxHistory.setObjectName("comboBoxHistory")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.comboBoxHistory.sizePolicy().hasHeightForWidth())
        self.comboBoxHistory.setSizePolicy(sizePolicy2)

        self.horizontalLayout.addWidget(self.comboBoxHistory)

        self.pushButtonPicker = QPushButton(PickerWidget)
        self.pushButtonPicker.setObjectName("pushButtonPicker")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.pushButtonPicker.sizePolicy().hasHeightForWidth())
        self.pushButtonPicker.setSizePolicy(sizePolicy3)

        self.horizontalLayout.addWidget(self.pushButtonPicker)

        self.retranslateUi(PickerWidget)

        QMetaObject.connectSlotsByName(PickerWidget)

    # setupUi

    def retranslateUi(self, PickerWidget):
        PickerWidget.setWindowTitle(QCoreApplication.translate("PickerWidget", "Form", None))
        self.labelPicker.setText(QCoreApplication.translate("PickerWidget", "Path", None))
        self.pushButtonPicker.setText(QCoreApplication.translate("PickerWidget", "\u9078\u629e...", None))

    # retranslateUi
