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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGraphicsView, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QTextEdit,
    QVBoxLayout, QWidget)

class Ui_DatasetOverviewWidget(object):
    def setupUi(self, DatasetOverviewWidget):
        if not DatasetOverviewWidget.objectName():
            DatasetOverviewWidget.setObjectName(u"DatasetOverviewWidget")
        DatasetOverviewWidget.resize(1331, 1192)
        self.horizontalDatasetOverviewWidget = QHBoxLayout(DatasetOverviewWidget)
        self.horizontalDatasetOverviewWidget.setObjectName(u"horizontalDatasetOverviewWidget")
        self.mainSplitter = QSplitter(DatasetOverviewWidget)
        self.mainSplitter.setObjectName(u"mainSplitter")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.mainSplitter.sizePolicy().hasHeightForWidth())
        self.mainSplitter.setSizePolicy(sizePolicy)
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.previewScrollArea = QScrollArea(self.mainSplitter)
        self.previewScrollArea.setObjectName(u"previewScrollArea")
        sizePolicy.setHeightForWidth(self.previewScrollArea.sizePolicy().hasHeightForWidth())
        self.previewScrollArea.setSizePolicy(sizePolicy)
        self.previewScrollArea.setWidgetResizable(True)
        self.previewContainer = QWidget()
        self.previewContainer.setObjectName(u"previewContainer")
        self.previewContainer.setGeometry(QRect(0, 0, 996, 1168))
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.previewContainer.sizePolicy().hasHeightForWidth())
        self.previewContainer.setSizePolicy(sizePolicy1)
        self.horizontalpreviewContainer = QHBoxLayout(self.previewContainer)
        self.horizontalpreviewContainer.setObjectName(u"horizontalpreviewContainer")
        self.previewgraphicsView = QGraphicsView(self.previewContainer)
        self.previewgraphicsView.setObjectName(u"previewgraphicsView")
        sizePolicy1.setHeightForWidth(self.previewgraphicsView.sizePolicy().hasHeightForWidth())
        self.previewgraphicsView.setSizePolicy(sizePolicy1)
        self.previewgraphicsView.setMinimumSize(QSize(128, 128))

        self.horizontalpreviewContainer.addWidget(self.previewgraphicsView)

        self.previewScrollArea.setWidget(self.previewContainer)
        self.mainSplitter.addWidget(self.previewScrollArea)
        self.infoContainer = QWidget(self.mainSplitter)
        self.infoContainer.setObjectName(u"infoContainer")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.infoContainer.sizePolicy().hasHeightForWidth())
        self.infoContainer.setSizePolicy(sizePolicy2)
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

        self.fileNameLabel = QLabel(self.metadataGroupBox)
        self.fileNameLabel.setObjectName(u"fileNameLabel")

        self.metadataLayout.setWidget(0, QFormLayout.LabelRole, self.fileNameLabel)

        self.infoSplitter.addWidget(self.metadataGroupBox)
        self.annotationGroupBox = QGroupBox(self.infoSplitter)
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

        self.infoSplitter.addWidget(self.annotationGroupBox)
        self.thumbnailScrollArea = QScrollArea(self.infoSplitter)
        self.thumbnailScrollArea.setObjectName(u"thumbnailScrollArea")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.thumbnailScrollArea.sizePolicy().hasHeightForWidth())
        self.thumbnailScrollArea.setSizePolicy(sizePolicy4)
        self.thumbnailScrollArea.setMinimumSize(QSize(0, 128))
        self.thumbnailScrollArea.setWidgetResizable(True)
        self.thumbnailContainer = QWidget()
        self.thumbnailContainer.setObjectName(u"thumbnailContainer")
        self.thumbnailContainer.setGeometry(QRect(0, 0, 282, 380))
        self.thumbnailContainer.setMinimumSize(QSize(64, 64))
#if QT_CONFIG(whatsthis)
        self.thumbnailContainer.setWhatsThis(u"")
#endif // QT_CONFIG(whatsthis)
#if QT_CONFIG(accessibility)
        self.thumbnailContainer.setAccessibleName(u"")
#endif // QT_CONFIG(accessibility)
#if QT_CONFIG(accessibility)
        self.thumbnailContainer.setAccessibleDescription(u"")
#endif // QT_CONFIG(accessibility)
        self.thumbnailContainer.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.thumbnailContainer.setAutoFillBackground(False)
        self.gridLayout = QGridLayout(self.thumbnailContainer)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(5, -1, -1, -1)
        self.thumbnailButtonTemplate = QPushButton(self.thumbnailContainer)
        self.thumbnailButtonTemplate.setObjectName(u"thumbnailButtonTemplate")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(1)
        sizePolicy5.setHeightForWidth(self.thumbnailButtonTemplate.sizePolicy().hasHeightForWidth())
        self.thumbnailButtonTemplate.setSizePolicy(sizePolicy5)
        self.thumbnailButtonTemplate.setMinimumSize(QSize(0, 0))
#if QT_CONFIG(tooltip)
        self.thumbnailButtonTemplate.setToolTip(u"")
#endif // QT_CONFIG(tooltip)
        self.thumbnailButtonTemplate.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.thumbnailButtonTemplate.setText(u"")
        self.thumbnailButtonTemplate.setIconSize(QSize(150, 150))
#if QT_CONFIG(shortcut)
        self.thumbnailButtonTemplate.setShortcut(u"")
#endif // QT_CONFIG(shortcut)
        self.thumbnailButtonTemplate.setCheckable(False)
        self.thumbnailButtonTemplate.setAutoRepeatDelay(0)
        self.thumbnailButtonTemplate.setAutoRepeatInterval(0)
        self.thumbnailButtonTemplate.setAutoDefault(False)
        self.thumbnailButtonTemplate.setFlat(True)

        self.gridLayout.addWidget(self.thumbnailButtonTemplate, 0, 0, 1, 1)

        self.thumbnailScrollArea.setWidget(self.thumbnailContainer)
        self.infoSplitter.addWidget(self.thumbnailScrollArea)

        self.verticalLayout.addWidget(self.infoSplitter)

        self.mainSplitter.addWidget(self.infoContainer)

        self.horizontalDatasetOverviewWidget.addWidget(self.mainSplitter)


        self.retranslateUi(DatasetOverviewWidget)
        self.mainSplitter.splitterMoved.connect(self.previewgraphicsView.invalidateScene)

        QMetaObject.connectSlotsByName(DatasetOverviewWidget)
    # setupUi

    def retranslateUi(self, DatasetOverviewWidget):
        DatasetOverviewWidget.setWindowTitle(QCoreApplication.translate("DatasetOverviewWidget", u"Form", None))
        self.metadataGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30e1\u30bf\u30c7\u30fc\u30bf", None))
        self.imagePathLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u753b\u50cf\u30d1\u30b9:", None))
        self.extensionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u62e1\u5f35\u5b50:", None))
        self.formatLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a9\u30fc\u30de\u30c3\u30c8:", None))
        self.modeLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30e2\u30fc\u30c9:", None))
        self.alphaChannelLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30eb\u30d5\u30a1\u30c1\u30e3\u30f3\u30cd\u30eb:", None))
        self.resolutionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u89e3\u50cf\u5ea6:", None))
        self.aspectRatioLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None))
        self.fileNameLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d:", None))
        self.annotationGroupBox.setTitle(QCoreApplication.translate("DatasetOverviewWidget", u"\u65e2\u5b58\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.tagsLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30bf\u30b0:", None))
        self.captionLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3:", None))
    # retranslateUi

