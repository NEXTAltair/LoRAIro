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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget)

class Ui_TagFilterWidget(object):
    def setupUi(self, TagFilterWidget):
        if not TagFilterWidget.objectName():
            TagFilterWidget.setObjectName(u"TagFilterWidget")
        TagFilterWidget.resize(269, 277)
        self.verticalLayout = QVBoxLayout(TagFilterWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.filterGroupBox = QGroupBox(TagFilterWidget)
        self.filterGroupBox.setObjectName(u"filterGroupBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.filterGroupBox.sizePolicy().hasHeightForWidth())
        self.filterGroupBox.setSizePolicy(sizePolicy)
        self.filterGroupBox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vboxLayout = QVBoxLayout(self.filterGroupBox)
        self.vboxLayout.setObjectName(u"vboxLayout")
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


        self.vboxLayout.addWidget(self.filterTypeWidget)

        self.filterLineEdit = QLineEdit(self.filterGroupBox)
        self.filterLineEdit.setObjectName(u"filterLineEdit")

        self.vboxLayout.addWidget(self.filterLineEdit)

        self.taggingFilter = QWidget(self.filterGroupBox)
        self.taggingFilter.setObjectName(u"taggingFilter")
        self.horizontalLayout_2 = QHBoxLayout(self.taggingFilter)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.noTagscheckBox = QCheckBox(self.taggingFilter)
        self.noTagscheckBox.setObjectName(u"noTagscheckBox")

        self.horizontalLayout_2.addWidget(self.noTagscheckBox)

        self.NSFWcheckBox = QCheckBox(self.taggingFilter)
        self.NSFWcheckBox.setObjectName(u"NSFWcheckBox")

        self.horizontalLayout_2.addWidget(self.NSFWcheckBox)


        self.vboxLayout.addWidget(self.taggingFilter)

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


        self.vboxLayout.addWidget(self.countRangeWidget)

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
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.setObjectName(u"resolutionComboBox")

        self.resolutionLayout.addWidget(self.resolutionComboBox)


        self.vboxLayout.addWidget(self.resolutionWidget)

        self.applyFilterButton = QPushButton(self.filterGroupBox)
        self.applyFilterButton.setObjectName(u"applyFilterButton")

        self.vboxLayout.addWidget(self.applyFilterButton)


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
        self.filterLineEdit.setPlaceholderText(QCoreApplication.translate("TagFilterWidget", u"Enter filter criteria", None))
        self.noTagscheckBox.setText(QCoreApplication.translate("TagFilterWidget", u"\u30bf\u30b0\u306e\u7121\u3044\u753b\u50cf", None))
        self.NSFWcheckBox.setText(QCoreApplication.translate("TagFilterWidget", u"NSFW", None))
        self.tagUpdateatLabel.setText(QCoreApplication.translate("TagFilterWidget", u"\u30bf\u30b0\u7de8\u96c6\u65e5", None))
        self.resolutionLabel.setText(QCoreApplication.translate("TagFilterWidget", u"Resolution:", None))
        self.resolutionComboBox.setItemText(0, QCoreApplication.translate("TagFilterWidget", u"None", None))
        self.resolutionComboBox.setItemText(1, QCoreApplication.translate("TagFilterWidget", u"512x512", None))
        self.resolutionComboBox.setItemText(2, QCoreApplication.translate("TagFilterWidget", u"768x768", None))
        self.resolutionComboBox.setItemText(3, QCoreApplication.translate("TagFilterWidget", u"1024x1024", None))

        self.applyFilterButton.setText(QCoreApplication.translate("TagFilterWidget", u"Apply Filters", None))
    # retranslateUi

