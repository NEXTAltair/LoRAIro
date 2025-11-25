# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'FilePickerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.0
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

class Ui_FilePickerWidget(object):
    def setupUi(self, FilePickerWidget):
        if not FilePickerWidget.objectName():
            FilePickerWidget.setObjectName(u"FilePickerWidget")
        FilePickerWidget.resize(562, 253)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(FilePickerWidget.sizePolicy().hasHeightForWidth())
        FilePickerWidget.setSizePolicy(sizePolicy)
        self.horizontalLayout = QHBoxLayout(FilePickerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.FilePicker = PickerWidget(FilePickerWidget)
        self.FilePicker.setObjectName(u"FilePicker")

        self.horizontalLayout.addWidget(self.FilePicker)


        self.retranslateUi(FilePickerWidget)

        QMetaObject.connectSlotsByName(FilePickerWidget)
    # setupUi

    def retranslateUi(self, FilePickerWidget):
        FilePickerWidget.setWindowTitle(QCoreApplication.translate("FilePickerWidget", u"Form", None))
    # retranslateUi

