
################################################################################
## Form generated from reading UI file 'FilterSearchPanel.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTime,
    QUrl,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_FilterSearchPanel:
    def setupUi(self, FilterSearchPanel):
        if not FilterSearchPanel.objectName():
            FilterSearchPanel.setObjectName("FilterSearchPanel")
        FilterSearchPanel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        FilterSearchPanel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        FilterSearchPanel.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.mainLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.mainLayout.setSpacing(10)
        self.mainLayout.setObjectName("mainLayout")
        self.mainLayout.setContentsMargins(5, 5, 5, 5)
        self.searchGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.searchGroup.setObjectName("searchGroup")
        self.searchLayout = QVBoxLayout(self.searchGroup)
        self.searchLayout.setObjectName("searchLayout")
        self.searchTypeLayout = QHBoxLayout()
        self.searchTypeLayout.setObjectName("searchTypeLayout")
        self.searchTypeLabel = QLabel(self.searchGroup)
        self.searchTypeLabel.setObjectName("searchTypeLabel")

        self.searchTypeLayout.addWidget(self.searchTypeLabel)

        self.checkboxTags = QCheckBox(self.searchGroup)
        self.checkboxTags.setObjectName("checkboxTags")
        self.checkboxTags.setChecked(True)

        self.searchTypeLayout.addWidget(self.checkboxTags)

        self.checkboxCaption = QCheckBox(self.searchGroup)
        self.checkboxCaption.setObjectName("checkboxCaption")

        self.searchTypeLayout.addWidget(self.checkboxCaption)

        self.searchTypeSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.searchTypeLayout.addItem(self.searchTypeSpacer)


        self.searchLayout.addLayout(self.searchTypeLayout)

        self.lineEditSearch = QLineEdit(self.searchGroup)
        self.lineEditSearch.setObjectName("lineEditSearch")

        self.searchLayout.addWidget(self.lineEditSearch)

        self.tagOptionsLayout = QHBoxLayout()
        self.tagOptionsLayout.setObjectName("tagOptionsLayout")
        self.tagOptionsLabel = QLabel(self.searchGroup)
        self.tagOptionsLabel.setObjectName("tagOptionsLabel")

        self.tagOptionsLayout.addWidget(self.tagOptionsLabel)

        self.radioAnd = QRadioButton(self.searchGroup)
        self.radioAnd.setObjectName("radioAnd")
        self.radioAnd.setChecked(True)

        self.tagOptionsLayout.addWidget(self.radioAnd)

        self.radioOr = QRadioButton(self.searchGroup)
        self.radioOr.setObjectName("radioOr")

        self.tagOptionsLayout.addWidget(self.radioOr)

        self.tagOptionsSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.tagOptionsLayout.addItem(self.tagOptionsSpacer)


        self.searchLayout.addLayout(self.tagOptionsLayout)


        self.mainLayout.addWidget(self.searchGroup)

        self.filterGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.filterGroup.setObjectName("filterGroup")
        self.filterLayout = QVBoxLayout(self.filterGroup)
        self.filterLayout.setObjectName("filterLayout")
        self.resolutionLayout = QHBoxLayout()
        self.resolutionLayout.setObjectName("resolutionLayout")
        self.resolutionLabel = QLabel(self.filterGroup)
        self.resolutionLabel.setObjectName("resolutionLabel")

        self.resolutionLayout.addWidget(self.resolutionLabel)

        self.comboResolution = QComboBox(self.filterGroup)
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.addItem("")
        self.comboResolution.setObjectName("comboResolution")

        self.resolutionLayout.addWidget(self.comboResolution)

        self.resolutionSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.resolutionLayout.addItem(self.resolutionSpacer)


        self.filterLayout.addLayout(self.resolutionLayout)

        self.aspectRatioLayout = QHBoxLayout()
        self.aspectRatioLayout.setObjectName("aspectRatioLayout")
        self.aspectRatioLabel = QLabel(self.filterGroup)
        self.aspectRatioLabel.setObjectName("aspectRatioLabel")

        self.aspectRatioLayout.addWidget(self.aspectRatioLabel)

        self.comboAspectRatio = QComboBox(self.filterGroup)
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.addItem("")
        self.comboAspectRatio.setObjectName("comboAspectRatio")

        self.aspectRatioLayout.addWidget(self.comboAspectRatio)

        self.aspectRatioSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.aspectRatioLayout.addItem(self.aspectRatioSpacer)


        self.filterLayout.addLayout(self.aspectRatioLayout)


        self.mainLayout.addWidget(self.filterGroup)

        self.dateGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.dateGroup.setObjectName("dateGroup")
        self.dateLayout = QVBoxLayout(self.dateGroup)
        self.dateLayout.setObjectName("dateLayout")
        self.checkboxDateFilter = QCheckBox(self.dateGroup)
        self.checkboxDateFilter.setObjectName("checkboxDateFilter")

        self.dateLayout.addWidget(self.checkboxDateFilter)

        self.frameDateRange = QFrame(self.dateGroup)
        self.frameDateRange.setObjectName("frameDateRange")
        self.frameDateRange.setVisible(False)
        self.frameDateRange.setFrameShape(QFrame.Shape.NoFrame)
        self.dateRangeLayout = QVBoxLayout(self.frameDateRange)
        self.dateRangeLayout.setObjectName("dateRangeLayout")
        self.dateRangeLayout.setContentsMargins(0, 0, 0, 0)
        self.dateRangeSliderPlaceholder = QLabel(self.frameDateRange)
        self.dateRangeSliderPlaceholder.setObjectName("dateRangeSliderPlaceholder")
        self.dateRangeSliderPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.dateRangeLayout.addWidget(self.dateRangeSliderPlaceholder)


        self.dateLayout.addWidget(self.frameDateRange)


        self.mainLayout.addWidget(self.dateGroup)

        self.optionsGroup = QGroupBox(self.scrollAreaWidgetContents)
        self.optionsGroup.setObjectName("optionsGroup")
        self.optionsLayout = QVBoxLayout(self.optionsGroup)
        self.optionsLayout.setObjectName("optionsLayout")
        self.checkboxOnlyUntagged = QCheckBox(self.optionsGroup)
        self.checkboxOnlyUntagged.setObjectName("checkboxOnlyUntagged")

        self.optionsLayout.addWidget(self.checkboxOnlyUntagged)

        self.checkboxOnlyUncaptioned = QCheckBox(self.optionsGroup)
        self.checkboxOnlyUncaptioned.setObjectName("checkboxOnlyUncaptioned")

        self.optionsLayout.addWidget(self.checkboxOnlyUncaptioned)

        self.checkboxExcludeDuplicates = QCheckBox(self.optionsGroup)
        self.checkboxExcludeDuplicates.setObjectName("checkboxExcludeDuplicates")

        self.optionsLayout.addWidget(self.checkboxExcludeDuplicates)

        self.checkboxIncludeNSFW = QCheckBox(self.optionsGroup)
        self.checkboxIncludeNSFW.setObjectName("checkboxIncludeNSFW")

        self.optionsLayout.addWidget(self.checkboxIncludeNSFW)


        self.mainLayout.addWidget(self.optionsGroup)

        self.actionLayout = QHBoxLayout()
        self.actionLayout.setObjectName("actionLayout")
        self.buttonApply = QPushButton(self.scrollAreaWidgetContents)
        self.buttonApply.setObjectName("buttonApply")

        self.actionLayout.addWidget(self.buttonApply)

        self.buttonClear = QPushButton(self.scrollAreaWidgetContents)
        self.buttonClear.setObjectName("buttonClear")

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
        FilterSearchPanel.setWindowTitle(QCoreApplication.translate("FilterSearchPanel", "Filter Search Panel", None))
        self.searchGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", "\u691c\u7d22", None))
        self.searchTypeLabel.setText(QCoreApplication.translate("FilterSearchPanel", "\u691c\u7d22\u5bfe\u8c61:", None))
        self.checkboxTags.setText(QCoreApplication.translate("FilterSearchPanel", "\u30bf\u30b0", None))
        self.checkboxCaption.setText(QCoreApplication.translate("FilterSearchPanel", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.lineEditSearch.setPlaceholderText(QCoreApplication.translate("FilterSearchPanel", "\u691c\u7d22\u30ad\u30fc\u30ef\u30fc\u30c9\u3092\u5165\u529b\uff08\u8907\u6570\u30bf\u30b0\u306e\u5834\u5408\u306f\u30ab\u30f3\u30de\u533a\u5207\u308a\uff09...", None))
        self.tagOptionsLabel.setText(QCoreApplication.translate("FilterSearchPanel", "\u8907\u6570\u30bf\u30b0:", None))
        self.radioAnd.setText(QCoreApplication.translate("FilterSearchPanel", "\u3059\u3079\u3066\u542b\u3080", None))
        self.radioOr.setText(QCoreApplication.translate("FilterSearchPanel", "\u3044\u305a\u308c\u304b\u542b\u3080", None))
        self.filterGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", "\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.resolutionLabel.setText(QCoreApplication.translate("FilterSearchPanel", "\u89e3\u50cf\u5ea6:", None))
        self.comboResolution.setItemText(0, QCoreApplication.translate("FilterSearchPanel", "\u5168\u3066", None))
        self.comboResolution.setItemText(1, QCoreApplication.translate("FilterSearchPanel", "512x512", None))
        self.comboResolution.setItemText(2, QCoreApplication.translate("FilterSearchPanel", "1024x1024", None))
        self.comboResolution.setItemText(3, QCoreApplication.translate("FilterSearchPanel", "1280x720", None))
        self.comboResolution.setItemText(4, QCoreApplication.translate("FilterSearchPanel", "720x1280", None))
        self.comboResolution.setItemText(5, QCoreApplication.translate("FilterSearchPanel", "1920x1080", None))
        self.comboResolution.setItemText(6, QCoreApplication.translate("FilterSearchPanel", "1536x1536", None))

        self.aspectRatioLabel.setText(QCoreApplication.translate("FilterSearchPanel", "\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None))
        self.comboAspectRatio.setItemText(0, QCoreApplication.translate("FilterSearchPanel", "\u5168\u3066", None))
        self.comboAspectRatio.setItemText(1, QCoreApplication.translate("FilterSearchPanel", "\u6b63\u65b9\u5f62 (1:1)", None))
        self.comboAspectRatio.setItemText(2, QCoreApplication.translate("FilterSearchPanel", "\u98a8\u666f (16:9)", None))
        self.comboAspectRatio.setItemText(3, QCoreApplication.translate("FilterSearchPanel", "\u7e26\u9577 (9:16)", None))
        self.comboAspectRatio.setItemText(4, QCoreApplication.translate("FilterSearchPanel", "\u98a8\u666f (4:3)", None))
        self.comboAspectRatio.setItemText(5, QCoreApplication.translate("FilterSearchPanel", "\u7e26\u9577 (3:4)", None))

        self.dateGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", "\u65e5\u4ed8\u7bc4\u56f2", None))
        self.checkboxDateFilter.setText(QCoreApplication.translate("FilterSearchPanel", "\u65e5\u4ed8\u7bc4\u56f2\u3067\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.dateRangeSliderPlaceholder.setStyleSheet(QCoreApplication.translate("FilterSearchPanel", "background-color: #f0f0f0; border: 1px dashed #ccc; padding: 10px;", None))
        self.dateRangeSliderPlaceholder.setText(QCoreApplication.translate("FilterSearchPanel", "\u65e5\u4ed8\u7bc4\u56f2\u30b9\u30e9\u30a4\u30c0\u30fc (CustomRangeSlider)", None))
        self.optionsGroup.setTitle(QCoreApplication.translate("FilterSearchPanel", "\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.checkboxOnlyUntagged.setText(QCoreApplication.translate("FilterSearchPanel", "\u672a\u30bf\u30b0\u753b\u50cf\u306e\u307f\u691c\u7d22", None))
        self.checkboxOnlyUncaptioned.setText(QCoreApplication.translate("FilterSearchPanel", "\u672a\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u753b\u50cf\u306e\u307f\u691c\u7d22", None))
        self.checkboxExcludeDuplicates.setText(QCoreApplication.translate("FilterSearchPanel", "\u91cd\u8907\u753b\u50cf\u3092\u9664\u5916", None))
        self.checkboxIncludeNSFW.setText(QCoreApplication.translate("FilterSearchPanel", "NSFW\u30b3\u30f3\u30c6\u30f3\u30c4\u3092\u542b\u3080", None))
        self.buttonApply.setText(QCoreApplication.translate("FilterSearchPanel", "\u691c\u7d22\u5b9f\u884c", None))
        self.buttonClear.setText(QCoreApplication.translate("FilterSearchPanel", "\u30af\u30ea\u30a2", None))
    # retranslateUi

