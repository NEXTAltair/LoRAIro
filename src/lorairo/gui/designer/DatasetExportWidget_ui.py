# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DatasetExportWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
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
    QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QRadioButton, QSizePolicy, QSplitter, QTextEdit,
    QVBoxLayout, QWidget)

from ..widgets.directory_picker import DirectoryPickerWidget
from ..widgets.filter import TagFilterWidget
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget

class Ui_DatasetExportWidget(object):
    def setupUi(self, DatasetExportWidget):
        if not DatasetExportWidget.objectName():
            DatasetExportWidget.setObjectName(u"DatasetExportWidget")
        DatasetExportWidget.resize(1200, 800)
        self.mainLayout = QHBoxLayout(DatasetExportWidget)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainSplitter = QSplitter(DatasetExportWidget)
        self.mainSplitter.setObjectName(u"mainSplitter")
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.leftPanel = QWidget(self.mainSplitter)
        self.leftPanel.setObjectName(u"leftPanel")
        self.leftPanelLayout = QVBoxLayout(self.leftPanel)
        self.leftPanelLayout.setObjectName(u"leftPanelLayout")
        self.leftPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.dbSearchWidget = TagFilterWidget(self.leftPanel)
        self.dbSearchWidget.setObjectName(u"dbSearchWidget")
        self.filterLayout = QVBoxLayout(self.dbSearchWidget)
        self.filterLayout.setObjectName(u"filterLayout")

        self.leftPanelLayout.addWidget(self.dbSearchWidget)

        self.thumbnailSelector = ThumbnailSelectorWidget(self.leftPanel)
        self.thumbnailSelector.setObjectName(u"thumbnailSelector")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.thumbnailSelector.sizePolicy().hasHeightForWidth())
        self.thumbnailSelector.setSizePolicy(sizePolicy)

        self.leftPanelLayout.addWidget(self.thumbnailSelector)

        self.imageCountLabel = QLabel(self.leftPanel)
        self.imageCountLabel.setObjectName(u"imageCountLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.imageCountLabel.sizePolicy().hasHeightForWidth())
        self.imageCountLabel.setSizePolicy(sizePolicy1)

        self.leftPanelLayout.addWidget(self.imageCountLabel)

        self.mainSplitter.addWidget(self.leftPanel)
        self.rightPanel = QWidget(self.mainSplitter)
        self.rightPanel.setObjectName(u"rightPanel")
        self.rightPanelLayout = QVBoxLayout(self.rightPanel)
        self.rightPanelLayout.setObjectName(u"rightPanelLayout")
        self.rightPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.imagePreview = ImagePreviewWidget(self.rightPanel)
        self.imagePreview.setObjectName(u"imagePreview")
        sizePolicy.setHeightForWidth(self.imagePreview.sizePolicy().hasHeightForWidth())
        self.imagePreview.setSizePolicy(sizePolicy)

        self.rightPanelLayout.addWidget(self.imagePreview)

        self.exportGroupBox = QGroupBox(self.rightPanel)
        self.exportGroupBox.setObjectName(u"exportGroupBox")
        self.exportLayout = QVBoxLayout(self.exportGroupBox)
        self.exportLayout.setObjectName(u"exportLayout")
        self.exportDirectoryPicker = DirectoryPickerWidget(self.exportGroupBox)
        self.exportDirectoryPicker.setObjectName(u"exportDirectoryPicker")

        self.exportLayout.addWidget(self.exportDirectoryPicker)

        self.resolutionLabel = QLabel(self.exportGroupBox)
        self.resolutionLabel.setObjectName(u"resolutionLabel")
        sizePolicy1.setHeightForWidth(self.resolutionLabel.sizePolicy().hasHeightForWidth())
        self.resolutionLabel.setSizePolicy(sizePolicy1)

        self.exportLayout.addWidget(self.resolutionLabel)

        self.comboBoxResolution = QComboBox(self.exportGroupBox)
        self.comboBoxResolution.addItem("")
        self.comboBoxResolution.addItem("")
        self.comboBoxResolution.addItem("")
        self.comboBoxResolution.addItem("")
        self.comboBoxResolution.setObjectName(u"comboBoxResolution")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.comboBoxResolution.sizePolicy().hasHeightForWidth())
        self.comboBoxResolution.setSizePolicy(sizePolicy2)

        self.exportLayout.addWidget(self.comboBoxResolution)

        self.exportFormatLabel = QLabel(self.exportGroupBox)
        self.exportFormatLabel.setObjectName(u"exportFormatLabel")
        sizePolicy1.setHeightForWidth(self.exportFormatLabel.sizePolicy().hasHeightForWidth())
        self.exportFormatLabel.setSizePolicy(sizePolicy1)

        self.exportLayout.addWidget(self.exportFormatLabel)

        self.formatSelectionLayout = QVBoxLayout()
        self.formatSelectionLayout.setObjectName(u"formatSelectionLayout")
        self.radioTxtSeparate = QRadioButton(self.exportGroupBox)
        self.radioTxtSeparate.setObjectName(u"radioTxtSeparate")
        self.radioTxtSeparate.setChecked(True)

        self.formatSelectionLayout.addWidget(self.radioTxtSeparate)

        self.radioTxtMerged = QRadioButton(self.exportGroupBox)
        self.radioTxtMerged.setObjectName(u"radioTxtMerged")

        self.formatSelectionLayout.addWidget(self.radioTxtMerged)

        self.radioJson = QRadioButton(self.exportGroupBox)
        self.radioJson.setObjectName(u"radioJson")

        self.formatSelectionLayout.addWidget(self.radioJson)


        self.exportLayout.addLayout(self.formatSelectionLayout)

        self.latestOnlyCheckBox = QCheckBox(self.exportGroupBox)
        self.latestOnlyCheckBox.setObjectName(u"latestOnlyCheckBox")

        self.exportLayout.addWidget(self.latestOnlyCheckBox)

        self.validationResultsLabel = QLabel(self.exportGroupBox)
        self.validationResultsLabel.setObjectName(u"validationResultsLabel")
        sizePolicy1.setHeightForWidth(self.validationResultsLabel.sizePolicy().hasHeightForWidth())
        self.validationResultsLabel.setSizePolicy(sizePolicy1)

        self.exportLayout.addWidget(self.validationResultsLabel)

        self.validationStatsLayout = QHBoxLayout()
        self.validationStatsLayout.setObjectName(u"validationStatsLayout")
        self.totalImagesLabel = QLabel(self.exportGroupBox)
        self.totalImagesLabel.setObjectName(u"totalImagesLabel")
        sizePolicy1.setHeightForWidth(self.totalImagesLabel.sizePolicy().hasHeightForWidth())
        self.totalImagesLabel.setSizePolicy(sizePolicy1)

        self.validationStatsLayout.addWidget(self.totalImagesLabel)

        self.validImagesLabel = QLabel(self.exportGroupBox)
        self.validImagesLabel.setObjectName(u"validImagesLabel")
        sizePolicy1.setHeightForWidth(self.validImagesLabel.sizePolicy().hasHeightForWidth())
        self.validImagesLabel.setSizePolicy(sizePolicy1)

        self.validationStatsLayout.addWidget(self.validImagesLabel)

        self.errorCountLabel = QLabel(self.exportGroupBox)
        self.errorCountLabel.setObjectName(u"errorCountLabel")
        sizePolicy1.setHeightForWidth(self.errorCountLabel.sizePolicy().hasHeightForWidth())
        self.errorCountLabel.setSizePolicy(sizePolicy1)

        self.validationStatsLayout.addWidget(self.errorCountLabel)


        self.exportLayout.addLayout(self.validationStatsLayout)

        self.validationDetailsText = QTextEdit(self.exportGroupBox)
        self.validationDetailsText.setObjectName(u"validationDetailsText")
        sizePolicy.setHeightForWidth(self.validationDetailsText.sizePolicy().hasHeightForWidth())
        self.validationDetailsText.setSizePolicy(sizePolicy)
        self.validationDetailsText.setMaximumSize(QSize(16777215, 100))
        self.validationDetailsText.setReadOnly(True)

        self.exportLayout.addWidget(self.validationDetailsText)

        self.actionButtonsLayout = QHBoxLayout()
        self.actionButtonsLayout.setObjectName(u"actionButtonsLayout")
        self.validateButton = QPushButton(self.exportGroupBox)
        self.validateButton.setObjectName(u"validateButton")
        sizePolicy2.setHeightForWidth(self.validateButton.sizePolicy().hasHeightForWidth())
        self.validateButton.setSizePolicy(sizePolicy2)

        self.actionButtonsLayout.addWidget(self.validateButton)

        self.exportButton = QPushButton(self.exportGroupBox)
        self.exportButton.setObjectName(u"exportButton")
        self.exportButton.setEnabled(False)
        sizePolicy2.setHeightForWidth(self.exportButton.sizePolicy().hasHeightForWidth())
        self.exportButton.setSizePolicy(sizePolicy2)

        self.actionButtonsLayout.addWidget(self.exportButton)


        self.exportLayout.addLayout(self.actionButtonsLayout)

        self.controlButtonsLayout = QHBoxLayout()
        self.controlButtonsLayout.setObjectName(u"controlButtonsLayout")
        self.cancelButton = QPushButton(self.exportGroupBox)
        self.cancelButton.setObjectName(u"cancelButton")
        self.cancelButton.setEnabled(False)
        sizePolicy2.setHeightForWidth(self.cancelButton.sizePolicy().hasHeightForWidth())
        self.cancelButton.setSizePolicy(sizePolicy2)

        self.controlButtonsLayout.addWidget(self.cancelButton)

        self.closeButton = QPushButton(self.exportGroupBox)
        self.closeButton.setObjectName(u"closeButton")
        sizePolicy2.setHeightForWidth(self.closeButton.sizePolicy().hasHeightForWidth())
        self.closeButton.setSizePolicy(sizePolicy2)

        self.controlButtonsLayout.addWidget(self.closeButton)


        self.exportLayout.addLayout(self.controlButtonsLayout)

        self.exportProgressBar = QProgressBar(self.exportGroupBox)
        self.exportProgressBar.setObjectName(u"exportProgressBar")
        self.exportProgressBar.setValue(0)
        self.exportProgressBar.setVisible(False)
        sizePolicy2.setHeightForWidth(self.exportProgressBar.sizePolicy().hasHeightForWidth())
        self.exportProgressBar.setSizePolicy(sizePolicy2)

        self.exportLayout.addWidget(self.exportProgressBar)

        self.statusLabel = QLabel(self.exportGroupBox)
        self.statusLabel.setObjectName(u"statusLabel")
        sizePolicy1.setHeightForWidth(self.statusLabel.sizePolicy().hasHeightForWidth())
        self.statusLabel.setSizePolicy(sizePolicy1)

        self.exportLayout.addWidget(self.statusLabel)


        self.rightPanelLayout.addWidget(self.exportGroupBox)

        self.mainSplitter.addWidget(self.rightPanel)

        self.mainLayout.addWidget(self.mainSplitter)


        self.retranslateUi(DatasetExportWidget)

        QMetaObject.connectSlotsByName(DatasetExportWidget)
    # setupUi

    def retranslateUi(self, DatasetExportWidget):
        DatasetExportWidget.setWindowTitle(QCoreApplication.translate("DatasetExportWidget", u"Dataset Export", None))
        self.imageCountLabel.setText("")
        self.exportGroupBox.setTitle(QCoreApplication.translate("DatasetExportWidget", u"Export Settings", None))
        self.resolutionLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u51e6\u7406\u6e08\u307f\u753b\u50cf\u89e3\u50cf\u5ea6:", None))
        self.comboBoxResolution.setItemText(0, QCoreApplication.translate("DatasetExportWidget", u"512px", None))
        self.comboBoxResolution.setItemText(1, QCoreApplication.translate("DatasetExportWidget", u"768px", None))
        self.comboBoxResolution.setItemText(2, QCoreApplication.translate("DatasetExportWidget", u"1024px", None))
        self.comboBoxResolution.setItemText(3, QCoreApplication.translate("DatasetExportWidget", u"1536px", None))

        self.exportFormatLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8\u5f62\u5f0f:", None))
        self.radioTxtSeparate.setText(QCoreApplication.translate("DatasetExportWidget", u"TXT\u5f62\u5f0f\uff08\u30bf\u30b0+\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u5225\u30d5\u30a1\u30a4\u30eb\uff09", None))
        self.radioTxtMerged.setText(QCoreApplication.translate("DatasetExportWidget", u"TXT\u5f62\u5f0f\uff08\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u7d71\u5408\uff09", None))
        self.radioJson.setText(QCoreApplication.translate("DatasetExportWidget", u"JSON\u5f62\u5f0f\uff08metadata.json\uff09", None))
        self.latestOnlyCheckBox.setText(QCoreApplication.translate("DatasetExportWidget", u"\u6700\u65b0\u306e\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u306e\u307f\u4f7f\u7528", None))
        self.validationResultsLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u691c\u8a3c\u7d50\u679c:", None))
        self.totalImagesLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u5bfe\u8c61\u753b\u50cf\u6570: --", None))
        self.validImagesLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8\u53ef\u80fd: --", None))
        self.errorCountLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u30a8\u30e9\u30fc: --", None))
        self.validationDetailsText.setPlaceholderText(QCoreApplication.translate("DatasetExportWidget", u"\u691c\u8a3c\u5b9f\u884c\u30dc\u30bf\u30f3\u3092\u30af\u30ea\u30c3\u30af\u3057\u3066\u8a73\u7d30\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002", None))
        self.validateButton.setText(QCoreApplication.translate("DatasetExportWidget", u"\u691c\u8a3c\u5b9f\u884c", None))
        self.exportButton.setText(QCoreApplication.translate("DatasetExportWidget", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8\u958b\u59cb", None))
        self.cancelButton.setText(QCoreApplication.translate("DatasetExportWidget", u"\u30ad\u30e3\u30f3\u30bb\u30eb", None))
        self.closeButton.setText(QCoreApplication.translate("DatasetExportWidget", u"\u9589\u3058\u308b", None))
        self.statusLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u6e96\u5099\u5b8c\u4e86", None))
    # retranslateUi

