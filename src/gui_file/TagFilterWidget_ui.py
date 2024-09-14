# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'TagFilterWidget.ui'
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

class Ui_TagFilterWidget(object):
    def setupUi(self, TagFilterWidget):
        if not TagFilterWidget.objectName():
            TagFilterWidget.setObjectName(u"TagFilterWidget")
        TagFilterWidget.resize(400, 300)
        self.verticalLayout = QVBoxLayout(TagFilterWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.filterGroupBox = QGroupBox(TagFilterWidget)
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

        self.countRangeGroupBox = QGroupBox(self.filterGroupBox)
        self.countRangeGroupBox.setObjectName(u"countRangeGroupBox")
        self.verticalLayout_2 = QVBoxLayout(self.countRangeGroupBox)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.countRangeSlide = QWidget(self.countRangeGroupBox)
        self.countRangeSlide.setObjectName(u"countRangeSlide")

        self.verticalLayout_2.addWidget(self.countRangeSlide)


        self.filterLayout.addWidget(self.countRangeGroupBox)

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


        self.retranslateUi(TagFilterWidget)

        QMetaObject.connectSlotsByName(TagFilterWidget)
    # setupUi

    def retranslateUi(self, TagFilterWidget):
        TagFilterWidget.setWindowTitle(QCoreApplication.translate("TagFilterWidget", u"Form", None))
        self.filterGroupBox.setTitle(QCoreApplication.translate("TagFilterWidget", u"Filter Criteria", None))
        self.filterTypeLabel.setText(QCoreApplication.translate("TagFilterWidget", u"Filter Type:", None))
        self.filterTypeComboBox.setItemText(0, QCoreApplication.translate("TagFilterWidget", u"Tags", None))
        self.filterTypeComboBox.setItemText(1, QCoreApplication.translate("TagFilterWidget", u"Caption", None))

        self.andRadioButton.setText(QCoreApplication.translate("TagFilterWidget", u"AND\u691c\u7d22", None))
        self.countRangeGroupBox.setTitle(QCoreApplication.translate("TagFilterWidget", u"count", None))
        self.filterLineEdit.setPlaceholderText(QCoreApplication.translate("TagFilterWidget", u"Enter filter criteria", None))
        self.resolutionLabel.setText(QCoreApplication.translate("TagFilterWidget", u"Resolution:", None))
        self.resolutionComboBox.setItemText(0, QCoreApplication.translate("TagFilterWidget", u"512x512", None))
        self.resolutionComboBox.setItemText(1, QCoreApplication.translate("TagFilterWidget", u"768x768", None))
        self.resolutionComboBox.setItemText(2, QCoreApplication.translate("TagFilterWidget", u"1024x1024", None))

        self.applyFilterButton.setText(QCoreApplication.translate("TagFilterWidget", u"Apply Filters", None))
    # retranslateUi

