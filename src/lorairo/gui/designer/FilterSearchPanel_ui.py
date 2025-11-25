# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'FilterSearchPanel.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

class Ui_FilterSearchPanel(object):
    def setupUi(self, FilterSearchPanel):
        if not FilterSearchPanel.objectName():
            FilterSearchPanel.setObjectName(u"FilterSearchPanel")
        FilterSearchPanel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        FilterSearchPanel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        FilterSearchPanel.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.mainLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.mainLayout.setSpacing(10)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(5, 5, 5, 5)
        self.searchGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.searchGroup.setObjectName(u"searchGroup")
        self.searchLayout = QVBoxLayout(self.searchGroup)
        self.searchLayout.setObjectName(u"searchLayout")
        self.searchTypeLayout = QHBoxLayout()
        self.searchTypeLayout.setObjectName(u"searchTypeLayout")
        self.searchTypeLabel = QLabel(self.searchGroup)
        self.searchTypeLabel.setObjectName(u"searchTypeLabel")

        self.searchTypeLayout.addWidget(self.searchTypeLabel)

        self.checkboxTags = QCheckBox(self.searchGroup)
        self.checkboxTags.setObjectName(u"checkboxTags")
        self.checkboxTags.setChecked(True)

        self.searchTypeLayout.addWidget(self.checkboxTags)

        self.checkboxCaption = QCheckBox(self.searchGroup)
        self.checkboxCaption.setObjectName(u"checkboxCaption")

        self.searchTypeLayout.addWidget(self.checkboxCaption)

        self.searchTypeSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.searchTypeLayout.addItem(self.searchTypeSpacer)


        self.searchLayout.addLayout(self.searchTypeLayout)

        self.lineEditSearch = QLineEdit(self.searchGroup)
        self.lineEditSearch.setObjectName(u"lineEditSearch")

        self.searchLayout.addWidget(self.lineEditSearch)

        self.tagOptionsLayout = QHBoxLayout()
        self.tagOptionsLayout.setObjectName(u"tagOptionsLayout")
        self.tagOptionsLabel = QLabel(self.searchGroup)
        self.tagOptionsLabel.setObjectName(u"tagOptionsLabel")

        self.tagOptionsLayout.addWidget(self.tagOptionsLabel)

        self.radioAnd = QRadioButton(self.searchGroup)
        self.radioAnd.setObjectName(u"radioAnd")
        self.radioAnd.setChecked(True)

        self.tagOptionsLayout.addWidget(self.radioAnd)

        self.radioOr = QRadioButton(self.searchGroup)
        self.radioOr.setObjectName(u"radioOr")

        self.tagOptionsLayout.addWidget(self.radioOr)

        self.tagOptionsSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.tagOptionsLayout.addItem(self.tagOptionsSpacer)


        self.searchLayout.addLayout(self.tagOptionsLayout)


        self.mainLayout.addWidget(self.searchGroup)

        self.filterGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.filterGroup.setObjectName(u"filterGroup")
        self.filterLayout = QVBoxLayout(self.filterGroup)
        self.filterLayout.setObjectName(u"filterLayout")
        self.resolutionLayout = QHBoxLayout()
        self.resolutionLayout.setObjectName(u"resolutionLayout")
        self.resolutionLabel = QLabel(self.filterGroup)
        self.resolutionLabel.setObjectName(u"resolutionLabel")

        self.resolutionLayout.addWidget(self.resolutionLabel)

        self.comboResolution = QComboBox(self.filterGroup)
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.setObjectName(u"comboResolution")

        self.resolutionLayout.addWidget(self.comboResolution)

        self.resolutionSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.resolutionLayout.addItem(self.resolutionSpacer)


        self.filterLayout.addLayout(self.resolutionLayout)

        self.aspectRatioLayout = QHBoxLayout()
        self.aspectRatioLayout.setObjectName(u"aspectRatioLayout")
        self.aspectRatioLabel = QLabel(self.filterGroup)
        self.aspectRatioLabel.setObjectName(u"aspectRatioLabel")

        self.aspectRatioLayout.addWidget(self.aspectRatioLabel)

        self.comboAspectRatio = QComboBox(self.filterGroup)
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.setObjectName(u"comboAspectRatio")

        self.aspectRatioLayout.addWidget(self.comboAspectRatio)

        self.aspectRatioSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.aspectRatioLayout.addItem(self.aspectRatioSpacer)


        self.filterLayout.addLayout(self.aspectRatioLayout)


        self.mainLayout.addWidget(self.filterGroup)

        self.dateGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.dateGroup.setObjectName(u"dateGroup")
        self.dateLayout = QVBoxLayout(self.dateGroup)
        self.dateLayout.setObjectName(u"dateLayout")
        self.checkboxDateFilter = QCheckBox(self.dateGroup)
        self.checkboxDateFilter.setObjectName(u"checkboxDateFilter")

        self.dateLayout.addWidget(self.checkboxDateFilter)

        self.frameDateRange = QFrame(self.dateGroup)
        self.frameDateRange.setObjectName(u"frameDateRange")
        self.frameDateRange.setVisible(False)
        self.frameDateRange.setFrameShape(QFrame.Shape.NoFrame)
        self.dateRangeLayout = QVBoxLayout(self.frameDateRange)
        self.dateRangeLayout.setObjectName(u"dateRangeLayout")
        self.dateRangeLayout.setContentsMargins(0, 0, 0, 0)
        self.dateRangeSliderPlaceholder = QLabel(self.frameDateRange)
        self.dateRangeSliderPlaceholder.setObjectName(u"dateRangeSliderPlaceholder")
        self.dateRangeSliderPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.dateRangeLayout.addWidget(self.dateRangeSliderPlaceholder)


        self.dateLayout.addWidget(self.frameDateRange)


        self.mainLayout.addWidget(self.dateGroup)

        self.ratingGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.ratingGroup.setObjectName(u"ratingGroup")
        self.ratingLayout = QVBoxLayout(self.ratingGroup)
        self.ratingLayout.setObjectName(u"ratingLayout")
        self.ratingFilterLayout = QHBoxLayout()
        self.ratingFilterLayout.setObjectName(u"ratingFilterLayout")
        self.ratingLabel = QLabel(self.ratingGroup)
        self.ratingLabel.setObjectName(u"ratingLabel")

        self.ratingFilterLayout.addWidget(self.ratingLabel)

        self.comboRating = QComboBox(self.ratingGroup)
        self.comboRating.addItem("")
        self.comboRating.addItem("")
        self.comboRating.addItem("")
        self.comboRating.addItem("")
        self.comboRating.addItem("")
        self.comboRating.addItem("")
        self.comboRating.setObjectName(u"comboRating")

        self.ratingFilterLayout.addWidget(self.comboRating)

        self.ratingSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.ratingFilterLayout.addItem(self.ratingSpacer)


        self.ratingLayout.addLayout(self.ratingFilterLayout)

        self.checkboxIncludeUnrated = QCheckBox(self.ratingGroup)
        self.checkboxIncludeUnrated.setObjectName(u"checkboxIncludeUnrated")
        self.checkboxIncludeUnrated.setChecked(True)

        self.ratingLayout.addWidget(self.checkboxIncludeUnrated)


        self.mainLayout.addWidget(self.ratingGroup)

        self.optionsGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.optionsGroup.setObjectName(u"optionsGroup")
        self.optionsLayout = QVBoxLayout(self.optionsGroup)
        self.optionsLayout.setObjectName(u"optionsLayout")
        self.checkboxOnlyUntagged = QCheckBox(self.optionsGroup)
        self.checkboxOnlyUntagged.setObjectName(u"checkboxOnlyUntagged")

        self.optionsLayout.addWidget(self.checkboxOnlyUntagged)

        self.checkboxOnlyUncaptioned = QCheckBox(self.optionsGroup)
        self.checkboxOnlyUncaptioned.setObjectName(u"checkboxOnlyUncaptioned")

        self.optionsLayout.addWidget(self.checkboxOnlyUncaptioned)

        self.checkboxExcludeDuplicates = QCheckBox(self.optionsGroup)
        self.checkboxExcludeDuplicates.setObjectName(u"checkboxExcludeDuplicates")

        self.optionsLayout.addWidget(self.checkboxExcludeDuplicates)

        self.checkboxIncludeNSFW = QCheckBox(self.optionsGroup)
        self.checkboxIncludeNSFW.setObjectName(u"checkboxIncludeNSFW")

        self.optionsLayout.addWidget(self.checkboxIncludeNSFW)


        self.mainLayout.addWidget(self.optionsGroup)

        self.actionLayout = QHBoxLayout()
        self.actionLayout.setObjectName(u"actionLayout")
        self.buttonApply = QPushButton(self.scrollAreaWidgetContents)
        self.buttonApply.setObjectName(u"buttonApply")

        self.actionLayout.addWidget(self.buttonApply)

        self.buttonClear = QPushButton(self.scrollAreaWidgetContents)
        self.buttonClear.setObjectName(u"buttonClear")

        self.actionLayout.addWidget(self.buttonClear)


        self.mainLayout.addLayout(self.actionLayout)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.mainLayout.addItem(self.verticalSpacer)

        FilterSearchPanel.setWidget(self.scrollAreaWidgetContents)

        self.retranslateUi(FilterSearchPanel)
        self.checkboxDateFilter.toggled.connect(self.frameDateRange.setVisible)
        self.buttonClear.clicked.connect(self.lineEditSearch.clear)

        QMetaObject.connectSlotsByName(FilterSearchPanel)
    # setupUi

    def retranslateUi(self, FilterSearchPanel):
        FilterSearchPanel.setWindowTitle(QCoreApplication.translate("FilterSearchPanel", u"Filter Search Panel", None))
        self.searchGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", u"\u691c\u7d22", None))
        self.searchTypeLabel.setText(QCoreApplication.translate("FilterSearchPanel", u"\u691c\u7d22\u5bfe\u8c61:", None))
        self.checkboxTags.setText(QCoreApplication.translate("FilterSearchPanel", u"\u30bf\u30b0", None))
        self.checkboxCaption.setText(QCoreApplication.translate("FilterSearchPanel", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.lineEditSearch.setPlaceholderText(QCoreApplication.translate("FilterSearchPanel", u"\u691c\u7d22\u30ad\u30fc\u30ef\u30fc\u30c9\u3092\u5165\u529b\uff08\u8907\u6570\u30bf\u30b0\u306e\u5834\u5408\u306f\u30ab\u30f3\u30de\u533a\u5207\u308a\uff09...", None))
        self.tagOptionsLabel.setText(QCoreApplication.translate("FilterSearchPanel", u"\u8907\u6570\u30bf\u30b0:", None))
        self.radioAnd.setText(QCoreApplication.translate("FilterSearchPanel", u"\u3059\u3079\u3066\u542b\u3080", None))
        self.radioOr.setText(QCoreApplication.translate("FilterSearchPanel", u"\u3044\u305a\u308c\u304b\u542b\u3080", None))
        self.filterGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", u"\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.resolutionLabel.setText(QCoreApplication.translate("FilterSearchPanel", u"\u89e3\u50cf\u5ea6:", None))
        self.comboResolution.setItemText(0, QCoreApplication.translate("FilterSearchPanel", u"\u5168\u3066", None))
        self.comboResolution.setItemText(1, QCoreApplication.translate("FilterSearchPanel", u"512x512", None))
        self.comboResolution.setItemText(2, QCoreApplication.translate("FilterSearchPanel", u"1024x1024", None))
        self.comboResolution.setItemText(3, QCoreApplication.translate("FilterSearchPanel", u"1280x720", None))
        self.comboResolution.setItemText(4, QCoreApplication.translate("FilterSearchPanel", u"720x1280", None))
        self.comboResolution.setItemText(5, QCoreApplication.translate("FilterSearchPanel", u"1920x1080", None))
        self.comboResolution.setItemText(6, QCoreApplication.translate("FilterSearchPanel", u"1536x1536", None))

        self.aspectRatioLabel.setText(QCoreApplication.translate("FilterSearchPanel", u"\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None))
        self.comboAspectRatio.setItemText(0, QCoreApplication.translate("FilterSearchPanel", u"\u5168\u3066", None))
        self.comboAspectRatio.setItemText(1, QCoreApplication.translate("FilterSearchPanel", u"\u6b63\u65b9\u5f62 (1:1)", None))
        self.comboAspectRatio.setItemText(2, QCoreApplication.translate("FilterSearchPanel", u"\u98a8\u666f (16:9)", None))
        self.comboAspectRatio.setItemText(3, QCoreApplication.translate("FilterSearchPanel", u"\u7e26\u9577 (9:16)", None))
        self.comboAspectRatio.setItemText(4, QCoreApplication.translate("FilterSearchPanel", u"\u98a8\u666f (4:3)", None))
        self.comboAspectRatio.setItemText(5, QCoreApplication.translate("FilterSearchPanel", u"\u7e26\u9577 (3:4)", None))

        self.dateGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", u"\u65e5\u4ed8\u7bc4\u56f2", None))
        self.checkboxDateFilter.setText(QCoreApplication.translate("FilterSearchPanel", u"\u65e5\u4ed8\u7bc4\u56f2\u3067\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.dateRangeSliderPlaceholder.setStyleSheet(QCoreApplication.translate("FilterSearchPanel", u"background-color: #f0f0f0; border: 1px dashed #ccc; padding: 10px;", None))
        self.dateRangeSliderPlaceholder.setText(QCoreApplication.translate("FilterSearchPanel", u"\u65e5\u4ed8\u7bc4\u56f2\u30b9\u30e9\u30a4\u30c0\u30fc (CustomRangeSlider)", None))
        self.ratingGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", u"\u30ec\u30fc\u30c6\u30a3\u30f3\u30b0", None))
        self.ratingLabel.setText(QCoreApplication.translate("FilterSearchPanel", u"\u30ec\u30fc\u30c6\u30a3\u30f3\u30b0:", None))
        self.comboRating.setItemText(0, QCoreApplication.translate("FilterSearchPanel", u"\u5168\u3066", None))
        self.comboRating.setItemText(1, QCoreApplication.translate("FilterSearchPanel", u"PG (\u5168\u5e74\u9f62)", None))
        self.comboRating.setItemText(2, QCoreApplication.translate("FilterSearchPanel", u"PG-13 (\u8efd\u5fae\u306a\u8868\u73fe)", None))
        self.comboRating.setItemText(3, QCoreApplication.translate("FilterSearchPanel", u"R (\u4e2d\u7a0b\u5ea6)", None))
        self.comboRating.setItemText(4, QCoreApplication.translate("FilterSearchPanel", u"X (\u5f37\u3044\u8868\u73fe)", None))
        self.comboRating.setItemText(5, QCoreApplication.translate("FilterSearchPanel", u"XXX (\u904e\u6fc0\u306a\u8868\u73fe)", None))

        self.checkboxIncludeUnrated.setText(QCoreApplication.translate("FilterSearchPanel", u"\u672a\u8a55\u4fa1\u753b\u50cf\u3092\u542b\u3080", None))
        self.optionsGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", u"\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.checkboxOnlyUntagged.setText(QCoreApplication.translate("FilterSearchPanel", u"\u672a\u30bf\u30b0\u753b\u50cf\u306e\u307f\u691c\u7d22", None))
        self.checkboxOnlyUncaptioned.setText(QCoreApplication.translate("FilterSearchPanel", u"\u672a\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u753b\u50cf\u306e\u307f\u691c\u7d22", None))
        self.checkboxExcludeDuplicates.setText(QCoreApplication.translate("FilterSearchPanel", u"\u91cd\u8907\u753b\u50cf\u3092\u9664\u5916", None))
        self.checkboxIncludeNSFW.setText(QCoreApplication.translate("FilterSearchPanel", u"NSFW\u30b3\u30f3\u30c6\u30f3\u30c4\u3092\u542b\u3080", None))
        self.buttonApply.setText(QCoreApplication.translate("FilterSearchPanel", u"\u691c\u7d22\u5b9f\u884c", None))
        self.buttonClear.setText(QCoreApplication.translate("FilterSearchPanel", u"\u30af\u30ea\u30a2", None))
    # retranslateUi

