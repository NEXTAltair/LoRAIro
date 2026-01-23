
################################################################################
## Form generated from reading UI file 'MainWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
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
    QAction,
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
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class Ui_MainWindow:
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1287, 1178)
        icon = QIcon()
        icon.addFile(".", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
        self.actionOpenDataset = QAction(MainWindow)
        self.actionOpenDataset.setObjectName("actionOpenDataset")
        self.actionExit = QAction(MainWindow)
        self.actionExit.setObjectName("actionExit")
        self.actionEditImage = QAction(MainWindow)
        self.actionEditImage.setObjectName("actionEditImage")
        self.actionSelectAll = QAction(MainWindow)
        self.actionSelectAll.setObjectName("actionSelectAll")
        self.actionDeselectAll = QAction(MainWindow)
        self.actionDeselectAll.setObjectName("actionDeselectAll")
        self.actionToggleFilterPanel = QAction(MainWindow)
        self.actionToggleFilterPanel.setObjectName("actionToggleFilterPanel")
        self.actionToggleFilterPanel.setCheckable(True)
        self.actionToggleFilterPanel.setChecked(True)
        self.actionTogglePreviewPanel = QAction(MainWindow)
        self.actionTogglePreviewPanel.setObjectName("actionTogglePreviewPanel")
        self.actionTogglePreviewPanel.setCheckable(True)
        self.actionTogglePreviewPanel.setChecked(True)
        self.actionAnnotation = QAction(MainWindow)
        self.actionAnnotation.setObjectName("actionAnnotation")
        self.actionExport = QAction(MainWindow)
        self.actionExport.setObjectName("actionExport")
        self.actionSettings = QAction(MainWindow)
        self.actionSettings.setObjectName("actionSettings")
        self.actionErrorLog = QAction(MainWindow)
        self.actionErrorLog.setObjectName("actionErrorLog")
        self.actionAbout = QAction(MainWindow)
        self.actionAbout.setObjectName("actionAbout")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_main = QVBoxLayout(self.centralwidget)
        self.verticalLayout_main.setSpacing(0)
        self.verticalLayout_main.setObjectName("verticalLayout_main")
        self.verticalLayout_main.setContentsMargins(0, 0, 0, 0)
        self.tabWidgetMainMode = QTabWidget(self.centralwidget)
        self.tabWidgetMainMode.setObjectName("tabWidgetMainMode")
        self.tabWorkspace = QWidget()
        self.tabWorkspace.setObjectName("tabWorkspace")
        self.verticalLayout_workspace = QVBoxLayout(self.tabWorkspace)
        self.verticalLayout_workspace.setSpacing(0)
        self.verticalLayout_workspace.setObjectName("verticalLayout_workspace")
        self.verticalLayout_workspace.setContentsMargins(0, 0, 0, 0)
        self.frameDatasetSelector = QFrame(self.tabWorkspace)
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

        self.horizontalSpacer_dataset = QSpacerItem(20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_dataset.addItem(self.horizontalSpacer_dataset)

        self.pushButtonSettings = QPushButton(self.frameDatasetSelector)
        self.pushButtonSettings.setObjectName("pushButtonSettings")
        sizePolicy1.setHeightForWidth(self.pushButtonSettings.sizePolicy().hasHeightForWidth())
        self.pushButtonSettings.setSizePolicy(sizePolicy1)

        self.horizontalLayout_dataset.addWidget(self.pushButtonSettings)


        self.verticalLayout_workspace.addWidget(self.frameDatasetSelector)

        self.frameDbStatus = QFrame(self.tabWorkspace)
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

        self.horizontalSpacer_dbStatus = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_dbStatus.addItem(self.horizontalSpacer_dbStatus)


        self.verticalLayout_workspace.addWidget(self.frameDbStatus)

        self.splitterMainWorkArea = QSplitter(self.tabWorkspace)
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

        self.frameActionToolbar = QFrame(self.tabWorkspace)
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
        self.pushButtonAnnotate = QPushButton(self.frameActionToolbar)
        self.pushButtonAnnotate.setObjectName("pushButtonAnnotate")
        sizePolicy1.setHeightForWidth(self.pushButtonAnnotate.sizePolicy().hasHeightForWidth())
        self.pushButtonAnnotate.setSizePolicy(sizePolicy1)

        self.horizontalLayout_actionToolbar.addWidget(self.pushButtonAnnotate)

        self.pushButtonExport = QPushButton(self.frameActionToolbar)
        self.pushButtonExport.setObjectName("pushButtonExport")
        sizePolicy1.setHeightForWidth(self.pushButtonExport.sizePolicy().hasHeightForWidth())
        self.pushButtonExport.setSizePolicy(sizePolicy1)

        self.horizontalLayout_actionToolbar.addWidget(self.pushButtonExport)

        self.horizontalSpacer_actionToolbar = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_actionToolbar.addItem(self.horizontalSpacer_actionToolbar)

        self.labelStatus = QLabel(self.frameActionToolbar)
        self.labelStatus.setObjectName("labelStatus")

        self.horizontalLayout_actionToolbar.addWidget(self.labelStatus)


        self.verticalLayout_workspace.addWidget(self.frameActionToolbar)

        self.tabWidgetMainMode.addTab(self.tabWorkspace, "")
        self.tabBatchTag = QWidget()
        self.tabBatchTag.setObjectName("tabBatchTag")
        self.verticalLayout_batchTag = QVBoxLayout(self.tabBatchTag)
        self.verticalLayout_batchTag.setSpacing(8)
        self.verticalLayout_batchTag.setObjectName("verticalLayout_batchTag")
        self.verticalLayout_batchTag.setContentsMargins(8, 8, 8, 8)
        self.splitterBatchTag = QSplitter(self.tabBatchTag)
        self.splitterBatchTag.setObjectName("splitterBatchTag")
        self.splitterBatchTag.setOrientation(Qt.Orientation.Horizontal)
        self.splitterBatchTag.setChildrenCollapsible(False)
        self.groupBoxStagingImages = QGroupBox(self.splitterBatchTag)
        self.groupBoxStagingImages.setObjectName("groupBoxStagingImages")
        self.verticalLayout_staging = QVBoxLayout(self.groupBoxStagingImages)
        self.verticalLayout_staging.setObjectName("verticalLayout_staging")
        self.gridLayout_staging = QGridLayout()
        self.gridLayout_staging.setSpacing(6)
        self.gridLayout_staging.setObjectName("gridLayout_staging")
        self.stagingPlaceholder = QLabel(self.groupBoxStagingImages)
        self.stagingPlaceholder.setObjectName("stagingPlaceholder")
        self.stagingPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gridLayout_staging.addWidget(self.stagingPlaceholder, 0, 0, 1, 1)


        self.verticalLayout_staging.addLayout(self.gridLayout_staging)

        self.splitterBatchTag.addWidget(self.groupBoxStagingImages)
        self.groupBoxBatchOperations = QGroupBox(self.splitterBatchTag)
        self.groupBoxBatchOperations.setObjectName("groupBoxBatchOperations")
        self.verticalLayout_operations = QVBoxLayout(self.groupBoxBatchOperations)
        self.verticalLayout_operations.setObjectName("verticalLayout_operations")
        self.splitterBatchTagOperations = QSplitter(self.groupBoxBatchOperations)
        self.splitterBatchTagOperations.setObjectName("splitterBatchTagOperations")
        self.splitterBatchTagOperations.setOrientation(Qt.Orientation.Vertical)
        self.splitterBatchTagOperations.setChildrenCollapsible(False)
        self.batchTagWidgetPlaceholder = QWidget(self.splitterBatchTagOperations)
        self.batchTagWidgetPlaceholder.setObjectName("batchTagWidgetPlaceholder")
        self.splitterBatchTagOperations.addWidget(self.batchTagWidgetPlaceholder)
        self.annotationDisplayPlaceholder = QWidget(self.splitterBatchTagOperations)
        self.annotationDisplayPlaceholder.setObjectName("annotationDisplayPlaceholder")
        self.splitterBatchTagOperations.addWidget(self.annotationDisplayPlaceholder)
        self.groupBoxAnnotation = QGroupBox(self.splitterBatchTagOperations)
        self.groupBoxAnnotation.setObjectName("groupBoxAnnotation")
        self.verticalLayout_annotation = QVBoxLayout(self.groupBoxAnnotation)
        self.verticalLayout_annotation.setObjectName("verticalLayout_annotation")
        self.labelAnnotationTarget = QLabel(self.groupBoxAnnotation)
        self.labelAnnotationTarget.setObjectName("labelAnnotationTarget")

        self.verticalLayout_annotation.addWidget(self.labelAnnotationTarget)

        self.annotationFilterPlaceholder = QWidget(self.groupBoxAnnotation)
        self.annotationFilterPlaceholder.setObjectName("annotationFilterPlaceholder")

        self.verticalLayout_annotation.addWidget(self.annotationFilterPlaceholder)

        self.modelSelectionPlaceholder = QWidget(self.groupBoxAnnotation)
        self.modelSelectionPlaceholder.setObjectName("modelSelectionPlaceholder")

        self.verticalLayout_annotation.addWidget(self.modelSelectionPlaceholder)

        self.btnAnnotationExecute = QPushButton(self.groupBoxAnnotation)
        self.btnAnnotationExecute.setObjectName("btnAnnotationExecute")

        self.verticalLayout_annotation.addWidget(self.btnAnnotationExecute)

        self.splitterBatchTagOperations.addWidget(self.groupBoxAnnotation)

        self.verticalLayout_operations.addWidget(self.splitterBatchTagOperations)

        self.splitterBatchTag.addWidget(self.groupBoxBatchOperations)

        self.verticalLayout_batchTag.addWidget(self.splitterBatchTag)

        self.tabWidgetMainMode.addTab(self.tabBatchTag, "")

        self.verticalLayout_main.addWidget(self.tabWidgetMainMode)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName("menubar")
        self.menubar.setGeometry(QRect(0, 0, 1287, 33))
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuEdit = QMenu(self.menubar)
        self.menuEdit.setObjectName("menuEdit")
        self.menuView = QMenu(self.menubar)
        self.menuView.setObjectName("menuView")
        self.menuTools = QMenu(self.menubar)
        self.menuTools.setObjectName("menuTools")
        self.menuHelp = QMenu(self.menubar)
        self.menuHelp.setObjectName("menuHelp")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuEdit.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuTools.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        self.menuFile.addAction(self.actionOpenDataset)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionExit)
        self.menuEdit.addAction(self.actionSelectAll)
        self.menuEdit.addAction(self.actionDeselectAll)
        self.menuView.addAction(self.actionToggleFilterPanel)
        self.menuView.addAction(self.actionTogglePreviewPanel)
        self.menuTools.addAction(self.actionAnnotation)
        self.menuTools.addAction(self.actionExport)
        self.menuTools.addAction(self.actionErrorLog)
        self.menuTools.addAction(self.actionEditImage)
        self.menuTools.addSeparator()
        self.menuTools.addAction(self.actionSettings)
        self.menuHelp.addAction(self.actionAbout)

        self.retranslateUi(MainWindow)
        self.pushButtonSelectDataset.clicked.connect(MainWindow.select_and_process_dataset)
        self.pushButtonSettings.clicked.connect(MainWindow.open_settings)
        self.pushButtonAnnotate.clicked.connect(MainWindow.start_annotation)
        self.pushButtonExport.clicked.connect(MainWindow.export_data)
        self.btnAnnotationExecute.clicked.connect(MainWindow.start_annotation)

        self.tabWidgetMainMode.setCurrentIndex(0)
        self.tabWidgetRightPanel.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", "LoRAIro - \u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9", None))
        self.actionOpenDataset.setText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u3092\u958b\u304f", None))
#if QT_CONFIG(shortcut)
        self.actionOpenDataset.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.actionExit.setText(QCoreApplication.translate("MainWindow", "\u7d42\u4e86", None))
#if QT_CONFIG(shortcut)
        self.actionExit.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Q", None))
#endif // QT_CONFIG(shortcut)
        self.actionEditImage.setText(QCoreApplication.translate("MainWindow", "\u753b\u50cf\u3092\u7de8\u96c6", None))
#if QT_CONFIG(tooltip)
        self.actionEditImage.setToolTip(QCoreApplication.translate("MainWindow", "\u9078\u629e\u753b\u50cf\u306e\u30bf\u30b0\u30fb\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u30fb\u8a55\u4fa1\u3092\u7de8\u96c6", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(shortcut)
        self.actionEditImage.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+E", None))
#endif // QT_CONFIG(shortcut)
        self.actionSelectAll.setText(QCoreApplication.translate("MainWindow", "\u3059\u3079\u3066\u9078\u629e", None))
#if QT_CONFIG(shortcut)
        self.actionSelectAll.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+A", None))
#endif // QT_CONFIG(shortcut)
        self.actionDeselectAll.setText(QCoreApplication.translate("MainWindow", "\u9078\u629e\u89e3\u9664", None))
#if QT_CONFIG(shortcut)
        self.actionDeselectAll.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+D", None))
#endif // QT_CONFIG(shortcut)
        self.actionToggleFilterPanel.setText(QCoreApplication.translate("MainWindow", "\u30d5\u30a3\u30eb\u30bf\u30fc\u30d1\u30cd\u30eb\u8868\u793a\u5207\u66ff", None))
        self.actionTogglePreviewPanel.setText(QCoreApplication.translate("MainWindow", "\u30d7\u30ec\u30d3\u30e5\u30fc\u30d1\u30cd\u30eb\u8868\u793a\u5207\u66ff", None))
        self.actionAnnotation.setText(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None))
#if QT_CONFIG(shortcut)
        self.actionAnnotation.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+T", None))
#endif // QT_CONFIG(shortcut)
        self.actionExport.setText(QCoreApplication.translate("MainWindow", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None))
#if QT_CONFIG(shortcut)
        self.actionExport.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+E", None))
#endif // QT_CONFIG(shortcut)
        self.actionSettings.setText(QCoreApplication.translate("MainWindow", "\u8a2d\u5b9a", None))
#if QT_CONFIG(shortcut)
        self.actionSettings.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+,", None))
#endif // QT_CONFIG(shortcut)
        self.actionErrorLog.setText(QCoreApplication.translate("MainWindow", "\u30a8\u30e9\u30fc\u30ed\u30b0", None))
#if QT_CONFIG(tooltip)
        self.actionErrorLog.setToolTip(QCoreApplication.translate("MainWindow", "\u30a8\u30e9\u30fc\u30ed\u30b0\u30d3\u30e5\u30fc\u30a2\u3092\u8868\u793a", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(shortcut)
        self.actionErrorLog.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+L", None))
#endif // QT_CONFIG(shortcut)
        self.actionAbout.setText(QCoreApplication.translate("MainWindow", "LoRAIro\u306b\u3064\u3044\u3066", None))
        self.labelDataset.setText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8:", None))
        self.lineEditDatasetPath.setPlaceholderText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30c7\u30a3\u30ec\u30af\u30c8\u30ea\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044", None))
        self.pushButtonSelectDataset.setText(QCoreApplication.translate("MainWindow", "\u9078\u629e", None))
        self.pushButtonSettings.setText(QCoreApplication.translate("MainWindow", "\u8a2d\u5b9a", None))
        self.labelDbInfo.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelDbInfo.setText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9: \u672a\u63a5\u7d9a", None))
        self.labelFilterSearch.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelFilterSearch.setText(QCoreApplication.translate("MainWindow", "\u691c\u7d22\u30fb\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.labelPreviewDetail.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelPreviewDetail.setText(QCoreApplication.translate("MainWindow", "\u30d7\u30ec\u30d3\u30e5\u30fc\u30fb\u8a73\u7d30", None))
        self.tabWidgetRightPanel.setTabText(self.tabWidgetRightPanel.indexOf(self.tabImageDetails), QCoreApplication.translate("MainWindow", "\u753b\u50cf\u8a73\u7d30", None))
        self.pushButtonAnnotate.setText(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None))
        self.pushButtonExport.setText(QCoreApplication.translate("MainWindow", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None))
        self.labelStatus.setText(QCoreApplication.translate("MainWindow", "\u6e96\u5099\u5b8c\u4e86", None))
        self.tabWidgetMainMode.setTabText(self.tabWidgetMainMode.indexOf(self.tabWorkspace), QCoreApplication.translate("MainWindow", "\u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9", None))
        self.groupBoxStagingImages.setTitle(QCoreApplication.translate("MainWindow", "\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u753b\u50cf", None))
        self.stagingPlaceholder.setText(QCoreApplication.translate("MainWindow", "\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u753b\u50cf\u304c\u3042\u308a\u307e\u305b\u3093", None))
        self.groupBoxBatchOperations.setTitle(QCoreApplication.translate("MainWindow", "\u64cd\u4f5c", None))
        self.groupBoxAnnotation.setTitle(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None))
        self.labelAnnotationTarget.setText(QCoreApplication.translate("MainWindow", "\u5bfe\u8c61: \u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u6e08\u307f\u753b\u50cf", None))
        self.btnAnnotationExecute.setText(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u5b9f\u884c", None))
        self.tabWidgetMainMode.setTabText(self.tabWidgetMainMode.indexOf(self.tabBatchTag), QCoreApplication.translate("MainWindow", "\u30d0\u30c3\u30c1\u30bf\u30b0", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", "\u30d5\u30a1\u30a4\u30eb", None))
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "\u7de8\u96c6", None))
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", "\u8868\u793a", None))
        self.menuTools.setTitle(QCoreApplication.translate("MainWindow", "\u30c4\u30fc\u30eb", None))
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", "\u30d8\u30eb\u30d7", None))
    # retranslateUi

