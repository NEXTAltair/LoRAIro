
################################################################################
## Form generated from reading UI file 'MainWindow.ui'
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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.model_selection_widget import ModelSelectionWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.thumbnail import ThumbnailSelectorWidget


class Ui_MainWindow:
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(803, 563)
        icon = QIcon()
        icon.addFile(".", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
        self.actionOpenDataset = QAction(MainWindow)
        self.actionOpenDataset.setObjectName("actionOpenDataset")
        self.actionExit = QAction(MainWindow)
        self.actionExit.setObjectName("actionExit")
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
        self.actionAbout = QAction(MainWindow)
        self.actionAbout.setObjectName("actionAbout")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_main = QVBoxLayout(self.centralwidget)
        self.verticalLayout_main.setSpacing(0)
        self.verticalLayout_main.setObjectName("verticalLayout_main")
        self.verticalLayout_main.setContentsMargins(0, 0, 0, 0)
        self.frameDatasetSelector = QFrame(self.centralwidget)
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


        self.verticalLayout_main.addWidget(self.frameDatasetSelector)

        self.frameDbStatus = QFrame(self.centralwidget)
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

        self.pushButtonRegisterImages = QPushButton(self.frameDbStatus)
        self.pushButtonRegisterImages.setObjectName("pushButtonRegisterImages")
        sizePolicy1.setHeightForWidth(self.pushButtonRegisterImages.sizePolicy().hasHeightForWidth())
        self.pushButtonRegisterImages.setSizePolicy(sizePolicy1)

        self.horizontalLayout_dbStatus.addWidget(self.pushButtonRegisterImages)

        self.progressBarRegistration = QProgressBar(self.frameDbStatus)
        self.progressBarRegistration.setObjectName("progressBarRegistration")
        sizePolicy1.setHeightForWidth(self.progressBarRegistration.sizePolicy().hasHeightForWidth())
        self.progressBarRegistration.setSizePolicy(sizePolicy1)
        self.progressBarRegistration.setVisible(False)
        self.progressBarRegistration.setValue(0)

        self.horizontalLayout_dbStatus.addWidget(self.progressBarRegistration)


        self.verticalLayout_main.addWidget(self.frameDbStatus)

        self.splitterMainWorkArea = QSplitter(self.centralwidget)
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

        self.splitter = QSplitter(self.frameFilterSearchPanel)
        self.splitter.setObjectName("splitter")
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.frameFilterSearchContent = QFrame(self.splitter)
        self.frameFilterSearchContent.setObjectName("frameFilterSearchContent")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(3)
        sizePolicy4.setHeightForWidth(self.frameFilterSearchContent.sizePolicy().hasHeightForWidth())
        self.frameFilterSearchContent.setSizePolicy(sizePolicy4)
        self.frameFilterSearchContent.setMinimumSize(QSize(200, 150))
        self.frameFilterSearchContent.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalLayout_2 = QVBoxLayout(self.frameFilterSearchContent)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.filterSearchPanel = FilterSearchPanel(self.frameFilterSearchContent)
        self.filterSearchPanel.setObjectName("filterSearchPanel")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(1)
        sizePolicy5.setHeightForWidth(self.filterSearchPanel.sizePolicy().hasHeightForWidth())
        self.filterSearchPanel.setSizePolicy(sizePolicy5)

        self.verticalLayout_2.addWidget(self.filterSearchPanel)

        self.splitter.addWidget(self.frameFilterSearchContent)
        self.selectedImageDetailsWidget = SelectedImageDetailsWidget(self.splitter)
        self.selectedImageDetailsWidget.setObjectName("selectedImageDetailsWidget")
        sizePolicy5.setHeightForWidth(self.selectedImageDetailsWidget.sizePolicy().hasHeightForWidth())
        self.selectedImageDetailsWidget.setSizePolicy(sizePolicy5)
        self.selectedImageDetailsWidget.setMinimumSize(QSize(200, 100))
        self.splitter.addWidget(self.selectedImageDetailsWidget)

        self.verticalLayout.addWidget(self.splitter)

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
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy6.setHorizontalStretch(2)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.thumbnailSelectorWidget.sizePolicy().hasHeightForWidth())
        self.thumbnailSelectorWidget.setSizePolicy(sizePolicy6)

        self.verticalLayout_thumbnailGrid.addWidget(self.thumbnailSelectorWidget)

        self.frameThumbnailStatusIndicator = QFrame(self.frameThumbnailGrid)
        self.frameThumbnailStatusIndicator.setObjectName("frameThumbnailStatusIndicator")
        sizePolicy7 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy7.setHorizontalStretch(0)
        sizePolicy7.setVerticalStretch(0)
        sizePolicy7.setHeightForWidth(self.frameThumbnailStatusIndicator.sizePolicy().hasHeightForWidth())
        self.frameThumbnailStatusIndicator.setSizePolicy(sizePolicy7)
        self.frameThumbnailStatusIndicator.setStyleSheet("")
        self.frameThumbnailStatusIndicator.setFrameShape(QFrame.Shape.Box)
        self.horizontalLayout_thumbnailStatusIndicator = QHBoxLayout(self.frameThumbnailStatusIndicator)
        self.horizontalLayout_thumbnailStatusIndicator.setSpacing(8)
        self.horizontalLayout_thumbnailStatusIndicator.setObjectName("horizontalLayout_thumbnailStatusIndicator")
        self.horizontalLayout_thumbnailStatusIndicator.setContentsMargins(8, -1, 8, -1)
        self.labelStatusIndicatorTitle = QLabel(self.frameThumbnailStatusIndicator)
        self.labelStatusIndicatorTitle.setObjectName("labelStatusIndicatorTitle")

        self.horizontalLayout_thumbnailStatusIndicator.addWidget(self.labelStatusIndicatorTitle)

        self.labelStatusCompleted = QLabel(self.frameThumbnailStatusIndicator)
        self.labelStatusCompleted.setObjectName("labelStatusCompleted")

        self.horizontalLayout_thumbnailStatusIndicator.addWidget(self.labelStatusCompleted)

        self.labelStatusPartial = QLabel(self.frameThumbnailStatusIndicator)
        self.labelStatusPartial.setObjectName("labelStatusPartial")

        self.horizontalLayout_thumbnailStatusIndicator.addWidget(self.labelStatusPartial)

        self.labelStatusError = QLabel(self.frameThumbnailStatusIndicator)
        self.labelStatusError.setObjectName("labelStatusError")

        self.horizontalLayout_thumbnailStatusIndicator.addWidget(self.labelStatusError)

        self.labelStatusProcessing = QLabel(self.frameThumbnailStatusIndicator)
        self.labelStatusProcessing.setObjectName("labelStatusProcessing")

        self.horizontalLayout_thumbnailStatusIndicator.addWidget(self.labelStatusProcessing)

        self.horizontalSpacerStatusIndicator = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_thumbnailStatusIndicator.addItem(self.horizontalSpacerStatusIndicator)


        self.verticalLayout_thumbnailGrid.addWidget(self.frameThumbnailStatusIndicator)

        self.splitterMainWorkArea.addWidget(self.frameThumbnailGrid)
        self.framePreviewDetailPanel = QFrame(self.splitterMainWorkArea)
        self.framePreviewDetailPanel.setObjectName("framePreviewDetailPanel")
        sizePolicy6.setHeightForWidth(self.framePreviewDetailPanel.sizePolicy().hasHeightForWidth())
        self.framePreviewDetailPanel.setSizePolicy(sizePolicy6)
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
        sizePolicy8 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy8.setHorizontalStretch(0)
        sizePolicy8.setVerticalStretch(0)
        sizePolicy8.setHeightForWidth(self.framePreviewDetailContent.sizePolicy().hasHeightForWidth())
        self.framePreviewDetailContent.setSizePolicy(sizePolicy8)
        self.framePreviewDetailContent.setMaximumSize(QSize(16777215, 16777215))
        self.framePreviewDetailContent.setStyleSheet("")
        self.framePreviewDetailContent.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalLayout_previewDetailContent = QVBoxLayout(self.framePreviewDetailContent)
        self.verticalLayout_previewDetailContent.setSpacing(8)
        self.verticalLayout_previewDetailContent.setObjectName("verticalLayout_previewDetailContent")
        self.verticalLayout_previewDetailContent.setContentsMargins(5, 5, 5, 5)
        self.imagePreviewWidget = ImagePreviewWidget(self.framePreviewDetailContent)
        self.imagePreviewWidget.setObjectName("imagePreviewWidget")
        sizePolicy9 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy9.setHorizontalStretch(0)
        sizePolicy9.setVerticalStretch(2)
        sizePolicy9.setHeightForWidth(self.imagePreviewWidget.sizePolicy().hasHeightForWidth())
        self.imagePreviewWidget.setSizePolicy(sizePolicy9)

        self.verticalLayout_previewDetailContent.addWidget(self.imagePreviewWidget)

        self.groupBoxAnnotationControl = QGroupBox(self.framePreviewDetailContent)
        self.groupBoxAnnotationControl.setObjectName("groupBoxAnnotationControl")
        sizePolicy7.setHeightForWidth(self.groupBoxAnnotationControl.sizePolicy().hasHeightForWidth())
        self.groupBoxAnnotationControl.setSizePolicy(sizePolicy7)
        self.verticalLayout_annotationControl = QVBoxLayout(self.groupBoxAnnotationControl)
        self.verticalLayout_annotationControl.setObjectName("verticalLayout_annotationControl")
        self.modelSelectionWidget = ModelSelectionWidget(self.groupBoxAnnotationControl)
        self.modelSelectionWidget.setObjectName("modelSelectionWidget")
        sizePolicy10 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy10.setHorizontalStretch(0)
        sizePolicy10.setVerticalStretch(0)
        sizePolicy10.setHeightForWidth(self.modelSelectionWidget.sizePolicy().hasHeightForWidth())
        self.modelSelectionWidget.setSizePolicy(sizePolicy10)

        self.verticalLayout_annotationControl.addWidget(self.modelSelectionWidget)


        self.verticalLayout_previewDetailContent.addWidget(self.groupBoxAnnotationControl)

        self.groupBoxAnnotationResults = QGroupBox(self.framePreviewDetailContent)
        self.groupBoxAnnotationResults.setObjectName("groupBoxAnnotationResults")
        self.verticalLayout_annotationResults = QVBoxLayout(self.groupBoxAnnotationResults)
        self.verticalLayout_annotationResults.setObjectName("verticalLayout_annotationResults")
        self.tabWidgetAnnotationResults = QTabWidget(self.groupBoxAnnotationResults)
        self.tabWidgetAnnotationResults.setObjectName("tabWidgetAnnotationResults")
        self.tabCaption = QWidget()
        self.tabCaption.setObjectName("tabCaption")
        self.verticalLayout_tabCaption = QVBoxLayout(self.tabCaption)
        self.verticalLayout_tabCaption.setObjectName("verticalLayout_tabCaption")
        self.textEditCaption = QTextEdit(self.tabCaption)
        self.textEditCaption.setObjectName("textEditCaption")

        self.verticalLayout_tabCaption.addWidget(self.textEditCaption)

        self.tabWidgetAnnotationResults.addTab(self.tabCaption, "")
        self.tabTags = QWidget()
        self.tabTags.setObjectName("tabTags")
        self.verticalLayout_tabTags = QVBoxLayout(self.tabTags)
        self.verticalLayout_tabTags.setObjectName("verticalLayout_tabTags")
        self.textEditTags = QTextEdit(self.tabTags)
        self.textEditTags.setObjectName("textEditTags")

        self.verticalLayout_tabTags.addWidget(self.textEditTags)

        self.tabWidgetAnnotationResults.addTab(self.tabTags, "")
        self.tabMetadata = QWidget()
        self.tabMetadata.setObjectName("tabMetadata")
        self.verticalLayout_tabMetadata = QVBoxLayout(self.tabMetadata)
        self.verticalLayout_tabMetadata.setObjectName("verticalLayout_tabMetadata")
        self.textEditMetadata = QTextEdit(self.tabMetadata)
        self.textEditMetadata.setObjectName("textEditMetadata")
        self.textEditMetadata.setReadOnly(True)

        self.verticalLayout_tabMetadata.addWidget(self.textEditMetadata)

        self.tabWidgetAnnotationResults.addTab(self.tabMetadata, "")

        self.verticalLayout_annotationResults.addWidget(self.tabWidgetAnnotationResults)


        self.verticalLayout_previewDetailContent.addWidget(self.groupBoxAnnotationResults)


        self.verticalLayout_previewDetail.addWidget(self.framePreviewDetailContent)

        self.splitterMainWorkArea.addWidget(self.framePreviewDetailPanel)

        self.verticalLayout_main.addWidget(self.splitterMainWorkArea)

        self.frameActionToolbar = QFrame(self.centralwidget)
        self.frameActionToolbar.setObjectName("frameActionToolbar")
        sizePolicy7.setHeightForWidth(self.frameActionToolbar.sizePolicy().hasHeightForWidth())
        self.frameActionToolbar.setSizePolicy(sizePolicy7)
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


        self.verticalLayout_main.addWidget(self.frameActionToolbar)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName("menubar")
        self.menubar.setGeometry(QRect(0, 0, 803, 33))
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
        self.menuTools.addSeparator()
        self.menuTools.addAction(self.actionSettings)
        self.menuHelp.addAction(self.actionAbout)

        self.retranslateUi(MainWindow)
        self.pushButtonSelectDataset.clicked.connect(MainWindow.select_and_process_dataset)
        self.pushButtonRegisterImages.clicked.connect(MainWindow.register_images_to_db)
        self.pushButtonSettings.clicked.connect(MainWindow.open_settings)
        self.pushButtonAnnotate.clicked.connect(MainWindow.start_annotation)
        self.pushButtonExport.clicked.connect(MainWindow.export_data)

        self.tabWidgetAnnotationResults.setCurrentIndex(0)


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
        self.actionAbout.setText(QCoreApplication.translate("MainWindow", "LoRAIro\u306b\u3064\u3044\u3066", None))
        self.labelDataset.setText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8:", None))
        self.lineEditDatasetPath.setPlaceholderText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30c7\u30a3\u30ec\u30af\u30c8\u30ea\u3092\u9078\u629e\u3057\u3066\u304f\u3060\u3055\u3044", None))
        self.pushButtonSelectDataset.setText(QCoreApplication.translate("MainWindow", "\u9078\u629e", None))
        self.pushButtonSettings.setText(QCoreApplication.translate("MainWindow", "\u8a2d\u5b9a", None))
        self.labelDbInfo.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelDbInfo.setText(QCoreApplication.translate("MainWindow", "\u30c7\u30fc\u30bf\u30d9\u30fc\u30b9: \u672a\u63a5\u7d9a", None))
        self.pushButtonRegisterImages.setText(QCoreApplication.translate("MainWindow", "\u753b\u50cf\u3092DB\u767b\u9332", None))
        self.labelFilterSearch.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelFilterSearch.setText(QCoreApplication.translate("MainWindow", "\u691c\u7d22\u30fb\u30d5\u30a3\u30eb\u30bf\u30fc", None))
        self.labelStatusIndicatorTitle.setStyleSheet(QCoreApplication.translate("MainWindow", "font-size: 10px; font-weight: bold; color: #1976D2;", None))
        self.labelStatusIndicatorTitle.setText(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u72b6\u614b:", None))
        self.labelStatusCompleted.setStyleSheet(QCoreApplication.translate("MainWindow", "font-size: 9px; color: #4CAF50; font-weight: bold;", None))
        self.labelStatusCompleted.setText(QCoreApplication.translate("MainWindow", "\u2713 \u5b8c\u4e86: 0", None))
        self.labelStatusPartial.setStyleSheet(QCoreApplication.translate("MainWindow", "font-size: 9px; color: #FF9800; font-weight: bold;", None))
        self.labelStatusPartial.setText(QCoreApplication.translate("MainWindow", "\u26a0 \u90e8\u5206: 0", None))
        self.labelStatusError.setStyleSheet(QCoreApplication.translate("MainWindow", "font-size: 9px; color: #f44336; font-weight: bold;", None))
        self.labelStatusError.setText(QCoreApplication.translate("MainWindow", "\u2717 \u30a8\u30e9\u30fc: 0", None))
        self.labelStatusProcessing.setStyleSheet(QCoreApplication.translate("MainWindow", "font-size: 9px; color: #2196F3; font-weight: bold;", None))
        self.labelStatusProcessing.setText(QCoreApplication.translate("MainWindow", "\u25cf \u51e6\u7406\u4e2d: 0", None))
        self.labelPreviewDetail.setStyleSheet(QCoreApplication.translate("MainWindow", "font-weight: bold;", None))
        self.labelPreviewDetail.setText(QCoreApplication.translate("MainWindow", "\u30d7\u30ec\u30d3\u30e5\u30fc\u30fb\u8a73\u7d30", None))
        self.groupBoxAnnotationControl.setTitle(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u5236\u5fa1", None))
        self.groupBoxAnnotationResults.setTitle(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u7d50\u679c", None))
        self.textEditCaption.setPlaceholderText(QCoreApplication.translate("MainWindow", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u3053\u3053\u306b\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.tabWidgetAnnotationResults.setTabText(self.tabWidgetAnnotationResults.indexOf(self.tabCaption), QCoreApplication.translate("MainWindow", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.textEditTags.setPlaceholderText(QCoreApplication.translate("MainWindow", "\u30bf\u30b0\u304c\u3053\u3053\u306b\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.tabWidgetAnnotationResults.setTabText(self.tabWidgetAnnotationResults.indexOf(self.tabTags), QCoreApplication.translate("MainWindow", "\u30bf\u30b0", None))
        self.textEditMetadata.setPlaceholderText(QCoreApplication.translate("MainWindow", "\u30e1\u30bf\u30c7\u30fc\u30bf\u304c\u3053\u3053\u306b\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.tabWidgetAnnotationResults.setTabText(self.tabWidgetAnnotationResults.indexOf(self.tabMetadata), QCoreApplication.translate("MainWindow", "\u30e1\u30bf\u30c7\u30fc\u30bf", None))
        self.pushButtonAnnotate.setText(QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None))
        self.pushButtonExport.setText(QCoreApplication.translate("MainWindow", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None))
        self.labelStatus.setText(QCoreApplication.translate("MainWindow", "\u6e96\u5099\u5b8c\u4e86", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", "\u30d5\u30a1\u30a4\u30eb", None))
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "\u7de8\u96c6", None))
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", "\u8868\u793a", None))
        self.menuTools.setTitle(QCoreApplication.translate("MainWindow", "\u30c4\u30fc\u30eb", None))
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", "\u30d8\u30eb\u30d7", None))
    # retranslateUi

