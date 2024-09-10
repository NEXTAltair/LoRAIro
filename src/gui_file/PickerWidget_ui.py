# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'PickerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QWidget)

class Ui_PickerWidget(object):
    def setupUi(self, PickerWidget):
        if not PickerWidget.objectName():
            PickerWidget.setObjectName(u"PickerWidget")
        PickerWidget.resize(540, 210)
        PickerWidget.setMinimumSize(QSize(80, 0))
        PickerWidget.setAcceptDrops(True)
        self.horizontalLayout = QHBoxLayout(PickerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.labelPicker = QLabel(PickerWidget)
        self.labelPicker.setObjectName(u"labelPicker")

        self.horizontalLayout.addWidget(self.labelPicker)

        self.lineEditPicker = QLineEdit(PickerWidget)
        self.lineEditPicker.setObjectName(u"lineEditPicker")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lineEditPicker.sizePolicy().hasHeightForWidth())
        self.lineEditPicker.setSizePolicy(sizePolicy)

        self.horizontalLayout.addWidget(self.lineEditPicker)

        self.comboBoxHistory = QComboBox(PickerWidget)
        self.comboBoxHistory.setObjectName(u"comboBoxHistory")

        self.horizontalLayout.addWidget(self.comboBoxHistory)

        self.pushButtonPicker = QPushButton(PickerWidget)
        self.pushButtonPicker.setObjectName(u"pushButtonPicker")

        self.horizontalLayout.addWidget(self.pushButtonPicker)


        self.retranslateUi(PickerWidget)

        QMetaObject.connectSlotsByName(PickerWidget)
    # setupUi

    def retranslateUi(self, PickerWidget):
        PickerWidget.setWindowTitle(QCoreApplication.translate("PickerWidget", u"Form", None))
        self.labelPicker.setText(QCoreApplication.translate("PickerWidget", u"Path", None))
        self.pushButtonPicker.setText(QCoreApplication.translate("PickerWidget", u"\u9078\u629e...", None))
    # retranslateUi

