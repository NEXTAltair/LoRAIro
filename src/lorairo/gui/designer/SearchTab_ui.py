# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SearchTab.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
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
    QTime,
    QUrl,
    Qt,
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class Ui_SearchTab(object):
    def setupUi(self, SearchTab: QWidget) -> None:
        if not SearchTab.objectName():
            SearchTab.setObjectName("SearchTab")
        SearchTab.resize(1200, 800)
        self.verticalLayout_workspace = QVBoxLayout(SearchTab)
        self.verticalLayout_workspace.setSpacing(0)
        self.verticalLayout_workspace.setObjectName("verticalLayout_workspace")
        self.verticalLayout_workspace.setContentsMargins(0, 0, 0, 0)
        self.frameDatasetSelector = QFrame(SearchTab)
        self.frameDatasetSelector.setObjectName("frameDatasetSelector")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frameDatasetSelector.sizePolicy().hasHeightForWidth())
        self.frameDatasetSelector.setSizePolicy(sizePolicy)
        self.frameDatasetSelector.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameDatasetSelector.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_dataset = QHBoxLayout(self.frameDatasetSelector)
        self.horizontalLayout_dataset.setObjectName("horizontalLayout_dataset")
        self.horizontalLayout_dataset.setContentsMargins(10, 10, 10, 10)
        self.labelDataset = QLabel(self.frameDatasetSelector)
        self.labelDataset.setObjectName("labelDataset")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelDataset.sizePolicy().hasHeightForWidth())
        self.labelDataset.setSizePolicy(sizePolicy1)

        self.horizontalLayout_dataset.addWidget(self.labelDataset)

        self.lineEditDatasetPath = QLineEdit(self.frameDatasetSelector)
        self.lineEditDatasetPath.setObjectName("lineEditDatasetPath")
        self.lineEditDatasetPath.setReadOnly(True)

        self.horizontalLayout_dataset.addWidget(self.lineEditDatasetPath)

        self.pushButtonSelectDataset = QPushButton(self.frameDatasetSelector)
        self.pushButtonSelectDataset.setObjectName("pushButtonSelectDataset")
        sizePolicy1.setHeightForWidth(self.pushButtonSelectDataset.sizePolicy().hasHeightForWidth())
        self.pushButtonSelectDataset.setSizePolicy(sizePolicy1)

        self.horizontalLayout_dataset.addWidget(self.pushButtonSelectDataset)

        self.horizontalSpacer_dataset = QSpacerItem(
            20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_dataset.addItem(self.horizontalSpacer_dataset)

        self.pushButtonSettings = QPushButton(self.frameDatasetSelector)
        self.pushButtonSettings.setObjectName("pushButtonSettings")
        sizePolicy1.setHeightForWidth(self.pushButtonSettings.sizePolicy().hasHeightForWidth())
        self.pushButtonSettings.setSizePolicy(sizePolicy1)

        self.horizontalLayout_dataset.addWidget(self.pushButtonSettings)

        self.verticalLayout_workspace.addWidget(self.frameDatasetSelector)

        self.frameDbStatus = QFrame(SearchTab)
        self.frameDbStatus.setObjectName("frameDbStatus")
        sizePolicy.setHeightForWidth(self.frameDbStatus.sizePolicy().hasHeightForWidth())
        self.frameDbStatus.setSizePolicy(sizePolicy)
        self.frameDbStatus.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameDbStatus.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_dbStatus = QHBoxLayout(self.frameDbStatus)
        self.horizontalLayout_dbStatus.setObjectName("horizontalLayout_dbStatus")
        self.horizontalLayout_dbStatus.setContentsMargins(10, 5, 10, 5)
        self.labelDbInfo = QLabel(self.frameDbStatus)
        self.labelDbInfo.setObjectName("labelDbInfo")

        self.horizontalLayout_dbStatus.addWidget(self.labelDbInfo)

        self.horizontalSpacer_dbStatus = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_dbStatus.addItem(self.horizontalSpacer_dbStatus)

        self.verticalLayout_workspace.addWidget(self.frameDbStatus)

        self.splitterMainWorkArea = QSplitter(SearchTab)
        self.splitterMainWorkArea.setObjectName("splitterMainWorkArea")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.splitterMainWorkArea.sizePolicy().hasHeightForWidth())
        self.splitterMainWorkArea.setSizePolicy(sizePolicy2)
        self.splitterMainWorkArea.setOrientation(Qt.Orientation.Horizontal)
        self.splitterMainWorkArea.setChildrenCollapsible(False)
        self.frameFilterSearchPanel = QFrame(self.splitterMainWorkArea)
        self.frameFilterSearchPanel.setObjectName("frameFilterSearchPanel")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(1)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.frameFilterSearchPanel.sizePolicy().hasHeightForWidth())
        self.frameFilterSearchPanel.setSizePolicy(sizePolicy3)
        self.frameFilterSearchPanel.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameFilterSearchPanel.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout = QVBoxLayout(self.frameFilterSearchPanel)
        self.verticalLayout.setObjectName("verticalLayout")
        self.labelFilterSearch = QLabel(self.frameFilterSearchPanel)
        self.labelFilterSearch.setObjectName("labelFilterSearch")

        self.verticalLayout.addWidget(self.labelFilterSearch)

        self.filterSearchPanel = FilterSearchPanel(self.frameFilterSearchPanel)
        self.filterSearchPanel.setObjectName("filterSearchPanel")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.filterSearchPanel.sizePolicy().hasHeightForWidth())
        self.filterSearchPanel.setSizePolicy(sizePolicy4)

        self.verticalLayout.addWidget(self.filterSearchPanel)

        self.splitterMainWorkArea.addWidget(self.frameFilterSearchPanel)
        self.frameThumbnailGrid = QFrame(self.splitterMainWorkArea)
        self.frameThumbnailGrid.setObjectName("frameThumbnailGrid")
        sizePolicy2.setHeightForWidth(self.frameThumbnailGrid.sizePolicy().hasHeightForWidth())
        self.frameThumbnailGrid.setSizePolicy(sizePolicy2)
        self.frameThumbnailGrid.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameThumbnailGrid.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_thumbnailGrid = QVBoxLayout(self.frameThumbnailGrid)
        self.verticalLayout_thumbnailGrid.setSpacing(5)
        self.verticalLayout_thumbnailGrid.setObjectName("verticalLayout_thumbnailGrid")
        self.verticalLayout_thumbnailGrid.setContentsMargins(5, 5, 5, 5)
        self.thumbnailSelectorWidget = ThumbnailSelectorWidget(self.frameThumbnailGrid)
        self.thumbnailSelectorWidget.setObjectName("thumbnailSelectorWidget")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(2)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.thumbnailSelectorWidget.sizePolicy().hasHeightForWidth())
        self.thumbnailSelectorWidget.setSizePolicy(sizePolicy5)

        self.verticalLayout_thumbnailGrid.addWidget(self.thumbnailSelectorWidget)

        self.horizontalLayout_exportBottomBar = QHBoxLayout()
        self.horizontalLayout_exportBottomBar.setObjectName("horizontalLayout_exportBottomBar")
        self.labelExportTarget = QLabel(self.frameThumbnailGrid)
        self.labelExportTarget.setObjectName("labelExportTarget")

        self.horizontalLayout_exportBottomBar.addWidget(self.labelExportTarget)

        self.horizontalSpacer_exportBottomBar = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_exportBottomBar.addItem(self.horizontalSpacer_exportBottomBar)

        self.btnExportData = QPushButton(self.frameThumbnailGrid)
        self.btnExportData.setObjectName("btnExportData")

        self.horizontalLayout_exportBottomBar.addWidget(self.btnExportData)

        self.verticalLayout_thumbnailGrid.addLayout(self.horizontalLayout_exportBottomBar)

        self.splitterMainWorkArea.addWidget(self.frameThumbnailGrid)
        self.framePreviewDetailPanel = QFrame(self.splitterMainWorkArea)
        self.framePreviewDetailPanel.setObjectName("framePreviewDetailPanel")
        sizePolicy5.setHeightForWidth(self.framePreviewDetailPanel.sizePolicy().hasHeightForWidth())
        self.framePreviewDetailPanel.setSizePolicy(sizePolicy5)
        self.framePreviewDetailPanel.setFrameShape(QFrame.Shape.StyledPanel)
        self.framePreviewDetailPanel.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_previewDetail = QVBoxLayout(self.framePreviewDetailPanel)
        self.verticalLayout_previewDetail.setSpacing(5)
        self.verticalLayout_previewDetail.setObjectName("verticalLayout_previewDetail")
        self.verticalLayout_previewDetail.setContentsMargins(5, 5, 5, 5)
        self.labelPreviewDetail = QLabel(self.framePreviewDetailPanel)
        self.labelPreviewDetail.setObjectName("labelPreviewDetail")

        self.verticalLayout_previewDetail.addWidget(self.labelPreviewDetail)

        self.framePreviewDetailContent = QFrame(self.framePreviewDetailPanel)
        self.framePreviewDetailContent.setObjectName("framePreviewDetailContent")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.framePreviewDetailContent.sizePolicy().hasHeightForWidth())
        self.framePreviewDetailContent.setSizePolicy(sizePolicy6)
        self.framePreviewDetailContent.setMaximumSize(QSize(16777215, 16777215))
        self.framePreviewDetailContent.setStyleSheet("")
        self.framePreviewDetailContent.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalLayout_previewDetailContent = QVBoxLayout(self.framePreviewDetailContent)
        self.verticalLayout_previewDetailContent.setSpacing(8)
        self.verticalLayout_previewDetailContent.setObjectName("verticalLayout_previewDetailContent")
        self.verticalLayout_previewDetailContent.setContentsMargins(5, 5, 5, 5)
        self.splitterPreviewDetails = QSplitter(self.framePreviewDetailContent)
        self.splitterPreviewDetails.setObjectName("splitterPreviewDetails")
        self.splitterPreviewDetails.setOrientation(Qt.Orientation.Vertical)
        self.imagePreviewWidget = ImagePreviewWidget(self.splitterPreviewDetails)
        self.imagePreviewWidget.setObjectName("imagePreviewWidget")
        sizePolicy7 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy7.setHorizontalStretch(0)
        sizePolicy7.setVerticalStretch(2)
        sizePolicy7.setHeightForWidth(self.imagePreviewWidget.sizePolicy().hasHeightForWidth())
        self.imagePreviewWidget.setSizePolicy(sizePolicy7)
        self.splitterPreviewDetails.addWidget(self.imagePreviewWidget)
        self.tabWidgetRightPanel = QTabWidget(self.splitterPreviewDetails)
        self.tabWidgetRightPanel.setObjectName("tabWidgetRightPanel")
        sizePolicy7.setHeightForWidth(self.tabWidgetRightPanel.sizePolicy().hasHeightForWidth())
        self.tabWidgetRightPanel.setSizePolicy(sizePolicy7)
        self.tabWidgetRightPanel.setMinimumSize(QSize(200, 220))
        self.tabImageDetails = QWidget()
        self.tabImageDetails.setObjectName("tabImageDetails")
        self.verticalLayoutTabDetails = QVBoxLayout(self.tabImageDetails)
        self.verticalLayoutTabDetails.setSpacing(0)
        self.verticalLayoutTabDetails.setObjectName("verticalLayoutTabDetails")
        self.verticalLayoutTabDetails.setContentsMargins(0, 0, 0, 0)
        self.selectedImageDetailsWidget = SelectedImageDetailsWidget(self.tabImageDetails)
        self.selectedImageDetailsWidget.setObjectName("selectedImageDetailsWidget")

        self.verticalLayoutTabDetails.addWidget(self.selectedImageDetailsWidget)

        self.tabWidgetRightPanel.addTab(self.tabImageDetails, "")
        self.splitterPreviewDetails.addWidget(self.tabWidgetRightPanel)

        self.verticalLayout_previewDetailContent.addWidget(self.splitterPreviewDetails)

        self.verticalLayout_previewDetailContent.setStretch(0, 3)

        self.verticalLayout_previewDetail.addWidget(self.framePreviewDetailContent)

        self.splitterMainWorkArea.addWidget(self.framePreviewDetailPanel)

        self.verticalLayout_workspace.addWidget(self.splitterMainWorkArea)

        self.frameActionToolbar = QFrame(SearchTab)
        self.frameActionToolbar.setObjectName("frameActionToolbar")
        sizePolicy8 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy8.setHorizontalStretch(0)
        sizePolicy8.setVerticalStretch(0)
        sizePolicy8.setHeightForWidth(self.frameActionToolbar.sizePolicy().hasHeightForWidth())
        self.frameActionToolbar.setSizePolicy(sizePolicy8)
        self.frameActionToolbar.setFrameShape(QFrame.Shape.StyledPanel)
        self.frameActionToolbar.setFrameShadow(QFrame.Shadow.Raised)
        self.horizontalLayout_actionToolbar = QHBoxLayout(self.frameActionToolbar)
        self.horizontalLayout_actionToolbar.setObjectName("horizontalLayout_actionToolbar")
        self.horizontalLayout_actionToolbar.setContentsMargins(10, 5, 10, 5)
        self.pushButtonStageToBatchTag = QPushButton(self.frameActionToolbar)
        self.pushButtonStageToBatchTag.setObjectName("pushButtonStageToBatchTag")
        sizePolicy1.setHeightForWidth(self.pushButtonStageToBatchTag.sizePolicy().hasHeightForWidth())
        self.pushButtonStageToBatchTag.setSizePolicy(sizePolicy1)
        self.pushButtonStageToBatchTag.setMinimumWidth(140)

        self.horizontalLayout_actionToolbar.addWidget(self.pushButtonStageToBatchTag)

        self.horizontalSpacer_actionToolbar = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.horizontalLayout_actionToolbar.addItem(self.horizontalSpacer_actionToolbar)

        self.labelStatus = QLabel(self.frameActionToolbar)
        self.labelStatus.setObjectName("labelStatus")

        self.horizontalLayout_actionToolbar.addWidget(self.labelStatus)

        self.verticalLayout_workspace.addWidget(self.frameActionToolbar)

        self.retranslateUi(SearchTab)

        self.tabWidgetRightPanel.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(SearchTab)

    # setupUi

    def retranslateUi(self, SearchTab: QWidget) -> None:
        self.labelDataset.setText(
            QCoreApplication.translate("SearchTab", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8:", None)
        )
        self.lineEditDatasetPath.setPlaceholderText(
            QCoreApplication.translate(
                "SearchTab",
                "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30c7\u30a3\u30ec\u30af\u30c8\u30ea\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044",
                None,
            )
        )
        self.pushButtonSelectDataset.setText(QCoreApplication.translate("SearchTab", "\u9078\u629e", None))
        self.pushButtonSettings.setText(QCoreApplication.translate("SearchTab", "\u8a2d\u5b9a", None))
        self.labelDbInfo.setStyleSheet(QCoreApplication.translate("SearchTab", "font-weight: bold;", None))
        self.labelDbInfo.setText(
            QCoreApplication.translate(
                "SearchTab", "\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9: \u672a\u63a5\u7d9a", None
            )
        )
        self.labelFilterSearch.setStyleSheet(
            QCoreApplication.translate("SearchTab", "font-weight: bold;", None)
        )
        self.labelFilterSearch.setText(
            QCoreApplication.translate(
                "SearchTab", "\u691c\u7d22\u30fb\u30d5\u30a3\u30eb\u30bf\u30fc", None
            )
        )
        # if QT_CONFIG(tooltip)
        self.labelExportTarget.setToolTip(
            QCoreApplication.translate(
                "SearchTab",
                "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8\u5bfe\u8c61\u306f\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u96c6\u5408\uff08\u660e\u793a\u7684\u306b\u6295\u5165\u3057\u305f\u753b\u50cf\uff09\u3067\u3059",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.labelExportTarget.setText(
            QCoreApplication.translate(
                "SearchTab", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8\u5bfe\u8c61: 0 \u679a", None
            )
        )
        # if QT_CONFIG(tooltip)
        self.btnExportData.setToolTip(
            QCoreApplication.translate(
                "SearchTab",
                "\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u96c6\u5408\u3092\u30a8\u30af\u30b9\u30dd\u30fc\u30c8",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.btnExportData.setText(
            QCoreApplication.translate("SearchTab", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None)
        )
        self.labelPreviewDetail.setStyleSheet(
            QCoreApplication.translate("SearchTab", "font-weight: bold;", None)
        )
        self.labelPreviewDetail.setText(
            QCoreApplication.translate(
                "SearchTab", "\u30d7\u30ec\u30d3\u30e5\u30fc\u30fb\u8a73\u7d30", None
            )
        )
        self.tabWidgetRightPanel.setTabText(
            self.tabWidgetRightPanel.indexOf(self.tabImageDetails),
            QCoreApplication.translate("SearchTab", "\u753b\u50cf\u8a73\u7d30", None),
        )
        # if QT_CONFIG(tooltip)
        self.pushButtonStageToBatchTag.setToolTip(
            QCoreApplication.translate(
                "SearchTab",
                "\u9078\u629e\u4e2d\u306e\u753b\u50cf\u3092\u30d0\u30c3\u30c1\u30bf\u30b0\u306e\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u306b\u8ffd\u52a0\u3057\u307e\u3059",
                None,
            )
        )
        # endif // QT_CONFIG(tooltip)
        self.pushButtonStageToBatchTag.setText(
            QCoreApplication.translate(
                "SearchTab", "\u9078\u629e\u3092\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u3078", None
            )
        )
        self.labelStatus.setText(QCoreApplication.translate("SearchTab", "\u6e96\u5099\u5b8c\u4e86", None))
        pass

    # retranslateUi
