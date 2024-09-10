# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ProgressWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QLabel, QProgressBar, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget)

class Ui_ProgressWidget(object):
    def setupUi(self, ProgressWidget):
        if not ProgressWidget.objectName():
            ProgressWidget.setObjectName(u"ProgressWidget")
        ProgressWidget.setWindowModality(Qt.WindowModality.WindowModal)
        ProgressWidget.resize(400, 113)
        self.verticalLayout = QVBoxLayout(ProgressWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.statusLabel = QLabel(ProgressWidget)
        self.statusLabel.setObjectName(u"statusLabel")

        self.verticalLayout.addWidget(self.statusLabel, 0, Qt.AlignmentFlag.AlignLeft)

        self.progressBar = QProgressBar(ProgressWidget)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setValue(0)

        self.verticalLayout.addWidget(self.progressBar)

        self.cancelButton = QPushButton(ProgressWidget)
        self.cancelButton.setObjectName(u"cancelButton")

        self.verticalLayout.addWidget(self.cancelButton, 0, Qt.AlignmentFlag.AlignRight)


        self.retranslateUi(ProgressWidget)

        QMetaObject.connectSlotsByName(ProgressWidget)
    # setupUi

    def retranslateUi(self, ProgressWidget):
        ProgressWidget.setWindowTitle(QCoreApplication.translate("ProgressWidget", u"Form", None))
        self.statusLabel.setText(QCoreApplication.translate("ProgressWidget", u"\u5f85\u6a5f\u4e2d...", None))
        self.progressBar.setFormat(QCoreApplication.translate("ProgressWidget", u"%v / %m", None))
        self.cancelButton.setText(QCoreApplication.translate("ProgressWidget", u"\u30ad\u30e3\u30f3\u30bb\u30eb", None))
    # retranslateUi

