# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DirectoryPickerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
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
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QSizePolicy, QWidget)

from ..widgets.picker import PickerWidget

class Ui_DirectoryPickerWidget(object):
    def setupUi(self, DirectoryPickerWidget):
        if not DirectoryPickerWidget.objectName():
            DirectoryPickerWidget.setObjectName(u"DirectoryPickerWidget")
        DirectoryPickerWidget.resize(562, 253)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DirectoryPickerWidget.sizePolicy().hasHeightForWidth())
        DirectoryPickerWidget.setSizePolicy(sizePolicy)
        self.horizontalLayout = QHBoxLayout(DirectoryPickerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.DirectoryPicker = PickerWidget(DirectoryPickerWidget)
        self.DirectoryPicker.setObjectName(u"DirectoryPicker")

        self.horizontalLayout.addWidget(self.DirectoryPicker)


        self.retranslateUi(DirectoryPickerWidget)

        QMetaObject.connectSlotsByName(DirectoryPickerWidget)
    # setupUi

    def retranslateUi(self, DirectoryPickerWidget):
        DirectoryPickerWidget.setWindowTitle(QCoreApplication.translate("DirectoryPickerWidget", u"Form", None))
    # retranslateUi

