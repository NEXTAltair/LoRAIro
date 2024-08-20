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
from PySide6.QtWidgets import (QApplication, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMenuBar, QSizePolicy,
    QSplitter, QStackedWidget, QStatusBar, QVBoxLayout,
    QWidget)

from DatasetExportWidget import DatasetExportWidget
from DatasetOverviewWidget import DatasetOverviewWidget
from DirectoryPickerWidget import DirectoryPickerWidget
from ImageEditWidget import ImageEditWidget
from ImageTaggerWidget import ImageTaggerWidget
from SettingspageWidget import SettingspageWidget

class Ui_mainWindow(object):
    def setupUi(self, mainWindow):
        if not mainWindow.objectName():
            mainWindow.setObjectName(u"mainWindow")
        mainWindow.resize(802, 565)
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

        self.mainWindowSplitter = QSplitter(self.centralWidget)
        self.mainWindowSplitter.setObjectName(u"mainWindowSplitter")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(2)
        sizePolicy1.setHeightForWidth(self.mainWindowSplitter.sizePolicy().hasHeightForWidth())
        self.mainWindowSplitter.setSizePolicy(sizePolicy1)
        self.mainWindowSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.sidebarList = QListWidget(self.mainWindowSplitter)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        QListWidgetItem(self.sidebarList)
        self.sidebarList.setObjectName(u"sidebarList")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.sidebarList.sizePolicy().hasHeightForWidth())
        self.sidebarList.setSizePolicy(sizePolicy2)
        self.sidebarList.setMaximumSize(QSize(512, 16777215))
        self.mainWindowSplitter.addWidget(self.sidebarList)
        self.contentStackedWidget = QStackedWidget(self.mainWindowSplitter)
        self.contentStackedWidget.setObjectName(u"contentStackedWidget")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(2)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.contentStackedWidget.sizePolicy().hasHeightForWidth())
        self.contentStackedWidget.setSizePolicy(sizePolicy3)
        self.pageImageEdit = ImageEditWidget()
        self.pageImageEdit.setObjectName(u"pageImageEdit")
        sizePolicy.setHeightForWidth(self.pageImageEdit.sizePolicy().hasHeightForWidth())
        self.pageImageEdit.setSizePolicy(sizePolicy)
        self.verticalLayoutImageEdit = QVBoxLayout(self.pageImageEdit)
        self.verticalLayoutImageEdit.setObjectName(u"verticalLayoutImageEdit")
        self.contentStackedWidget.addWidget(self.pageImageEdit)
        self.pageImageTagger = ImageTaggerWidget()
        self.pageImageTagger.setObjectName(u"pageImageTagger")
        sizePolicy.setHeightForWidth(self.pageImageTagger.sizePolicy().hasHeightForWidth())
        self.pageImageTagger.setSizePolicy(sizePolicy)
        self.contentStackedWidget.addWidget(self.pageImageTagger)
        self.pageDatasetOverview = DatasetOverviewWidget()
        self.pageDatasetOverview.setObjectName(u"pageDatasetOverview")
        sizePolicy.setHeightForWidth(self.pageDatasetOverview.sizePolicy().hasHeightForWidth())
        self.pageDatasetOverview.setSizePolicy(sizePolicy)
        self.contentStackedWidget.addWidget(self.pageDatasetOverview)
        self.pageTagCaptionEdit = QWidget()
        self.pageTagCaptionEdit.setObjectName(u"pageTagCaptionEdit")
        sizePolicy.setHeightForWidth(self.pageTagCaptionEdit.sizePolicy().hasHeightForWidth())
        self.pageTagCaptionEdit.setSizePolicy(sizePolicy)
        self.verticalLayoutTagCaptionEdit = QVBoxLayout(self.pageTagCaptionEdit)
        self.verticalLayoutTagCaptionEdit.setObjectName(u"verticalLayoutTagCaptionEdit")
        self.labelTagCaptionEditTitle = QLabel(self.pageTagCaptionEdit)
        self.labelTagCaptionEditTitle.setObjectName(u"labelTagCaptionEditTitle")

        self.verticalLayoutTagCaptionEdit.addWidget(self.labelTagCaptionEditTitle)

        self.contentStackedWidget.addWidget(self.pageTagCaptionEdit)
        self.pageExport = DatasetExportWidget()
        self.pageExport.setObjectName(u"pageExport")
        sizePolicy.setHeightForWidth(self.pageExport.sizePolicy().hasHeightForWidth())
        self.pageExport.setSizePolicy(sizePolicy)
        self.verticalLayoutBatchProcessing = QVBoxLayout(self.pageExport)
        self.verticalLayoutBatchProcessing.setObjectName(u"verticalLayoutBatchProcessing")
        self.contentStackedWidget.addWidget(self.pageExport)
        self.pageSettings = SettingspageWidget()
        self.pageSettings.setObjectName(u"pageSettings")
        sizePolicy.setHeightForWidth(self.pageSettings.sizePolicy().hasHeightForWidth())
        self.pageSettings.setSizePolicy(sizePolicy)
        self.verticalLayoutSettings = QVBoxLayout(self.pageSettings)
        self.verticalLayoutSettings.setObjectName(u"verticalLayoutSettings")
        self.contentStackedWidget.addWidget(self.pageSettings)
        self.mainWindowSplitter.addWidget(self.contentStackedWidget)

        self.verticalLayout.addWidget(self.mainWindowSplitter)

        mainWindow.setCentralWidget(self.centralWidget)
        self.menuBar = QMenuBar(mainWindow)
        self.menuBar.setObjectName(u"menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 802, 21))
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

        self.contentStackedWidget.setCurrentIndex(4)


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
        ___qlistwidgetitem2.setText(QCoreApplication.translate("mainWindow", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u6982\u8981", None));
        ___qlistwidgetitem3 = self.sidebarList.item(3)
        ___qlistwidgetitem3.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u7de8\u96c6", None));
        ___qlistwidgetitem4 = self.sidebarList.item(4)
        ___qlistwidgetitem4.setText(QCoreApplication.translate("mainWindow", u"\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None));
        ___qlistwidgetitem5 = self.sidebarList.item(5)
        ___qlistwidgetitem5.setText(QCoreApplication.translate("mainWindow", u"\u30d0\u30c3\u30c1\u51e6\u7406", None));
        ___qlistwidgetitem6 = self.sidebarList.item(6)
        ___qlistwidgetitem6.setText(QCoreApplication.translate("mainWindow", u"\u8a2d\u5b9a", None));
        self.sidebarList.setSortingEnabled(__sortingEnabled)

        self.pageDatasetOverview.setWindowTitle(QCoreApplication.translate("mainWindow", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u6982\u8981", None))
        self.labelTagCaptionEditTitle.setText(QCoreApplication.translate("mainWindow", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u7de8\u96c6", None))
        self.menuFile.setTitle(QCoreApplication.translate("mainWindow", u"\u30d5\u30a1\u30a4\u30eb", None))
        self.menuHelp.setTitle(QCoreApplication.translate("mainWindow", u"\u30d8\u30eb\u30d7", None))
    # retranslateUi

