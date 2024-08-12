# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dataset_overview.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTextEdit, QVBoxLayout,
    QWidget)

class Ui_DatasetOverviewWidget(object):
    def setupUi(self, DatasetOverviewWidget):
        if not DatasetOverviewWidget.objectName():
            DatasetOverviewWidget.setObjectName(u"DatasetOverviewWidget")
        DatasetOverviewWidget.resize(1200, 800)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DatasetOverviewWidget.sizePolicy().hasHeightForWidth())
        DatasetOverviewWidget.setSizePolicy(sizePolicy)
        self.mainLayout = QVBoxLayout(DatasetOverviewWidget)
        self.mainLayout.setObjectName(u"mainLayout")
        self.directorySelectionWidget = QWidget(DatasetOverviewWidget)
        self.directorySelectionWidget.setObjectName(u"directorySelectionWidget")
        self.directorySelectionWidget.setEnabled(True)
        self.directorySelectionLayout = QHBoxLayout(self.directorySelectionWidget)
        self.directorySelectionLayout.setObjectName(u"directorySelectionLayout")
        self.datasetDirLabel = QLabel(self.directorySelectionWidget)
        self.datasetDirLabel.setObjectName(u"datasetDirLabel")

        self.directorySelectionLayout.addWidget(self.datasetDirLabel)

        self.datasetDirLineEdit = QLineEdit(self.directorySelectionWidget)
        self.datasetDirLineEdit.setObjectName(u"datasetDirLineEdit")

        self.directorySelectionLayout.addWidget(self.datasetDirLineEdit)

        self.selectDatasetButton = QPushButton(self.directorySelectionWidget)
        self.selectDatasetButton.setObjectName(u"selectDatasetButton")

        self.directorySelectionLayout.addWidget(self.selectDatasetButton)


        self.mainLayout.addWidget(self.directorySelectionWidget)

        self.mainSplitter = QSplitter(DatasetOverviewWidget)
        self.mainSplitter.setObjectName(u"mainSplitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.mainSplitter.sizePolicy().hasHeightForWidth())
        self.mainSplitter.setSizePolicy(sizePolicy1)
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.previewScrollArea = QScrollArea(self.mainSplitter)
        self.previewScrollArea.setObjectName(u"previewScrollArea")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.previewScrollArea.sizePolicy().hasHeightForWidth())
        self.previewScrollArea.setSizePolicy(sizePolicy2)
        self.previewScrollArea.setWidgetResizable(True)
        self.previewContainer = QWidget()
        self.previewContainer.setObjectName(u"previewContainer")
        self.previewContainer.setGeometry(QRect(0, 0, 917, 1051))
        self.previewLayout = QVBoxLayout(self.previewContainer)
        self.previewLayout.setObjectName(u"previewLayout")
        self.previewLabel = QLabel(self.previewContainer)
        self.previewLabel.setObjectName(u"previewLabel")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(1)
        sizePolicy3.setVerticalStretch(1)
        sizePolicy3.setHeightForWidth(self.previewLabel.sizePolicy().hasHeightForWidth())
        self.previewLabel.setSizePolicy(sizePolicy3)
        self.previewLabel.setMinimumSize(QSize(256, 256))
        self.previewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.previewLayout.addWidget(self.previewLabel)

        self.previewScrollArea.setWidget(self.previewContainer)
        self.mainSplitter.addWidget(self.previewScrollArea)
        self.infoContainer = QWidget(self.mainSplitter)
        self.infoContainer.setObjectName(u"infoContainer")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.infoContainer.sizePolicy().hasHeightForWidth())
        self.infoContainer.setSizePolicy(sizePolicy4)
        self.infoLayout = QVBoxLayout(self.infoContainer)
        self.infoLayout.setObjectName(u"infoLayout")
        self.metadataGroupBox = QGroupBox(self.infoContainer)
        self.metadataGroupBox.setObjectName(u"metadataGroupBox")
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

        self.extensionLabel = QLabel(self.metadataGroupBox)
        self.extensionLabel.setObjectName(u"extensionLabel")

        self.metadataLayout.setWidget(2, QFormLayout.LabelRole, self.extensionLabel)

        self.extensionValueLabel = QLabel(self.metadataGroupBox)
        self.extensionValueLabel.setObjectName(u"extensionValueLabel")

        self.metadataLayout.setWidget(2, QFormLayout.FieldRole, self.extensionValueLabel)


        self.infoLayout.addWidget(self.metadataGroupBox)

        self.annotationGroupBox = QGroupBox(self.infoContainer)
        self.annotationGroupBox.setObjectName(u"annotationGroupBox")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(1)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.annotationGroupBox.sizePolicy().hasHeightForWidth())
        self.annotationGroupBox.setSizePolicy(sizePolicy5)
        self.annotationLayout = QVBoxLayout(self.annotationGroupBox)
        self.annotationLayout.setObjectName(u"annotationLayout")
        self.tagsLabel = QLabel(self.annotationGroupBox)
        self.tagsLabel.setObjectName(u"tagsLabel")

        self.annotationLayout.addWidget(self.tagsLabel)

        self.tagsTextEdit = QTextEdit(self.annotationGroupBox)
        self.tagsTextEdit.setObjectName(u"tagsTextEdit")
        self.tagsTextEdit.setReadOnly(True)

        self.annotationLayout.addWidget(self.tagsTextEdit)

        self.captionLabel = QLabel(self.annotationGroupBox)
        self.captionLabel.setObjectName(u"captionLabel")

        self.annotationLayout.addWidget(self.captionLabel)

        self.captionTextEdit = QTextEdit(self.annotationGroupBox)
        self.captionTextEdit.setObjectName(u"captionTextEdit")
        self.captionTextEdit.setReadOnly(True)

        self.annotationLayout.addWidget(self.captionTextEdit)


        self.infoLayout.addWidget(self.annotationGroupBox)

        self.thumbnailButtonTemplate = QPushButton(self.infoContainer)
        self.thumbnailButtonTemplate.setObjectName(u"thumbnailButtonTemplate")
        self.thumbnailButtonTemplate.setMinimumSize(QSize(150, 150))
