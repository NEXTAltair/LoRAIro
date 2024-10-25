# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DatasetExportWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.8.0
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from ImagePreviewWidget import ImagePreviewWidget
from TagFilterWidget import TagFilterWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_DatasetExportWidget(object):
    def setupUi(self, DatasetExportWidget):
        if not DatasetExportWidget.objectName():
            DatasetExportWidget.setObjectName(u"DatasetExportWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(DatasetExportWidget.sizePolicy().hasHeightForWidth())
        DatasetExportWidget.setSizePolicy(sizePolicy)
        self.horizontalLayout = QHBoxLayout(DatasetExportWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.Lsplitter = QSplitter(DatasetExportWidget)
        self.Lsplitter.setObjectName(u"Lsplitter")
        sizePolicy.setHeightForWidth(self.Lsplitter.sizePolicy().hasHeightForWidth())
        self.Lsplitter.setSizePolicy(sizePolicy)
        self.Lsplitter.setMinimumSize(QSize(250, 0))
        self.Lsplitter.setMaximumSize(QSize(16777215, 16777215))
        self.Lsplitter.setOrientation(Qt.Orientation.Vertical)
        self.dbSearchWidget = TagFilterWidget(self.Lsplitter)
        self.dbSearchWidget.setObjectName(u"dbSearchWidget")
        self.Lsplitter.addWidget(self.dbSearchWidget)
        self.exportGroupBox = QGroupBox(self.Lsplitter)
        self.exportGroupBox.setObjectName(u"exportGroupBox")
        self.gridLayout = QGridLayout(self.exportGroupBox)
        self.gridLayout.setObjectName(u"gridLayout")
        self.exportDirectoryPicker = DirectoryPickerWidget(self.exportGroupBox)
        self.exportDirectoryPicker.setObjectName(u"exportDirectoryPicker")

        self.gridLayout.addWidget(self.exportDirectoryPicker, 0, 0, 1, 1)

        self.exportFormatLabel = QLabel(self.exportGroupBox)
        self.exportFormatLabel.setObjectName(u"exportFormatLabel")

        self.gridLayout.addWidget(self.exportFormatLabel, 1, 0, 1, 1)

        self.exportFormatLayout = QHBoxLayout()
        self.exportFormatLayout.setObjectName(u"exportFormatLayout")
        self.checkBoxTxtCap = QCheckBox(self.exportGroupBox)
        self.checkBoxTxtCap.setObjectName(u"checkBoxTxtCap")
        self.checkBoxTxtCap.setChecked(True)

        self.exportFormatLayout.addWidget(self.checkBoxTxtCap)

        self.checkBoxJson = QCheckBox(self.exportGroupBox)
        self.checkBoxJson.setObjectName(u"checkBoxJson")

        self.exportFormatLayout.addWidget(self.checkBoxJson)


        self.gridLayout.addLayout(self.exportFormatLayout, 2, 0, 1, 1)

        self.latestcheckBox = QCheckBox(self.exportGroupBox)
        self.latestcheckBox.setObjectName(u"latestcheckBox")

        self.gridLayout.addWidget(self.latestcheckBox, 3, 0, 1, 1)

        self.MergeCaptionWithTagscheckBox = QCheckBox(self.exportGroupBox)
        self.MergeCaptionWithTagscheckBox.setObjectName(u"MergeCaptionWithTagscheckBox")

        self.gridLayout.addWidget(self.MergeCaptionWithTagscheckBox, 4, 0, 1, 1)

        self.exportButton = QPushButton(self.exportGroupBox)
        self.exportButton.setObjectName(u"exportButton")

        self.gridLayout.addWidget(self.exportButton, 5, 0, 1, 1)

        self.exportProgressBar = QProgressBar(self.exportGroupBox)
        self.exportProgressBar.setObjectName(u"exportProgressBar")
        self.exportProgressBar.setValue(0)

        self.gridLayout.addWidget(self.exportProgressBar, 6, 0, 1, 1)

        self.statusLabel = QLabel(self.exportGroupBox)
        self.statusLabel.setObjectName(u"statusLabel")

        self.gridLayout.addWidget(self.statusLabel, 7, 0, 1, 1)

        self.imageCountLabel = QLabel(self.exportGroupBox)
        self.imageCountLabel.setObjectName(u"imageCountLabel")

        self.gridLayout.addWidget(self.imageCountLabel, 8, 0, 1, 1)

        self.Lsplitter.addWidget(self.exportGroupBox)

        self.horizontalLayout.addWidget(self.Lsplitter)

        self.ImageSplitter = QSplitter(DatasetExportWidget)
        self.ImageSplitter.setObjectName(u"ImageSplitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(2)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.ImageSplitter.sizePolicy().hasHeightForWidth())
        self.ImageSplitter.setSizePolicy(sizePolicy1)
        self.ImageSplitter.setMinimumSize(QSize(350, 0))
        self.ImageSplitter.setMaximumSize(QSize(600, 16777215))
        self.ImageSplitter.setOrientation(Qt.Orientation.Vertical)
        self.imagePreview = ImagePreviewWidget(self.ImageSplitter)
        self.imagePreview.setObjectName(u"imagePreview")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.imagePreview.sizePolicy().hasHeightForWidth())
        self.imagePreview.setSizePolicy(sizePolicy2)
        self.imagePreview.setMaximumSize(QSize(600, 16777215))
        self.ImageSplitter.addWidget(self.imagePreview)
        self.thumbnailSelector = ThumbnailSelectorWidget(self.ImageSplitter)
        self.thumbnailSelector.setObjectName(u"thumbnailSelector")
        sizePolicy2.setHeightForWidth(self.thumbnailSelector.sizePolicy().hasHeightForWidth())
        self.thumbnailSelector.setSizePolicy(sizePolicy2)
        self.thumbnailSelector.setMinimumSize(QSize(250, 0))
        self.thumbnailSelector.setMaximumSize(QSize(750, 16777215))
        self.ImageSplitter.addWidget(self.thumbnailSelector)

        self.horizontalLayout.addWidget(self.ImageSplitter)


        self.retranslateUi(DatasetExportWidget)

        QMetaObject.connectSlotsByName(DatasetExportWidget)
    # setupUi

    def retranslateUi(self, DatasetExportWidget):
        DatasetExportWidget.setWindowTitle(QCoreApplication.translate("DatasetExportWidget", u"Dataset Export", None))
        self.exportGroupBox.setTitle(QCoreApplication.translate("DatasetExportWidget", u"Export Settings", None))
        self.exportFormatLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Format:", None))
        self.checkBoxTxtCap.setText(QCoreApplication.translate("DatasetExportWidget", u"txt/caption", None))
        self.checkBoxJson.setText(QCoreApplication.translate("DatasetExportWidget", u"metadata.json", None))
        self.latestcheckBox.setText(QCoreApplication.translate("DatasetExportWidget", u"\u6700\u5f8c\u306b\u66f4\u65b0\u3055\u308c\u305f\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u3060\u3051\u3092\u51fa\u529b\u3059\u308b", None))
        self.MergeCaptionWithTagscheckBox.setText(QCoreApplication.translate("DatasetExportWidget", u"caption\u3068\u3057\u3066\u4fdd\u5b58\u3055\u308c\u305f\u6587\u5b57\u5217\u3082 \".tag\" \u306b\u4fdd\u5b58\u3059\u308b", None))
        self.exportButton.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Dataset", None))
        self.statusLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Status: Ready", None))
        self.imageCountLabel.setText("")
    # retranslateUi

