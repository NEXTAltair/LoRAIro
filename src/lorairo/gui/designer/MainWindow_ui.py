# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'MainWindow.ui'
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
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow: QWidget) -> None:
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1287, 1178)
        icon = QIcon()
        icon.addFile(".", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
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
        self.tabWidgetMainMode = QTabWidget(self.centralwidget)
        self.tabWidgetMainMode.setObjectName("tabWidgetMainMode")
        self.tabWorkspace = QWidget()
        self.tabWorkspace.setObjectName("tabWorkspace")
        self.verticalLayout_workspace = QVBoxLayout(self.tabWorkspace)
        self.verticalLayout_workspace.setSpacing(0)
        self.verticalLayout_workspace.setObjectName("verticalLayout_workspace")
        self.verticalLayout_workspace.setContentsMargins(0, 0, 0, 0)
        self.tabWidgetMainMode.addTab(self.tabWorkspace, "")
        self.tabMap = QWidget()
        self.tabMap.setObjectName("tabMap")
        self.verticalLayout_map = QVBoxLayout(self.tabMap)
        self.verticalLayout_map.setObjectName("verticalLayout_map")
        self.labelMapStub = QLabel(self.tabMap)
        self.labelMapStub.setObjectName("labelMapStub")
        self.labelMapStub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelMapStub.setWordWrap(True)

        self.verticalLayout_map.addWidget(self.labelMapStub)

        self.tabWidgetMainMode.addTab(self.tabMap, "")
        self.tabBatchTag = QWidget()
        self.tabBatchTag.setObjectName("tabBatchTag")
        self.verticalLayout_batchTag = QVBoxLayout(self.tabBatchTag)
        self.verticalLayout_batchTag.setSpacing(0)
        self.verticalLayout_batchTag.setObjectName("verticalLayout_batchTag")
        self.verticalLayout_batchTag.setContentsMargins(0, 0, 0, 0)
        self.tabWidgetMainMode.addTab(self.tabBatchTag, "")
        self.tabResults = QWidget()
        self.tabResults.setObjectName("tabResults")
        self.verticalLayout_results = QVBoxLayout(self.tabResults)
        self.verticalLayout_results.setObjectName("verticalLayout_results")
        self.labelResultsStub = QLabel(self.tabResults)
        self.labelResultsStub.setObjectName("labelResultsStub")
        self.labelResultsStub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelResultsStub.setWordWrap(True)

        self.verticalLayout_results.addWidget(self.labelResultsStub)

        self.tabWidgetMainMode.addTab(self.tabResults, "")
        self.tabErrors = QWidget()
        self.tabErrors.setObjectName("tabErrors")
        self.verticalLayout_errors = QVBoxLayout(self.tabErrors)
        self.verticalLayout_errors.setObjectName("verticalLayout_errors")
        self.tabWidgetMainMode.addTab(self.tabErrors, "")
        self.tabExport = QWidget()
        self.tabExport.setObjectName("tabExport")
        self.verticalLayout_export = QVBoxLayout(self.tabExport)
        self.verticalLayout_export.setObjectName("verticalLayout_export")
        self.tabWidgetMainMode.addTab(self.tabExport, "")

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
        self.menuFile.addAction(self.actionExit)
        self.menuEdit.addAction(self.actionSelectAll)
        self.menuEdit.addAction(self.actionDeselectAll)
        self.menuView.addAction(self.actionToggleFilterPanel)
        self.menuView.addAction(self.actionTogglePreviewPanel)
        self.menuTools.addAction(self.actionSettings)
        self.menuHelp.addAction(self.actionAbout)

        self.retranslateUi(MainWindow)

        self.tabWidgetMainMode.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(MainWindow)

    # setupUi

    def retranslateUi(self, MainWindow: QWidget) -> None:
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", "LoRAIro", None))
        self.actionExit.setText(QCoreApplication.translate("MainWindow", "\u7d42\u4e86", None))
        # if QT_CONFIG(shortcut)
        self.actionExit.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+Q", None))
        # endif // QT_CONFIG(shortcut)
        self.actionSelectAll.setText(
            QCoreApplication.translate("MainWindow", "\u3059\u3079\u3066\u9078\u629e", None)
        )
        # if QT_CONFIG(shortcut)
        self.actionSelectAll.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+A", None))
        # endif // QT_CONFIG(shortcut)
        self.actionDeselectAll.setText(
            QCoreApplication.translate("MainWindow", "\u9078\u629e\u89e3\u9664", None)
        )
        # if QT_CONFIG(shortcut)
        self.actionDeselectAll.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+D", None))
        # endif // QT_CONFIG(shortcut)
        self.actionToggleFilterPanel.setText(
            QCoreApplication.translate(
                "MainWindow",
                "\u30d5\u30a3\u30eb\u30bf\u30fc\u30d1\u30cd\u30eb\u8868\u793a\u5207\u66ff",
                None,
            )
        )
        self.actionTogglePreviewPanel.setText(
            QCoreApplication.translate(
                "MainWindow",
                "\u30d7\u30ec\u30d3\u30e5\u30fc\u30d1\u30cd\u30eb\u8868\u793a\u5207\u66ff",
                None,
            )
        )
        self.actionSettings.setText(QCoreApplication.translate("MainWindow", "\u8a2d\u5b9a", None))
        # if QT_CONFIG(shortcut)
        self.actionSettings.setShortcut(QCoreApplication.translate("MainWindow", "Ctrl+,", None))
        # endif // QT_CONFIG(shortcut)
        self.actionAbout.setText(
            QCoreApplication.translate("MainWindow", "LoRAIro\u306b\u3064\u3044\u3066", None)
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabWorkspace),
            QCoreApplication.translate("MainWindow", "\u691c\u7d22", None),
        )
        self.labelMapStub.setText(
            QCoreApplication.translate(
                "MainWindow",
                "\u30de\u30c3\u30d7\u30d3\u30e5\u30fc\u306f\u672a\u5b9f\u88c5\u3067\u3059\u3002\n"
                "embedding \u6563\u5e03\u56f3\u306b\u3088\u308b\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u4fef\u77b0\u3092\u4e88\u5b9a\uff08Wireframes v11 \u00b7 Map / \u5b9f\u88c5\u30ed\u30fc\u30c9\u30de\u30c3\u30d7 Phase 8\uff09\u3002",
                None,
            )
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabMap),
            QCoreApplication.translate("MainWindow", "\u30de\u30c3\u30d7", None),
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabBatchTag),
            QCoreApplication.translate("MainWindow", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None),
        )
        self.labelResultsStub.setText(
            QCoreApplication.translate(
                "MainWindow",
                "\u7d50\u679c\u30d3\u30e5\u30fc\u306f\u672a\u5b9f\u88c5\u3067\u3059\u3002\n"
                "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u54c1\u8cea\u30c8\u30ea\u30a2\u30fc\u30b8\uff08issue \u96c6\u7d04 + accept/edit/reject\uff09\u3092\u4e88\u5b9a\uff08Wireframes v11 \u00b7 Frame 5 / \u5b9f\u88c5\u30ed\u30fc\u30c9\u30de\u30c3\u30d7 Phase 2\uff09\u3002",
                None,
            )
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabResults),
            QCoreApplication.translate("MainWindow", "\u7d50\u679c", None),
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabErrors),
            QCoreApplication.translate("MainWindow", "\u30a8\u30e9\u30fc", None),
        )
        self.tabWidgetMainMode.setTabText(
            self.tabWidgetMainMode.indexOf(self.tabExport),
            QCoreApplication.translate("MainWindow", "\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None),
        )
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", "\u30d5\u30a1\u30a4\u30eb", None))
        self.menuEdit.setTitle(QCoreApplication.translate("MainWindow", "\u7de8\u96c6", None))
        self.menuView.setTitle(QCoreApplication.translate("MainWindow", "\u8868\u793a", None))
        self.menuTools.setTitle(QCoreApplication.translate("MainWindow", "\u30c4\u30fc\u30eb", None))
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", "\u30d8\u30eb\u30d7", None))

    # retranslateUi
