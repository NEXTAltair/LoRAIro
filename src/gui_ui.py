# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'gui.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QGraphicsView, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMenuBar,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget)

from DatasetOverviewWidget import DatasetOverviewWidget
from DirectoryPickerWidget import DirectoryPickerWidget
from ImageEditWidget import ImageEditWidget
from SettingspageWidget import SettingspageWidget

class Ui_mainWindow(object):
    def setupUi(self, mainWindow):
        if not mainWindow.objectName():
            mainWindow.setObjectName(u"mainWindow")
        mainWindow.resize(1172, 1371)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(mainWindow.sizePolicy().hasHeightForWidth())
        mainWindow.setSizePolicy(sizePolicy)
        mainWindow.setMinimumSize(QSize(0, 0))
        self.actionOpen = QAction(mainWindow)
        self.actionOpen.setObjectName(u"actionOpen")
        self.actionSave = QAction(mainWindow)
        self.actionSave.setObjectName(u"actionSave")
        self.actionExit = QAction(mainWindow)
        self.actionExit.setObjectName(u"actionExit")
        self.actionAbout = QAction(mainWindow)
        self.actionAbout.setObjectName(u"actionAbout")
        self.centralWidget = QWidget(mainWindow)
        self.centralWidget.setObjectName(u"centralWidget")
        sizePolicy.setHeightForWidth(self.centralWidget.sizePolicy().hasHeightForWidth())
        self.centralWidget.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(self.centralWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.datasetSelector = DirectoryPickerWidget(self.centralWidget)
        self.datasetSelector.setObjectName(u"datasetSelector")
        sizePolicy.setHeightForWidth(self.datasetSelector.sizePolicy().hasHeightForWidth())
        self.datasetSelector.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.datasetSelector)

        self.maineindowspliter = QSplitter(self.centralWidget)
        self.maineindowspliter.setObjectName(u"maineindowspliter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(2)
        sizePolicy1.setHeightForWidth(self.maineindowspliter.sizePolicy().hasHeightForWidth())
        self.maineindowspliter.setSizePolicy(sizePolicy1)
        self.maineindowspliter.setOrientation(Qt.Orientation.Horizontal)
        self.sidebarList = QListWidget(self.maineindowspliter)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        self.sidebarList.setObjectName(u"sidebarList")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(2)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.sidebarList.sizePolicy().hasHeightForWidth())
        self.sidebarList.setSizePolicy(sizePolicy2)
        self.sidebarList.setMaximumSize(QSize(512, 16777215))
        self.maineindowspliter.addWidget(self.sidebarList)
        self.contentStackedWidget = QStackedWidget(self.maineindowspliter)
        self.contentStackedWidget.setObjectName(u"contentStackedWidget")
        sizePolicy.setHeightForWidth(self.contentStackedWidget.sizePolicy().hasHeightForWidth())
        self.contentStackedWidget.setSizePolicy(sizePolicy)
        self.pageImageEdit = ImageEditWidget()
        self.pageImageEdit.setObjectName(u"pageImageEdit")
        self.verticalLayoutImageEdit = QVBoxLayout(self.pageImageEdit)
        self.verticalLayoutImageEdit.setObjectName(u"verticalLayoutImageEdit")
        self.contentStackedWidget.addWidget(self.pageImageEdit)
        self.pageAutoTag = QWidget()
        self.pageAutoTag.setObjectName(u"pageAutoTag")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(2)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.pageAutoTag.sizePolicy().hasHeightForWidth())
        self.pageAutoTag.setSizePolicy(sizePolicy3)
        self.verticalLayoutAutoTag = QVBoxLayout(self.pageAutoTag)
        self.verticalLayoutAutoTag.setObjectName(u"verticalLayoutAutoTag")
        self.labelAutoTagTitle = QLabel(self.pageAutoTag)
        self.labelAutoTagTitle.setObjectName(u"labelAutoTagTitle")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.labelAutoTagTitle.setFont(font)

        self.verticalLayoutAutoTag.addWidget(self.labelAutoTagTitle)

        self.horizontalLayoutAutoTagContent = QHBoxLayout()
        self.horizontalLayoutAutoTagContent.setObjectName(u"horizontalLayoutAutoTagContent")
        self.tableWidgetAutoTagImages = QTableWidget(self.pageAutoTag)
        if (self.tableWidgetAutoTagImages.columnCount() < 4):
            self.tableWidgetAutoTagImages.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetAutoTagImages.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetAutoTagImages.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetAutoTagImages.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetAutoTagImages.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        self.tableWidgetAutoTagImages.setObjectName(u"tableWidgetAutoTagImages")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(3)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.tableWidgetAutoTagImages.sizePolicy().hasHeightForWidth())
        self.tableWidgetAutoTagImages.setSizePolicy(sizePolicy4)

        self.horizontalLayoutAutoTagContent.addWidget(self.tableWidgetAutoTagImages)

        self.verticalLayoutAutoTagPreview = QVBoxLayout()
        self.verticalLayoutAutoTagPreview.setObjectName(u"verticalLayoutAutoTagPreview")
        self.labelAutoTagPreview = QLabel(self.pageAutoTag)
        self.labelAutoTagPreview.setObjectName(u"labelAutoTagPreview")
        self.labelAutoTagPreview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayoutAutoTagPreview.addWidget(self.labelAutoTagPreview)

        self.graphicsViewAutoTagPreview = QGraphicsView(self.pageAutoTag)
        self.graphicsViewAutoTagPreview.setObjectName(u"graphicsViewAutoTagPreview")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(1)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.graphicsViewAutoTagPreview.sizePolicy().hasHeightForWidth())
        self.graphicsViewAutoTagPreview.setSizePolicy(sizePolicy5)

        self.verticalLayoutAutoTagPreview.addWidget(self.graphicsViewAutoTagPreview)


        self.horizontalLayoutAutoTagContent.addLayout(self.verticalLayoutAutoTagPreview)


        self.verticalLayoutAutoTag.addLayout(self.horizontalLayoutAutoTagContent)

        self.groupBoxTagOptions = QGroupBox(self.pageAutoTag)
        self.groupBoxTagOptions.setObjectName(u"groupBoxTagOptions")
        self.horizontalLayoutTagOptions = QHBoxLayout(self.groupBoxTagOptions)
        self.horizontalLayoutTagOptions.setObjectName(u"horizontalLayoutTagOptions")
        self.labelModel = QLabel(self.groupBoxTagOptions)
        self.labelModel.setObjectName(u"labelModel")

        self.horizontalLayoutTagOptions.addWidget(self.labelModel)

        self.comboBoxModel = QComboBox(self.groupBoxTagOptions)
        self.comboBoxModel.addItem("")
        self.comboBoxModel.addItem("")
        self.comboBoxModel.addItem("")
        self.comboBoxModel.setObjectName(u"comboBoxModel")

        self.horizontalLayoutTagOptions.addWidget(self.comboBoxModel)

        self.labelModelName = QLabel(self.groupBoxTagOptions)
        self.labelModelName.setObjectName(u"labelModelName")

        self.horizontalLayoutTagOptions.addWidget(self.labelModelName)

        self.comboBoxModelName = QComboBox(self.groupBoxTagOptions)
        self.comboBoxModelName.setObjectName(u"comboBoxModelName")

        self.horizontalLayoutTagOptions.addWidget(self.comboBoxModelName)

        self.horizontalSpacerTagOptions = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutTagOptions.addItem(self.horizontalSpacerTagOptions)

        self.pushButtonGenerateTags = QPushButton(self.groupBoxTagOptions)
        self.pushButtonGenerateTags.setObjectName(u"pushButtonGenerateTags")

        self.horizontalLayoutTagOptions.addWidget(self.pushButtonGenerateTags)


        self.verticalLayoutAutoTag.addWidget(self.groupBoxTagOptions)

        self.groupBoxGeneratedTags = QGroupBox(self.pageAutoTag)
        self.groupBoxGeneratedTags.setObjectName(u"groupBoxGeneratedTags")
        self.verticalLayoutGeneratedTags = QVBoxLayout(self.groupBoxGeneratedTags)
        self.verticalLayoutGeneratedTags.setObjectName(u"verticalLayoutGeneratedTags")
        self.labelGeneratedTags = QLabel(self.groupBoxGeneratedTags)
        self.labelGeneratedTags.setObjectName(u"labelGeneratedTags")

        self.verticalLayoutGeneratedTags.addWidget(self.labelGeneratedTags)

        self.textEditGeneratedTags = QTextEdit(self.groupBoxGeneratedTags)
        self.textEditGeneratedTags.setObjectName(u"textEditGeneratedTags")

        self.verticalLayoutGeneratedTags.addWidget(self.textEditGeneratedTags)

        self.comboBoxTagActions = QComboBox(self.groupBoxGeneratedTags)
        self.comboBoxTagActions.setObjectName(u"comboBoxTagActions")

        self.verticalLayoutGeneratedTags.addWidget(self.comboBoxTagActions)

        self.horizontalLayoutTagActions = QHBoxLayout()
        self.horizontalLayoutTagActions.setObjectName(u"horizontalLayoutTagActions")
        self.pushButtonEditTags = QPushButton(self.groupBoxGeneratedTags)
        self.pushButtonEditTags.setObjectName(u"pushButtonEditTags")

        self.horizontalLayoutTagActions.addWidget(self.pushButtonEditTags)

        self.pushButtonApplyTags = QPushButton(self.groupBoxGeneratedTags)
        self.pushButtonApplyTags.setObjectName(u"pushButtonApplyTags")

        self.horizontalLayoutTagActions.addWidget(self.pushButtonApplyTags)


        self.verticalLayoutGeneratedTags.addLayout(self.horizontalLayoutTagActions)


        self.verticalLayoutAutoTag.addWidget(self.groupBoxGeneratedTags)

        self.contentStackedWidget.addWidget(self.pageAutoTag)
        self.pageTagCaptionEdit = QWidget()
        self.pageTagCaptionEdit.setObjectName(u"pageTagCaptionEdit")
        self.verticalLayoutTagCaptionEdit = QVBoxLayout(self.pageTagCaptionEdit)
        self.verticalLayoutTagCaptionEdit.setObjectName(u"verticalLayoutTagCaptionEdit")
        self.labelTagCaptionEditTitle = QLabel(self.pageTagCaptionEdit)
        self.labelTagCaptionEditTitle.setObjectName(u"labelTagCaptionEditTitle")

        self.verticalLayoutTagCaptionEdit.addWidget(self.labelTagCaptionEditTitle)

        self.contentStackedWidget.addWidget(self.pageTagCaptionEdit)
        self.DatasetOverview = DatasetOverviewWidget()
        self.DatasetOverview.setObjectName(u"DatasetOverview")
        sizePolicy.setHeightForWidth(self.DatasetOverview.sizePolicy().hasHeightForWidth())
        self.DatasetOverview.setSizePolicy(sizePolicy)
        self.contentStackedWidget.addWidget(self.DatasetOverview)
        self.pageBatchProcessing = QWidget()
        self.pageBatchProcessing.setObjectName(u"pageBatchProcessing")
        self.verticalLayoutBatchProcessing = QVBoxLayout(self.pageBatchProcessing)
        self.verticalLayoutBatchProcessing.setObjectName(u"verticalLayoutBatchProcessing")
        self.labelBatchProcessingTitle = QLabel(self.pageBatchProcessing)
        self.labelBatchProcessingTitle.setObjectName(u"labelBatchProcessingTitle")

        self.verticalLayoutBatchProcessing.addWidget(self.labelBatchProcessingTitle)

        self.contentStackedWidget.addWidget(self.pageBatchProcessing)
        self.pageExportImport = QWidget()
        self.pageExportImport.setObjectName(u"pageExportImport")
        self.verticalLayoutExportImport = QVBoxLayout(self.pageExportImport)
        self.verticalLayoutExportImport.setObjectName(u"verticalLayoutExportImport")
        self.labelExportImportTitle = QLabel(self.pageExportImport)
        self.labelExportImportTitle.setObjectName(u"labelExportImportTitle")

        self.verticalLayoutExportImport.addWidget(self.labelExportImportTitle)

        self.contentStackedWidget.addWidget(self.pageExportImport)
        self.pageSettings = SettingspageWidget()
        self.pageSettings.setObjectName(u"pageSettings")
        self.verticalLayoutSettings = QVBoxLayout(self.pageSettings)
        self.verticalLayoutSettings.setObjectName(u"verticalLayoutSettings")
        self.contentStackedWidget.addWidget(self.pageSettings)
        self.maineindowspliter.addWidget(self.contentStackedWidget)

        self.verticalLayout.addWidget(self.maineindowspliter)

        mainWindow.setCentralWidget(self.centralWidget)
        self.menuBar = QMenuBar(mainWindow)
        self.menuBar.setObjectName(u"menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 1172, 25))
        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName(u"menuFile")
        self.menuHelp = QMenu(self.menuBar)
        self.menuHelp.setObjectName(u"menuHelp")
        mainWindow.setMenuBar(self.menuBar)
        self.statusBar = QStatusBar(mainWindow)
        self.statusBar.setObjectName(u"statusBar")
        mainWindow.setStatusBar(self.statusBar)

        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuHelp.menuAction())
        self.menuFile.addAction(self.actionOpen)
        self.menuFile.addAction(self.actionSave)
        self.menuFile.addAction(self.actionExit)
        self.menuHelp.addAction(self.actionAbout)

        self.retranslateUi(mainWindow)
        self.sidebarList.currentRowChanged.connect(self.contentStackedWidget.setCurrentIndex)

        self.contentStackedWidget.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(mainWindow)
    # setupUi

    def retranslateUi(self, mainWindow):
        mainWindow.setWindowTitle(QCoreApplication.translate("mainWindow", u"\u753b\u50cf\u51e6\u7406\u30a2\u30d7\u30ea\u30b1\u30fc\u30b7\u30e7\u30f3", None))
        self.actionOpen.setText(QCoreApplication.translate("mainWindow", u"\u958b\u304f", None))
        self.actionSave.setText(QCoreApplication.translate("mainWindow", u"\u4fdd\u5b58", None))
        self.actionExit.setText(QCoreApplication.translate("mainWindow", u"\u7d42\u4e86", None))
        self.actionAbout.setText(QCoreApplication.translate("mainWindow", u"\u3053\u306e\u30a2\u30d7\u30ea\u306b\u3064\u3044\u3066", None))

        __sortingEnabled = self.sidebarList.isSortingEnabled()
        self.sidebarList.setSortingEnabled(False)
        ___qlistwidgetitem = self.sidebarList.item(0)
        ___qlistwidgetitem.setText(QCoreApplication.translate("mainWindow", u"\u753b\u50cf\u7de8\u96c6", None));
        ___qlistwidgetitem1 = self.sidebarList.item(1)
        ___qlistwidgetitem1.setText(QCoreApplication.translate("mainWindow", u"\u81ea\u52d5\u30bf\u30b0\u4ed8\u3051", None));
        ___qlistwidgetitem2 = self.sidebarList.item(2)
        ___qlistwidgetitem2.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u7de8\u96c6", None));
        ___qlistwidgetitem3 = self.sidebarList.item(3)
        ___qlistwidgetitem3.setText(QCoreApplication.translate("mainWindow", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u6982\u8981", None));
        ___qlistwidgetitem4 = self.sidebarList.item(4)
        ___qlistwidgetitem4.setText(QCoreApplication.translate("mainWindow", u"\u30d0\u30c3\u30c1\u51e6\u7406", None));
        ___qlistwidgetitem5 = self.sidebarList.item(5)
        ___qlistwidgetitem5.setText(QCoreApplication.translate("mainWindow", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8/\u30a4\u30f3\u30dd\u30fc\u30c8", None));
        ___qlistwidgetitem6 = self.sidebarList.item(6)
        ___qlistwidgetitem6.setText(QCoreApplication.translate("mainWindow", u"\u8a2d\u5b9a", None));
        ___qlistwidgetitem7 = self.sidebarList.item(7)
        ___qlistwidgetitem7.setText(QCoreApplication.translate("mainWindow", u"\u30d8\u30eb\u30d7", None));
        self.sidebarList.setSortingEnabled(__sortingEnabled)

        self.labelAutoTagTitle.setText(QCoreApplication.translate("mainWindow", u"\u81ea\u52d5\u30bf\u30b0\u4ed8\u3051", None))
        ___qtablewidgetitem = self.tableWidgetAutoTagImages.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("mainWindow", u"\u30b5\u30e0\u30cd\u30a4\u30eb", None));
        ___qtablewidgetitem1 = self.tableWidgetAutoTagImages.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("mainWindow", u"\u30d5\u30a1\u30a4\u30eb\u540d", None));
        ___qtablewidgetitem2 = self.tableWidgetAutoTagImages.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("mainWindow", u"\u65e2\u5b58\u30bf\u30b0", None));
        ___qtablewidgetitem3 = self.tableWidgetAutoTagImages.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0\u4ed8\u3051\u72b6\u6cc1", None));
        self.labelAutoTagPreview.setText(QCoreApplication.translate("mainWindow", u"\u30d7\u30ec\u30d3\u30e5\u30fc", None))
        self.groupBoxTagOptions.setTitle(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0\u751f\u6210\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.labelModel.setText(QCoreApplication.translate("mainWindow", u"\u4f7f\u7528\u30e2\u30c7\u30eb:", None))
        self.comboBoxModel.setItemText(0, QCoreApplication.translate("mainWindow", u"OpenAI", None))
        self.comboBoxModel.setItemText(1, QCoreApplication.translate("mainWindow", u"Google Vision AI", None))
        self.comboBoxModel.setItemText(2, QCoreApplication.translate("mainWindow", u"Anthropic", None))

        self.labelModelName.setText(QCoreApplication.translate("mainWindow", u"\u30e2\u30c7\u30eb\u540d", None))
        self.pushButtonGenerateTags.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0\u751f\u6210", None))
        self.groupBoxGeneratedTags.setTitle(QCoreApplication.translate("mainWindow", u"\u751f\u6210\u3055\u308c\u305f\u30bf\u30b0", None))
        self.labelGeneratedTags.setText(QCoreApplication.translate("mainWindow", u"\u751f\u6210\u3055\u308c\u305f\u30bf\u30b0", None))
        self.pushButtonEditTags.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0\u7de8\u96c6", None))
        self.pushButtonApplyTags.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0\u9069\u7528", None))
        self.labelTagCaptionEditTitle.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u7de8\u96c6", None))
        self.DatasetOverview.setWindowTitle(QCoreApplication.translate("mainWindow", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u6982\u8981", None))
        self.labelBatchProcessingTitle.setText(QCoreApplication.translate("mainWindow", u"\u30d0\u30c3\u30c1\u51e6\u7406", None))
        self.labelExportImportTitle.setText(QCoreApplication.translate("mainWindow", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8/\u30a4\u30f3\u30dd\u30fc\u30c8", None))
        self.menuFile.setTitle(QCoreApplication.translate("mainWindow", u"\u30d5\u30a1\u30a4\u30eb", None))
        self.menuHelp.setTitle(QCoreApplication.translate("mainWindow", u"\u30d8\u30eb\u30d7", None))
    # retranslateUi

