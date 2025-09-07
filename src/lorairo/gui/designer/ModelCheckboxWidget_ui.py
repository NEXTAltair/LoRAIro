# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ModelCheckboxWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel,
    QSizePolicy, QWidget)

class Ui_ModelCheckboxWidget(object):
    def setupUi(self, ModelCheckboxWidget):
        if not ModelCheckboxWidget.objectName():
            ModelCheckboxWidget.setObjectName(u"ModelCheckboxWidget")
        ModelCheckboxWidget.resize(300, 28)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ModelCheckboxWidget.sizePolicy().hasHeightForWidth())
        ModelCheckboxWidget.setSizePolicy(sizePolicy)
        ModelCheckboxWidget.setMinimumSize(QSize(0, 28))
        ModelCheckboxWidget.setMaximumSize(QSize(16777215, 28))
        self.mainLayout = QHBoxLayout(ModelCheckboxWidget)
        self.mainLayout.setSpacing(8)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(4, 2, 4, 2)
        self.checkboxModel = QCheckBox(ModelCheckboxWidget)
        self.checkboxModel.setObjectName(u"checkboxModel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.checkboxModel.sizePolicy().hasHeightForWidth())
        self.checkboxModel.setSizePolicy(sizePolicy1)
        self.checkboxModel.setMinimumSize(QSize(20, 20))

        self.mainLayout.addWidget(self.checkboxModel)

        self.labelModelName = QLabel(ModelCheckboxWidget)
        self.labelModelName.setObjectName(u"labelModelName")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.labelModelName.sizePolicy().hasHeightForWidth())
        self.labelModelName.setSizePolicy(sizePolicy2)
        font = QFont()
        font.setPointSize(9)
        self.labelModelName.setFont(font)
        self.labelModelName.setAlignment(Qt.AlignmentFlag.AlignLeading|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.labelModelName.setStyleSheet(u"QLabel {\n"
"    color: #333;\n"
"    padding: 2px 4px;\n"
"}")

        self.mainLayout.addWidget(self.labelModelName)

        self.labelProvider = QLabel(ModelCheckboxWidget)
        self.labelProvider.setObjectName(u"labelProvider")
        sizePolicy1.setHeightForWidth(self.labelProvider.sizePolicy().hasHeightForWidth())
        self.labelProvider.setSizePolicy(sizePolicy1)
        self.labelProvider.setMinimumSize(QSize(60, 18))
        self.labelProvider.setMaximumSize(QSize(60, 18))
        font1 = QFont()
        font1.setPointSize(8)
        self.labelProvider.setFont(font1)
        self.labelProvider.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelProvider.setStyleSheet(u"QLabel {\n"
"    background-color: #f0f0f0;\n"
"    color: #555;\n"
"    border: 1px solid #ddd;\n"
"    border-radius: 9px;\n"
"    padding: 1px 4px;\n"
"    font-weight: 500;\n"
"}")

        self.mainLayout.addWidget(self.labelProvider)

        self.labelCapabilities = QLabel(ModelCheckboxWidget)
        self.labelCapabilities.setObjectName(u"labelCapabilities")
        sizePolicy1.setHeightForWidth(self.labelCapabilities.sizePolicy().hasHeightForWidth())
        self.labelCapabilities.setSizePolicy(sizePolicy1)
        self.labelCapabilities.setMinimumSize(QSize(80, 18))
        self.labelCapabilities.setMaximumSize(QSize(80, 18))
        font2 = QFont()
        font2.setPointSize(7)
        self.labelCapabilities.setFont(font2)
        self.labelCapabilities.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelCapabilities.setStyleSheet(u"QLabel {\n"
"    background-color: #e8f4fd;\n"
"    color: #1976D2;\n"
"    border: 1px solid #90caf9;\n"
"    border-radius: 9px;\n"
"    padding: 1px 4px;\n"
"    font-weight: 500;\n"
"}")

        self.mainLayout.addWidget(self.labelCapabilities)


        self.retranslateUi(ModelCheckboxWidget)

        QMetaObject.connectSlotsByName(ModelCheckboxWidget)
    # setupUi

    def retranslateUi(self, ModelCheckboxWidget):
        ModelCheckboxWidget.setWindowTitle(QCoreApplication.translate("ModelCheckboxWidget", u"Model Checkbox", None))
        self.checkboxModel.setText("")
        self.labelModelName.setText(QCoreApplication.translate("ModelCheckboxWidget", u"Model Name", None))
        self.labelProvider.setText(QCoreApplication.translate("ModelCheckboxWidget", u"Provider", None))
        self.labelCapabilities.setText(QCoreApplication.translate("ModelCheckboxWidget", u"capabilities", None))
    # retranslateUi

