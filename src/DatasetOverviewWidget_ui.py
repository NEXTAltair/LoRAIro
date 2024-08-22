# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DatasetOverviewWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QSizePolicy, QSplitter,
    QTextEdit, QVBoxLayout, QWidget)

from ImagePreviewWidget import ImagePreviewWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_DatasetOverviewWidget(object):
    def setupUi(self, DatasetOverviewWidget):
        if not DatasetOverviewWidget.objectName():
            DatasetOverviewWidget.setObjectName(u"DatasetOverviewWidget")
        DatasetOverviewWidget.resize(690, 788)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DatasetOverviewWidget.sizePolicy().hasHeightForWidth())
        DatasetOverviewWidget.setSizePolicy(sizePolicy)
        self.horizontalDatasetOverviewWidget = QHBoxLayout(DatasetOverviewWidget)
        self.horizontalDatasetOverviewWidget.setObjectName(u"horizontalDatasetOverviewWidget")
        self.mainSplitter = QSplitter(DatasetOverviewWidget)
        self.mainSplitter.setObjectName(u"mainSplitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.mainSplitter.sizePolicy().hasHeightForWidth())
        self.mainSplitter.setSizePolicy(sizePolicy1)
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.ImagePreview = ImagePreviewWidget(self.mainSplitter)
        self.ImagePreview.setObjectName(u"ImagePreview")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(2)
        sizePolicy2.setVerticalStretch(2)
        sizePolicy2.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy2)
        self.ImagePreview.setMinimumSize(QSize(512, 512))
        self.mainSplitter.addWidget(self.ImagePreview)
        self.infoContainer = QWidget(self.mainSplitter)
        self.infoContainer.setObjectName(u"infoContainer")
        sizePolicy1.setHeightForWidth(self.infoContainer.sizePolicy().hasHeightForWidth())
        self.infoContainer.setSizePolicy(sizePolicy1)
        self.verticalLayout = QVBoxLayout(self.infoContainer)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.infoSplitter = QSplitter(self.infoContainer)
        self.infoSplitter.setObjectName(u"infoSplitter")
        self.infoSplitter.setOrientation(Qt.Orientation.Vertical)
        self.metadataGroupBox = QGroupBox(self.infoSplitter)
        self.metadataGroupBox.setObjectName(u"metadataGroupBox")
        self.metadataGroupBox.setMinimumSize(QSize(0, 64))
        self.metadataLayout = QFormLayout(self.metadataGroupBox)
        self.metadataLayout.setObjectName(u"metadataLayout")
        self.fileNameLabel = QLabel(self.metadataGroupBox)
        self.fileNameLabel.setObjectName(u"fileNameLabel")

        self.metadataLayout.setWidget(0, QFormLayout.LabelRole, self.fileNameLabel)

        self.fileNameValueLabel = QLabel(self.metadataGroupBox)
        self.fileNameValueLabel.setObjectName(u"fileNameValueLabel")

        self.metadataLayout.setWidget(0, QFormLayout.FieldRole, self.fileNameValueLabel)

        self.imagePathLabel = QLabel(self.metadataGroupBox)
        self.imagePathLabel.setObjectName(u"imagePathLabel")

        self.metadataLayout.setWidget(1, QFormLayout.LabelRole, self.imagePathLabel)

        self.imagePathValueLabel = QLabel(self.metadataGroupBox)
        self.imagePathValueLabel.setObjectName(u"imagePathValueLabel")

        self.metadataLayout.setWidget(1, QFormLayout.FieldRole, self.imagePathValueLabel)

        self.extensionLabel = QLabel(self.metadataGroupBox)
        self.extensionLabel.setObjectName(u"extensionLabel")

        self.metadataLayout.setWidget(2, QFormLayout.LabelRole, self.extensionLabel)

        self.extensionValueLabel = QLabel(self.metadataGroupBox)
        self.extensionValueLabel.setObjectName(u"extensionValueLabel")

        self.metadataLayout.setWidget(2, QFormLayout.FieldRole, self.extensionValueLabel)

        self.formatLabel = QLabel(self.metadataGroupBox)
        self.formatLabel.setObjectName(u"formatLabel")

        self.metadataLayout.setWidget(3, QFormLayout.LabelRole, self.formatLabel)

        self.formatValueLabel = QLabel(self.metadataGroupBox)
        self.formatValueLabel.setObjectName(u"formatValueLabel")

        self.metadataLayout.setWidget(3, QFormLayout.FieldRole, self.formatValueLabel)

        self.modeLabel = QLabel(self.metadataGroupBox)
        self.modeLabel.setObjectName(u"modeLabel")

        self.metadataLayout.setWidget(4, QFormLayout.LabelRole, self.modeLabel)

        self.modeValueLabel = QLabel(self.metadataGroupBox)
        self.modeValueLabel.setObjectName(u"modeValueLabel")

        self.metadataLayout.setWidget(4, QFormLayout.FieldRole, self.modeValueLabel)

        self.alphaChannelLabel = QLabel(self.metadataGroupBox)
        self.alphaChannelLabel.setObjectName(u"alphaChannelLabel")

        self.metadataLayout.setWidget(5, QFormLayout.LabelRole, self.alphaChannelLabel)

        self.alphaChannelValueLabel = QLabel(self.metadataGroupBox)
        self.alphaChannelValueLabel.setObjectName(u"alphaChannelValueLabel")

        self.metadataLayout.setWidget(5, QFormLayout.FieldRole, self.alphaChannelValueLabel)

        self.resolutionLabel = QLabel(self.metadataGroupBox)
        self.resolutionLabel.setObjectName(u"resolutionLabel")

        self.metadataLayout.setWidget(6, QFormLayout.LabelRole, self.resolutionLabel)

        self.resolutionValueLabel = QLabel(self.metadataGroupBox)
        self.resolutionValueLabel.setObjectName(u"resolutionValueLabel")

        self.metadataLayout.setWidget(6, QFormLayout.FieldRole, self.resolutionValueLabel)

        self.aspectRatioLabel = QLabel(self.metadataGroupBox)
        self.aspectRatioLabel.setObjectName(u"aspectRatioLabel")

        self.metadataLayout.setWidget(7, QFormLayout.LabelRole, self.aspectRatioLabel)

        self.aspectRatioValueLabel = QLabel(self.metadataGroupBox)
        self.aspectRatioValueLabel.setObjectName(u"aspectRatioValueLabel")

        self.metadataLayout.setWidget(7, QFormLayout.FieldRole, self.aspectRatioValueLabel)

        self.infoSplitter.addWidget(self.metadataGroupBox)
        self.annotationSplitter = QSplitter(self.infoSplitter)
        self.annotationSplitter.setObjectName(u"annotationSplitter")
        self.annotationSplitter.setOrientation(Qt.Orientation.Vertical)
        self.annotationGroupBox = QGroupBox(self.annotationSplitter)
        self.annotationGroupBox.setObjectName(u"annotationGroupBox")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.annotationGroupBox.sizePolicy().hasHeightForWidth())
        self.annotationGroupBox.setSizePolicy(sizePolicy3)
        self.gridLayout_2 = QGridLayout(self.annotationGroupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.tagsLabel = QLabel(self.annotationGroupBox)
        self.tagsLabel.setObjectName(u"tagsLabel")

        self.gridLayout_2.addWidget(self.tagsLabel, 0, 0, 1, 1)

        self.tagsTextEdit = QTextEdit(self.annotationGroupBox)
        self.tagsTextEdit.setObjectName(u"tagsTextEdit")
        self.tagsTextEdit.setReadOnly(True)

        self.gridLayout_2.addWidget(self.tagsTextEdit, 1, 0, 1, 1)

        self.captionLabel = QLabel(self.annotationGroupBox)
        self.captionLabel.setObjectName(u"captionLabel")

        self.gridLayout_2.addWidget(self.captionLabel, 2, 0, 1, 1)

        self.captionTextEdit = QTextEdit(self.annotationGroupBox)
        self.captionTextEdit.setObjectName(u"captionTextEdit")
        self.captionTextEdit.setReadOnly(True)

        self.gridLayout_2.addWidget(self.captionTextEdit, 3, 0, 1, 1)

        self.annotationSplitter.addWidget(self.annotationGroupBox)
        self.thumbnailSelector = ThumbnailSelectorWidget(self.annotationSplitter)
        self.thumbnailSelector.setObjectName(u"thumbnailSelector")
        self.annotationSplitter.addWidget(self.thumbnailSelector)
        self.infoSplitter.addWidget(self.annotationSplitter)

        self.verticalLayout.addWidget(self.infoSplitter)

        self.mainSplitter.addWidget(self.infoContainer)

        self.horizontalDatasetOverviewWidget.addWidget(self.mainSplitter)


        self.retranslateUi(DatasetOverviewWidget)

        QMetaObject.connectSlotsByName(DatasetOverviewWidget)
    # setupUi

    def retranslateUi(self, DatasetOverviewWidget):
        DatasetOverviewWidget.setWindowTitle(QCoreApplication.translate("DatasetOverviewWidget", u"Dataset Overview", None))
        self.metadataGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30e1\u30bf\u30c7\u30fc\u30bf", None))
        self.fileNameLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d:", None))
        self.imagePathLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30d1\u30b9:", None))
        self.extensionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u62e1\u5f35\u5b50:", None))
        self.formatLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a9\u30fc\u30de\u30c3\u30c8:", None))
        self.modeLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30e2\u30fc\u30c9:", None))
        self.alphaChannelLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30eb\u30d5\u30a1\u30c1\u30e3\u30f3\u30cd\u30eb:", None))
        self.resolutionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u89e3\u50cf\u5ea6:", None))
        self.aspectRatioLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None))
        self.annotationGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u65e2\u5b58\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.tagsLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30bf\u30b0:", None))
        self.captionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3:", None))
    # retranslateUi