#if QT_CONFIG(tooltip)
        self.thumbnailButtonTemplate.setToolTip(u"")
#endif // QT_CONFIG(tooltip)
        self.thumbnailButtonTemplate.setText(u"")
        self.thumbnailButtonTemplate.setIconSize(QSize(150, 150))
#if QT_CONFIG(shortcut)
        self.thumbnailButtonTemplate.setShortcut(u"")
#endif // QT_CONFIG(shortcut)
        self.thumbnailButtonTemplate.setCheckable(False)
        self.thumbnailButtonTemplate.setFlat(True)

        self.infoLayout.addWidget(self.thumbnailButtonTemplate)

        self.thumbnailScrollArea = QScrollArea(self.infoContainer)
        self.thumbnailScrollArea.setObjectName(u"thumbnailScrollArea")
        self.thumbnailScrollArea.setWidgetResizable(True)
        self.thumbnailContainer = QWidget()
        self.thumbnailContainer.setObjectName(u"thumbnailContainer")
        self.thumbnailContainer.setGeometry(QRect(0, 0, 274, 177))
        self.thumbnailContainer.setMinimumSize(QSize(150, 150))
        self.thumbnailLayout = QHBoxLayout(self.thumbnailContainer)
        self.thumbnailLayout.setObjectName(u"thumbnailLayout")
        self.thumbnailScrollArea.setWidget(self.thumbnailContainer)

        self.infoLayout.addWidget(self.thumbnailScrollArea)

        self.mainSplitter.addWidget(self.infoContainer)

        self.mainLayout.addWidget(self.mainSplitter)


        self.retranslateUi(DatasetOverviewWidget)

        QMetaObject.connectSlotsByName(DatasetOverviewWidget)
    # setupUi

    def retranslateUi(self, DatasetOverviewWidget):
        DatasetOverviewWidget.setWindowTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u6982\u8981", None))
        self.datasetDirLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30c7\u30a3\u30ec\u30af\u30c8\u30ea:", None))
        self.selectDatasetButton.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u9078\u629e", None))
        self.previewLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30d7\u30ec\u30d3\u30e5\u30fc", None))
        self.metadataGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30e1\u30bf\u30c7\u30fc\u30bf", None))
        self.fileNameLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d:", None))
        self.imagePathLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30d1\u30b9:", None))
        self.formatLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a9\u30fc\u30de\u30c3\u30c8:", None))
        self.modeLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30e2\u30fc\u30c9:", None))
        self.alphaChannelLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30eb\u30d5\u30a1\u30c1\u30e3\u30f3\u30cd\u30eb:", None))
        self.resolutionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u89e3\u50cf\u5ea6:", None))
        self.aspectRatioLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None))
        self.extensionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u62e1\u5f35\u5b50:", None))
        self.annotationGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u65e2\u5b58\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.tagsLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30bf\u30b0:", None))
        self.captionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3:", None))
    # retranslateUi

