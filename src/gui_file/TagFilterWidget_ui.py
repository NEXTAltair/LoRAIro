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
        self.filterTypeWidget = QWidget(self.filterGroupBox)
        self.filterTypeWidget.setObjectName(u"filterTypeWidget")
        self.filterTypeLayout = QHBoxLayout(self.filterTypeWidget)
        self.filterTypeLayout.setObjectName(u"filterTypeLayout")
        self.filterTypeLabel = QLabel(self.filterTypeWidget)
        self.filterTypeLabel.setObjectName(u"filterTypeLabel")

        self.filterTypeLayout.addWidget(self.filterTypeLabel)

        self.filterTypeComboBox = QComboBox(self.filterTypeWidget)
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.setObjectName(u"filterTypeComboBox")

        self.filterTypeLayout.addWidget(self.filterTypeComboBox)

        self.andRadioButton = QRadioButton(self.filterTypeWidget)
        self.andRadioButton.setObjectName(u"andRadioButton")

        self.filterTypeLayout.addWidget(self.andRadioButton)


        self.filterLayout.addWidget(self.filterTypeWidget)

        self.countRangeWidget = QWidget(self.filterGroupBox)
        self.countRangeWidget.setObjectName(u"countRangeWidget")
        self.countRangeWidget.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.horizontalLayout = QHBoxLayout(self.countRangeWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.tagUpdateatLabel = QLabel(self.countRangeWidget)
        self.tagUpdateatLabel.setObjectName(u"tagUpdateatLabel")

        self.horizontalLayout.addWidget(self.tagUpdateatLabel)

        self.countRangeSlide = QWidget(self.countRangeWidget)
        self.countRangeSlide.setObjectName(u"countRangeSlide")

        self.horizontalLayout.addWidget(self.countRangeSlide)


        self.filterLayout.addWidget(self.countRangeWidget)

        self.filterLineEdit = QLineEdit(self.filterGroupBox)
        self.filterLineEdit.setObjectName(u"filterLineEdit")

        self.filterLayout.addWidget(self.filterLineEdit)

        self.resolutionWidget = QWidget(self.filterGroupBox)
        self.resolutionWidget.setObjectName(u"resolutionWidget")
        self.resolutionLayout = QHBoxLayout(self.resolutionWidget)
        self.resolutionLayout.setObjectName(u"resolutionLayout")
        self.resolutionLabel = QLabel(self.resolutionWidget)
        self.resolutionLabel.setObjectName(u"resolutionLabel")

        self.resolutionLayout.addWidget(self.resolutionLabel)

        self.resolutionComboBox = QComboBox(self.resolutionWidget)
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.setObjectName(u"resolutionComboBox")

        self.resolutionLayout.addWidget(self.resolutionComboBox)


        self.filterLayout.addWidget(self.resolutionWidget)

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
        self.tagUpdateatLabel.setText(QCoreApplication.translate("TagFilterWidget", u"\u30bf\u30b0\u7de8\u96c6\u65e5", None))
        self.filterLineEdit.setPlaceholderText(QCoreApplication.translate("TagFilterWidget", u"Enter filter criteria", None))
        self.resolutionLabel.setText(QCoreApplication.translate("TagFilterWidget", u"Resolution:", None))
        self.resolutionComboBox.setItemText(0, QCoreApplication.translate("TagFilterWidget", u"512x512", None))
        self.resolutionComboBox.setItemText(1, QCoreApplication.translate("TagFilterWidget", u"768x768", None))
        self.resolutionComboBox.setItemText(2, QCoreApplication.translate("TagFilterWidget", u"1024x1024", None))

        self.applyFilterButton.setText(QCoreApplication.translate("TagFilterWidget", u"Apply Filters", None))
    # retranslateUi

