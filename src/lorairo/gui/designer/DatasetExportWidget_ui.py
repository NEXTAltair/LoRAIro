
################################################################################
## Form generated from reading UI file 'DatasetExportWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.0
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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..widgets.directory_picker import DirectoryPickerWidget
from ..widgets.filter import TagFilterWidget
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class Ui_DatasetExportWidget:
    def setupUi(self, DatasetExportWidget):
        if not DatasetExportWidget.objectName():
            DatasetExportWidget.setObjectName("DatasetExportWidget")
        DatasetExportWidget.resize(1200, 800)
        self.mainLayout = QHBoxLayout(DatasetExportWidget)
        self.mainLayout.setObjectName("mainLayout")
        self.mainSplitter = QSplitter(DatasetExportWidget)
        self.mainSplitter.setObjectName("mainSplitter")
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.leftPanel = QWidget(self.mainSplitter)
        self.leftPanel.setObjectName("leftPanel")
        self.leftPanelLayout = QVBoxLayout(self.leftPanel)
        self.leftPanelLayout.setObjectName("leftPanelLayout")
        self.leftPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.dbSearchWidget = TagFilterWidget(self.leftPanel)
        self.dbSearchWidget.setObjectName("dbSearchWidget")
        self.filterLayout = QVBoxLayout(self.dbSearchWidget)
        self.filterLayout.setObjectName("filterLayout")

        self.leftPanelLayout.addWidget(self.dbSearchWidget)

        self.thumbnailSelector = ThumbnailSelectorWidget(self.leftPanel)
        self.thumbnailSelector.setObjectName("thumbnailSelector")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.thumbnailSelector.sizePolicy().hasHeightForWidth())
        self.thumbnailSelector.setSizePolicy(sizePolicy)

        self.leftPanelLayout.addWidget(self.thumbnailSelector)

        self.imageCountLabel = QLabel(self.leftPanel)
        self.imageCountLabel.setObjectName("imageCountLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.imageCountLabel.sizePolicy().hasHeightForWidth())
        self.imageCountLabel.setSizePolicy(sizePolicy1)

        self.leftPanelLayout.addWidget(self.imageCountLabel)

        self.mainSplitter.addWidget(self.leftPanel)
        self.rightPanel = QWidget(self.mainSplitter)
        self.rightPanel.setObjectName("rightPanel")
        self.rightPanelLayout = QVBoxLayout(self.rightPanel)
        self.rightPanelLayout.setObjectName("rightPanelLayout")
        self.rightPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.imagePreview = ImagePreviewWidget(self.rightPanel)
        self.imagePreview.setObjectName("imagePreview")
        sizePolicy.setHeightForWidth(self.imagePreview.sizePolicy().hasHeightForWidth())
        self.imagePreview.setSizePolicy(sizePolicy)

        self.rightPanelLayout.addWidget(self.imagePreview)

        self.exportGroupBox = QGroupBox(self.rightPanel)
        self.exportGroupBox.setObjectName("exportGroupBox")
        self.exportLayout = QVBoxLayout(self.exportGroupBox)
        self.exportLayout.setObjectName("exportLayout")
        self.exportDirectoryPicker = DirectoryPickerWidget(self.exportGroupBox)
        self.exportDirectoryPicker.setObjectName("exportDirectoryPicker")

        self.exportLayout.addWidget(self.exportDirectoryPicker)

        self.exportFormatLabel = QLabel(self.exportGroupBox)
        self.exportFormatLabel.setObjectName("exportFormatLabel")
        sizePolicy1.setHeightForWidth(self.exportFormatLabel.sizePolicy().hasHeightForWidth())
        self.exportFormatLabel.setSizePolicy(sizePolicy1)

        self.exportLayout.addWidget(self.exportFormatLabel)

        self.exportFormatLayout = QHBoxLayout()
        self.exportFormatLayout.setObjectName("exportFormatLayout")
        self.checkBoxTxtCap = QCheckBox(self.exportGroupBox)
        self.checkBoxTxtCap.setObjectName("checkBoxTxtCap")
        self.checkBoxTxtCap.setChecked(True)

        self.exportFormatLayout.addWidget(self.checkBoxTxtCap)

        self.checkBoxJson = QCheckBox(self.exportGroupBox)
        self.checkBoxJson.setObjectName("checkBoxJson")

        self.exportFormatLayout.addWidget(self.checkBoxJson)


        self.exportLayout.addLayout(self.exportFormatLayout)

        self.latestcheckBox = QCheckBox(self.exportGroupBox)
        self.latestcheckBox.setObjectName("latestcheckBox")

        self.exportLayout.addWidget(self.latestcheckBox)

        self.MergeCaptionWithTagscheckBox = QCheckBox(self.exportGroupBox)
        self.MergeCaptionWithTagscheckBox.setObjectName("MergeCaptionWithTagscheckBox")

        self.exportLayout.addWidget(self.MergeCaptionWithTagscheckBox)

        self.exportButton = QPushButton(self.exportGroupBox)
        self.exportButton.setObjectName("exportButton")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.exportButton.sizePolicy().hasHeightForWidth())
        self.exportButton.setSizePolicy(sizePolicy2)

        self.exportLayout.addWidget(self.exportButton)

        self.exportProgressBar = QProgressBar(self.exportGroupBox)
        self.exportProgressBar.setObjectName("exportProgressBar")
        self.exportProgressBar.setValue(0)
        sizePolicy2.setHeightForWidth(self.exportProgressBar.sizePolicy().hasHeightForWidth())
        self.exportProgressBar.setSizePolicy(sizePolicy2)

        self.exportLayout.addWidget(self.exportProgressBar)

        self.statusLabel = QLabel(self.exportGroupBox)
        self.statusLabel.setObjectName("statusLabel")
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
        DatasetExportWidget.setWindowTitle(QCoreApplication.translate("DatasetExportWidget", "Dataset Export", None))
        self.imageCountLabel.setText("")
        self.exportGroupBox.setTitle(QCoreApplication.translate("DatasetExportWidget", "Export Settings", None))
        self.exportFormatLabel.setText(QCoreApplication.translate("DatasetExportWidget", "Export Format:", None))
        self.checkBoxTxtCap.setText(QCoreApplication.translate("DatasetExportWidget", "txt/caption", None))
        self.checkBoxJson.setText(QCoreApplication.translate("DatasetExportWidget", "metadata.json", None))
        self.latestcheckBox.setText(QCoreApplication.translate("DatasetExportWidget", "\u6700\u5f8c\u306b\u66f4\u65b0\u3055\u308c\u305f\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u3060\u3051\u3092\u51fa\u529b\u3059\u308b", None))
        self.MergeCaptionWithTagscheckBox.setText(QCoreApplication.translate("DatasetExportWidget", "caption\u3068\u3057\u3066\u4fdd\u5b58\u3055\u308c\u305f\u6587\u5b57\u5217\u3082 \".tag\" \u306b\u4fdd\u5b58\u3059\u308b", None))
        self.exportButton.setText(QCoreApplication.translate("DatasetExportWidget", "Export Dataset", None))
        self.statusLabel.setText(QCoreApplication.translate("DatasetExportWidget", "Status: Ready", None))
    # retranslateUi

