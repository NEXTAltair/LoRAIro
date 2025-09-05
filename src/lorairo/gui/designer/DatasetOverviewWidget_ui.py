################################################################################
## Form generated from reading UI file 'DatasetOverviewWidget.ui'
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
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets.filter import TagFilterWidget
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class Ui_DatasetOverviewWidget:
    def setupUi(self, DatasetOverviewWidget):
        if not DatasetOverviewWidget.objectName():
            DatasetOverviewWidget.setObjectName("DatasetOverviewWidget")
        DatasetOverviewWidget.resize(350, 777)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(DatasetOverviewWidget.sizePolicy().hasHeightForWidth())
        DatasetOverviewWidget.setSizePolicy(sizePolicy)
        self.verticalLayout_3 = QVBoxLayout(DatasetOverviewWidget)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.mainSplitter = QSplitter(DatasetOverviewWidget)
        self.mainSplitter.setObjectName("mainSplitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(2)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.mainSplitter.sizePolicy().hasHeightForWidth())
        self.mainSplitter.setSizePolicy(sizePolicy1)
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.mainSplitter.setHandleWidth(5)
        self.infoContainer = QWidget(self.mainSplitter)
        self.infoContainer.setObjectName("infoContainer")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.infoContainer.sizePolicy().hasHeightForWidth())
        self.infoContainer.setSizePolicy(sizePolicy2)
        self.infoContainer.setMinimumSize(QSize(0, 0))
        self.verticalLayout_2 = QVBoxLayout(self.infoContainer)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.dbSearchWidget = TagFilterWidget(self.infoContainer)
        self.dbSearchWidget.setObjectName("dbSearchWidget")
        sizePolicy.setHeightForWidth(self.dbSearchWidget.sizePolicy().hasHeightForWidth())
        self.dbSearchWidget.setSizePolicy(sizePolicy)

        self.verticalLayout_2.addWidget(self.dbSearchWidget)

        self.infoSplitter = QSplitter(self.infoContainer)
        self.infoSplitter.setObjectName("infoSplitter")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.infoSplitter.sizePolicy().hasHeightForWidth())
        self.infoSplitter.setSizePolicy(sizePolicy3)
        self.infoSplitter.setOrientation(Qt.Orientation.Vertical)
        self.metadataGroupBox = QGroupBox(self.infoSplitter)
        self.metadataGroupBox.setObjectName("metadataGroupBox")
        sizePolicy3.setHeightForWidth(self.metadataGroupBox.sizePolicy().hasHeightForWidth())
        self.metadataGroupBox.setSizePolicy(sizePolicy3)
        self.metadataGroupBox.setMinimumSize(QSize(0, 0))
        self.metadataLayout = QFormLayout(self.metadataGroupBox)
        self.metadataLayout.setObjectName("metadataLayout")
        self.fileNameLabel = QLabel(self.metadataGroupBox)
        self.fileNameLabel.setObjectName("fileNameLabel")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.fileNameLabel.sizePolicy().hasHeightForWidth())
        self.fileNameLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.fileNameLabel)

        self.fileNameValueLabel = QLabel(self.metadataGroupBox)
        self.fileNameValueLabel.setObjectName("fileNameValueLabel")
        sizePolicy4.setHeightForWidth(self.fileNameValueLabel.sizePolicy().hasHeightForWidth())
        self.fileNameValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.fileNameValueLabel)

        self.imagePathLabel = QLabel(self.metadataGroupBox)
        self.imagePathLabel.setObjectName("imagePathLabel")
        sizePolicy4.setHeightForWidth(self.imagePathLabel.sizePolicy().hasHeightForWidth())
        self.imagePathLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.imagePathLabel)

        self.imagePathValueLabel = QLabel(self.metadataGroupBox)
        self.imagePathValueLabel.setObjectName("imagePathValueLabel")
        sizePolicy4.setHeightForWidth(self.imagePathValueLabel.sizePolicy().hasHeightForWidth())
        self.imagePathValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.imagePathValueLabel)

        self.extensionLabel = QLabel(self.metadataGroupBox)
        self.extensionLabel.setObjectName("extensionLabel")
        sizePolicy4.setHeightForWidth(self.extensionLabel.sizePolicy().hasHeightForWidth())
        self.extensionLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.extensionLabel)

        self.extensionValueLabel = QLabel(self.metadataGroupBox)
        self.extensionValueLabel.setObjectName("extensionValueLabel")
        sizePolicy4.setHeightForWidth(self.extensionValueLabel.sizePolicy().hasHeightForWidth())
        self.extensionValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.extensionValueLabel)

        self.formatLabel = QLabel(self.metadataGroupBox)
        self.formatLabel.setObjectName("formatLabel")
        sizePolicy4.setHeightForWidth(self.formatLabel.sizePolicy().hasHeightForWidth())
        self.formatLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, self.formatLabel)

        self.formatValueLabel = QLabel(self.metadataGroupBox)
        self.formatValueLabel.setObjectName("formatValueLabel")
        sizePolicy4.setHeightForWidth(self.formatValueLabel.sizePolicy().hasHeightForWidth())
        self.formatValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.formatValueLabel)

        self.modeLabel = QLabel(self.metadataGroupBox)
        self.modeLabel.setObjectName("modeLabel")
        sizePolicy4.setHeightForWidth(self.modeLabel.sizePolicy().hasHeightForWidth())
        self.modeLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, self.modeLabel)

        self.modeValueLabel = QLabel(self.metadataGroupBox)
        self.modeValueLabel.setObjectName("modeValueLabel")
        sizePolicy4.setHeightForWidth(self.modeValueLabel.sizePolicy().hasHeightForWidth())
        self.modeValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.modeValueLabel)

        self.alphaChannelLabel = QLabel(self.metadataGroupBox)
        self.alphaChannelLabel.setObjectName("alphaChannelLabel")
        sizePolicy4.setHeightForWidth(self.alphaChannelLabel.sizePolicy().hasHeightForWidth())
        self.alphaChannelLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, self.alphaChannelLabel)

        self.alphaChannelValueLabel = QLabel(self.metadataGroupBox)
        self.alphaChannelValueLabel.setObjectName("alphaChannelValueLabel")
        sizePolicy4.setHeightForWidth(self.alphaChannelValueLabel.sizePolicy().hasHeightForWidth())
        self.alphaChannelValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.alphaChannelValueLabel)

        self.resolutionLabel = QLabel(self.metadataGroupBox)
        self.resolutionLabel.setObjectName("resolutionLabel")
        sizePolicy4.setHeightForWidth(self.resolutionLabel.sizePolicy().hasHeightForWidth())
        self.resolutionLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, self.resolutionLabel)

        self.resolutionValueLabel = QLabel(self.metadataGroupBox)
        self.resolutionValueLabel.setObjectName("resolutionValueLabel")
        sizePolicy4.setHeightForWidth(self.resolutionValueLabel.sizePolicy().hasHeightForWidth())
        self.resolutionValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.resolutionValueLabel)

        self.aspectRatioLabel = QLabel(self.metadataGroupBox)
        self.aspectRatioLabel.setObjectName("aspectRatioLabel")
        sizePolicy4.setHeightForWidth(self.aspectRatioLabel.sizePolicy().hasHeightForWidth())
        self.aspectRatioLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(7, QFormLayout.ItemRole.LabelRole, self.aspectRatioLabel)

        self.aspectRatioValueLabel = QLabel(self.metadataGroupBox)
        self.aspectRatioValueLabel.setObjectName("aspectRatioValueLabel")
        sizePolicy4.setHeightForWidth(self.aspectRatioValueLabel.sizePolicy().hasHeightForWidth())
        self.aspectRatioValueLabel.setSizePolicy(sizePolicy4)

        self.metadataLayout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.aspectRatioValueLabel)

        self.infoSplitter.addWidget(self.metadataGroupBox)
        self.annotationGroupBox = QGroupBox(self.infoSplitter)
        self.annotationGroupBox.setObjectName("annotationGroupBox")
        sizePolicy3.setHeightForWidth(self.annotationGroupBox.sizePolicy().hasHeightForWidth())
        self.annotationGroupBox.setSizePolicy(sizePolicy3)
        self.gridLayout_2 = QGridLayout(self.annotationGroupBox)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.tagsTextEdit = QTextEdit(self.annotationGroupBox)
        self.tagsTextEdit.setObjectName("tagsTextEdit")
        self.tagsTextEdit.setReadOnly(True)
        sizePolicy3.setHeightForWidth(self.tagsTextEdit.sizePolicy().hasHeightForWidth())
        self.tagsTextEdit.setSizePolicy(sizePolicy3)

        self.gridLayout_2.addWidget(self.tagsTextEdit, 1, 0, 1, 1)

        self.captionTextEdit = QTextEdit(self.annotationGroupBox)
        self.captionTextEdit.setObjectName("captionTextEdit")
        self.captionTextEdit.setReadOnly(True)
        sizePolicy3.setHeightForWidth(self.captionTextEdit.sizePolicy().hasHeightForWidth())
        self.captionTextEdit.setSizePolicy(sizePolicy3)

        self.gridLayout_2.addWidget(self.captionTextEdit, 3, 0, 1, 1)

        self.tagsLabel = QLabel(self.annotationGroupBox)
        self.tagsLabel.setObjectName("tagsLabel")
        sizePolicy4.setHeightForWidth(self.tagsLabel.sizePolicy().hasHeightForWidth())
        self.tagsLabel.setSizePolicy(sizePolicy4)

        self.gridLayout_2.addWidget(self.tagsLabel, 0, 0, 1, 1)

        self.captionLabel = QLabel(self.annotationGroupBox)
        self.captionLabel.setObjectName("captionLabel")
        sizePolicy4.setHeightForWidth(self.captionLabel.sizePolicy().hasHeightForWidth())
        self.captionLabel.setSizePolicy(sizePolicy4)

        self.gridLayout_2.addWidget(self.captionLabel, 2, 0, 1, 1)

        self.infoSplitter.addWidget(self.annotationGroupBox)

        self.verticalLayout_2.addWidget(self.infoSplitter)

        self.mainSplitter.addWidget(self.infoContainer)
        self.imageContainer = QWidget(self.mainSplitter)
        self.imageContainer.setObjectName("imageContainer")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(1)
        sizePolicy5.setVerticalStretch(2)
        sizePolicy5.setHeightForWidth(self.imageContainer.sizePolicy().hasHeightForWidth())
        self.imageContainer.setSizePolicy(sizePolicy5)
        self.imageContainer.setMinimumSize(QSize(0, 0))
        self.verticalLayout = QVBoxLayout(self.imageContainer)
        self.verticalLayout.setObjectName("verticalLayout")
        self.ImagePreview = ImagePreviewWidget(self.imageContainer)
        self.ImagePreview.setObjectName("ImagePreview")
        sizePolicy3.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy3)

        self.verticalLayout.addWidget(self.ImagePreview)

        self.thumbnailSelector = ThumbnailSelectorWidget(self.imageContainer)
        self.thumbnailSelector.setObjectName("thumbnailSelector")
        sizePolicy3.setHeightForWidth(self.thumbnailSelector.sizePolicy().hasHeightForWidth())
        self.thumbnailSelector.setSizePolicy(sizePolicy3)

        self.verticalLayout.addWidget(self.thumbnailSelector)

        self.mainSplitter.addWidget(self.imageContainer)

        self.verticalLayout_3.addWidget(self.mainSplitter)

        self.retranslateUi(DatasetOverviewWidget)

        QMetaObject.connectSlotsByName(DatasetOverviewWidget)

    # setupUi

    def retranslateUi(self, DatasetOverviewWidget):
        DatasetOverviewWidget.setWindowTitle(
            QCoreApplication.translate("DatasetOverviewWidget", "Dataset Overview", None)
        )
        self.metadataGroupBox.setTitle("")
        self.fileNameLabel.setText(
            QCoreApplication.translate("DatasetOverviewWidget", "\u30d5\u30a1\u30a4\u30eb\u540d:", None)
        )
        self.imagePathLabel.setText(
            QCoreApplication.translate("DatasetOverviewWidget", "\u753b\u50cf\u30d1\u30b9:", None)
        )
        self.extensionLabel.setText(
            QCoreApplication.translate("DatasetOverviewWidget", "\u62e1\u5f35\u5b50:", None)
        )
        self.formatLabel.setText(
            QCoreApplication.translate(
                "DatasetOverviewWidget", "\u30d5\u30a9\u30fc\u30de\u30c3\u30c8:", None
            )
        )
        self.modeLabel.setText(
            QCoreApplication.translate("DatasetOverviewWidget", "\u30e2\u30fc\u30c9:", None)
        )
        self.alphaChannelLabel.setText(
            QCoreApplication.translate(
                "DatasetOverviewWidget", "\u30a2\u30eb\u30d5\u30a1\u30c1\u30e3\u30f3\u30cd\u30eb:", None
            )
        )
        self.resolutionLabel.setText(
            QCoreApplication.translate("DatasetOverviewWidget", "\u89e3\u50cf\u5ea6:", None)
        )
        self.aspectRatioLabel.setText(
            QCoreApplication.translate(
                "DatasetOverviewWidget", "\u30a2\u30b9\u30da\u30af\u30c8\u6bd4:", None
            )
        )
        self.annotationGroupBox.setTitle("")
        self.tagsLabel.setText(QCoreApplication.translate("DatasetOverviewWidget", "\u30bf\u30b0:", None))
        self.captionLabel.setText(
            QCoreApplication.translate(
                "DatasetOverviewWidget", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3:", None
            )
        )

    # retranslateUi
