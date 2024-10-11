# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DatasetExportWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QSizePolicy,
    QSplitter, QVBoxLayout, QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from ImagePreviewWidget import ImagePreviewWidget
from TagFilterWidget import TagFilterWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

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
        self.filterWidget = TagFilterWidget(self.leftPanel)
        self.filterWidget.setObjectName(u"filterWidget")
        self.filterLayout = QVBoxLayout(self.filterWidget)
        self.filterLayout.setObjectName(u"filterLayout")

        self.leftPanelLayout.addWidget(self.filterWidget)

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

        self.exportFormatLabel = QLabel(self.exportGroupBox)
        self.exportFormatLabel.setObjectName(u"exportFormatLabel")

        self.exportLayout.addWidget(self.exportFormatLabel)

        self.exportFormatLayout = QHBoxLayout()
        self.exportFormatLayout.setObjectName(u"exportFormatLayout")
        self.checkBoxTxtCap = QCheckBox(self.exportGroupBox)
        self.checkBoxTxtCap.setObjectName(u"checkBoxTxtCap")
        self.checkBoxTxtCap.setChecked(True)

        self.exportFormatLayout.addWidget(self.checkBoxTxtCap)

        self.checkBoxJson = QCheckBox(self.exportGroupBox)
        self.checkBoxJson.setObjectName(u"checkBoxJson")

        self.exportFormatLayout.addWidget(self.checkBoxJson)


        self.exportLayout.addLayout(self.exportFormatLayout)

        self.latestcheckBox = QCheckBox(self.exportGroupBox)
        self.latestcheckBox.setObjectName(u"latestcheckBox")

        self.exportLayout.addWidget(self.latestcheckBox, 0, Qt.AlignmentFlag.AlignLeft)

        self.exportButton = QPushButton(self.exportGroupBox)
        self.exportButton.setObjectName(u"exportButton")

        self.exportLayout.addWidget(self.exportButton)

        self.exportProgressBar = QProgressBar(self.exportGroupBox)
        self.exportProgressBar.setObjectName(u"exportProgressBar")
        self.exportProgressBar.setValue(0)

        self.exportLayout.addWidget(self.exportProgressBar)

        self.statusLabel = QLabel(self.exportGroupBox)
        self.statusLabel.setObjectName(u"statusLabel")

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
        self.exportFormatLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Format:", None))
        self.checkBoxTxtCap.setText(QCoreApplication.translate("DatasetExportWidget", u"txt/caption", None))
        self.checkBoxJson.setText(QCoreApplication.translate("DatasetExportWidget", u"metadata.json", None))
        self.latestcheckBox.setText(QCoreApplication.translate("DatasetExportWidget", u"\u6700\u5f8c\u306b\u66f4\u65b0\u3055\u308c\u305f\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u3060\u3051\u3092\u51fa\u529b\u3059\u308b", None))
        self.exportButton.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Dataset", None))
        self.statusLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Status: Ready", None))
    # retranslateUi

