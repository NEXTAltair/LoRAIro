# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ThumbnailSelectorWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget)

class Ui_ThumbnailSelectorWidget(object):
    def setupUi(self, ThumbnailSelectorWidget):
        if not ThumbnailSelectorWidget.objectName():
            ThumbnailSelectorWidget.setObjectName(u"ThumbnailSelectorWidget")
        ThumbnailSelectorWidget.resize(107, 107)
        self.verticalLayout = QVBoxLayout(ThumbnailSelectorWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.scrollAreaThumbnails = QScrollArea(ThumbnailSelectorWidget)
        self.scrollAreaThumbnails.setObjectName(u"scrollAreaThumbnails")
        self.scrollAreaThumbnails.setWidgetResizable(True)
        self.widgetThumbnailsContent = QWidget()
        self.widgetThumbnailsContent.setObjectName(u"widgetThumbnailsContent")
        self.widgetThumbnailsContent.setGeometry(QRect(0, 0, 83, 83))
        self.widgetThumbnailsContent.setMinimumSize(QSize(64, 64))
        self.scrollAreaThumbnails.setWidget(self.widgetThumbnailsContent)

        self.verticalLayout.addWidget(self.scrollAreaThumbnails)


        self.retranslateUi(ThumbnailSelectorWidget)

        QMetaObject.connectSlotsByName(ThumbnailSelectorWidget)
    # setupUi

    def retranslateUi(self, ThumbnailSelectorWidget):
        pass
    # retranslateUi

