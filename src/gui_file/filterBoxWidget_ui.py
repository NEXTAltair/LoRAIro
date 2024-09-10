# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'filterBoxWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton,
    QSizePolicy, QVBoxLayout, QWidget)

class Ui_filterBoxWidget(object):
    def setupUi(self, filterBoxWidget):
        if not filterBoxWidget.objectName():
            filterBoxWidget.setObjectName(u"filterBoxWidget")
        filterBoxWidget.resize(400, 300)
        self.verticalLayout = QVBoxLayout(filterBoxWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.filterGroupBox = QGroupBox(filterBoxWidget)
        self.filterGroupBox.setObjectName(u"filterGroupBox")
        self.filterLayout = QVBoxLayout(self.filterGroupBox)
        self.filterLayout.setObjectName(u"filterLayout")
        self.filterTypeLayout = QHBoxLayout()
        self.filterTypeLayout.setObjectName(u"filterTypeLayout")
        self.filterTypeLabel = QLabel(self.filterGroupBox)
        self.filterTypeLabel.setObjectName(u"filterTypeLabel")

        self.filterTypeLayout.addWidget(self.filterTypeLabel)

        self.filterTypeComboBox = QComboBox(self.filterGroupBox)
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.setObjectName(u"filterTypeComboBox")

        self.filterTypeLayout.addWidget(self.filterTypeComboBox)

        self.andRadioButton = QRadioButton(self.filterGroupBox)
        self.andRadioButton.setObjectName(u"andRadioButton")

        self.filterTypeLayout.addWidget(self.andRadioButton)


        self.filterLayout.addLayout(self.filterTypeLayout)

        self.filterLineEdit = QLineEdit(self.filterGroupBox)
        self.filterLineEdit.setObjectName(u"filterLineEdit")

        self.filterLayout.addWidget(self.filterLineEdit)

        self.resolutionLayout = QHBoxLayout()
        self.resolutionLayout.setObjectName(u"resolutionLayout")
        self.resolutionLabel = QLabel(self.filterGroupBox)
        self.resolutionLabel.setObjectName(u"resolutionLabel")

        self.resolutionLayout.addWidget(self.resolutionLabel)

        self.resolutionComboBox = QComboBox(self.filterGroupBox)
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.setObjectName(u"resolutionComboBox")

        self.resolutionLayout.addWidget(self.resolutionComboBox)


        self.filterLayout.addLayout(self.resolutionLayout)

        self.applyFilterButton = QPushButton(self.filterGroupBox)
        self.applyFilterButton.setObjectName(u"applyFilterButton")

        self.filterLayout.addWidget(self.applyFilterButton)


        self.verticalLayout.addWidget(self.filterGroupBox)


        self.retranslateUi(filterBoxWidget)

        QMetaObject.connectSlotsByName(filterBoxWidget)
    # setupUi

    def retranslateUi(self, filterBoxWidget):
        filterBoxWidget.setWindowTitle(QCoreApplication.translate("filterBoxWidget", u"Form", None))
        self.filterGroupBox.setTitle(QCoreApplication.translate("filterBoxWidget", u"Filter Criteria", None))
        self.filterTypeLabel.setText(QCoreApplication.translate("filterBoxWidget", u"Filter Type:", None))
        self.filterTypeComboBox.setItemText(0, QCoreApplication.translate("filterBoxWidget", u"Tags", None))
        self.filterTypeComboBox.setItemText(1, QCoreApplication.translate("filterBoxWidget", u"Caption", None))

        self.andRadioButton.setText(QCoreApplication.translate("filterBoxWidget", u"AND\u691c\u7d22", None))
        self.filterLineEdit.setPlaceholderText(QCoreApplication.translate("filterBoxWidget", u"Enter filter criteria", None))
        self.resolutionLabel.setText(QCoreApplication.translate("filterBoxWidget", u"Resolution:", None))
        self.resolutionComboBox.setItemText(0, QCoreApplication.translate("filterBoxWidget", u"512x512", None))
        self.resolutionComboBox.setItemText(1, QCoreApplication.translate("filterBoxWidget", u"768x768", None))
        self.resolutionComboBox.setItemText(2, QCoreApplication.translate("filterBoxWidget", u"1024x1024", None))

        self.applyFilterButton.setText(QCoreApplication.translate("filterBoxWidget", u"Apply Filters", None))
    # retranslateUi

