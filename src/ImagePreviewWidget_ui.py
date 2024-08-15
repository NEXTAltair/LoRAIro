# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ImagePreviewWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QGraphicsView, QSizePolicy, QVBoxLayout,
    QWidget)

class Ui_ImagePreviewWidget(object):
    def setupUi(self, ImagePreviewWidget):
        if not ImagePreviewWidget.objectName():
            ImagePreviewWidget.setObjectName(u"ImagePreviewWidget")
        ImagePreviewWidget.resize(512, 512)
        self.verticalLayout = QVBoxLayout(ImagePreviewWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.previewGraphicsView = QGraphicsView(ImagePreviewWidget)
        self.previewGraphicsView.setObjectName(u"previewGraphicsView")

        self.verticalLayout.addWidget(self.previewGraphicsView)


        self.retranslateUi(ImagePreviewWidget)

        QMetaObject.connectSlotsByName(ImagePreviewWidget)
    # setupUi

    def retranslateUi(self, ImagePreviewWidget):
        ImagePreviewWidget.setWindowTitle(QCoreApplication.translate("ImagePreviewWidget", u"Form", None))
    # retranslateUi

