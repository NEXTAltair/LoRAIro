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
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QWidget)

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

        self.listWidgetHistory = QListWidget(PickerWidget)
        self.listWidgetHistory.setObjectName(u"listWidgetHistory")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.listWidgetHistory.sizePolicy().hasHeightForWidth())
        self.listWidgetHistory.setSizePolicy(sizePolicy1)
        self.listWidgetHistory.setMinimumSize(QSize(100, 0))
        self.listWidgetHistory.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.listWidgetHistory.setUniformItemSizes(False)
        self.listWidgetHistory.setSelectionRectVisible(False)

        self.horizontalLayout.addWidget(self.listWidgetHistory)

        self.pushButtonHistory = QPushButton(PickerWidget)
        self.pushButtonHistory.setObjectName(u"pushButtonHistory")
        self.pushButtonHistory.setMinimumSize(QSize(80, 0))

        self.horizontalLayout.addWidget(self.pushButtonHistory)

        self.pushButtonPicker = QPushButton(PickerWidget)
        self.pushButtonPicker.setObjectName(u"pushButtonPicker")

        self.horizontalLayout.addWidget(self.pushButtonPicker)

#if QT_CONFIG(shortcut)
        self.labelPicker.setBuddy(self.lineEditPicker)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.lineEditPicker, self.listWidgetHistory)
        QWidget.setTabOrder(self.listWidgetHistory, self.pushButtonHistory)
        QWidget.setTabOrder(self.pushButtonHistory, self.pushButtonPicker)

        self.retranslateUi(PickerWidget)
        self.pushButtonHistory.clicked.connect(PickerWidget.toggle_history_visibility)

        QMetaObject.connectSlotsByName(PickerWidget)
    # setupUi

    def retranslateUi(self, PickerWidget):
        PickerWidget.setWindowTitle(QCoreApplication.translate("PickerWidget", u"Form", None))
        self.labelPicker.setText(QCoreApplication.translate("PickerWidget", u"Path", None))
        self.pushButtonHistory.setText(QCoreApplication.translate("PickerWidget", u"\u5c65\u6b74", None))
        self.pushButtonPicker.setText(QCoreApplication.translate("PickerWidget", u"\u9078\u629e...", None))
    # retranslateUi

