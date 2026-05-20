# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ErrorLogViewerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_ErrorLogViewerWidget(object):
    def setupUi(self, ErrorLogViewerWidget: QWidget) -> None:
        if not ErrorLogViewerWidget.objectName():
            ErrorLogViewerWidget.setObjectName(u"ErrorLogViewerWidget")
        ErrorLogViewerWidget.resize(800, 600)
        self.verticalLayoutMain = QVBoxLayout(ErrorLogViewerWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(6, 6, 6, 6)
        self.groupBoxFilters = QGroupBox(ErrorLogViewerWidget)
        self.groupBoxFilters.setObjectName(u"groupBoxFilters")
        self.horizontalLayoutFilters = QHBoxLayout(self.groupBoxFilters)
        self.horizontalLayoutFilters.setObjectName(u"horizontalLayoutFilters")
        self.labelOperationType = QLabel(self.groupBoxFilters)
        self.labelOperationType.setObjectName(u"labelOperationType")

        self.horizontalLayoutFilters.addWidget(self.labelOperationType)

        self.comboOperationType = QComboBox(self.groupBoxFilters)
        self.comboOperationType.addItem("")
        self.comboOperationType.addItem("")
        self.comboOperationType.addItem("")
        self.comboOperationType.addItem("")
        self.comboOperationType.addItem("")
        self.comboOperationType.addItem("")
        self.comboOperationType.setObjectName(u"comboOperationType")

        self.horizontalLayoutFilters.addWidget(self.comboOperationType)

        self.checkBoxShowResolved = QCheckBox(self.groupBoxFilters)
        self.checkBoxShowResolved.setObjectName(u"checkBoxShowResolved")

        self.horizontalLayoutFilters.addWidget(self.checkBoxShowResolved)

        self.buttonRefresh = QPushButton(self.groupBoxFilters)
        self.buttonRefresh.setObjectName(u"buttonRefresh")

        self.horizontalLayoutFilters.addWidget(self.buttonRefresh)

        self.horizontalSpacerFilters = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutFilters.addItem(self.horizontalSpacerFilters)


        self.verticalLayoutMain.addWidget(self.groupBoxFilters)

        self.tableWidgetErrors = QTableWidget(ErrorLogViewerWidget)
        if (self.tableWidgetErrors.columnCount() < 8):
            self.tableWidgetErrors.setColumnCount(8)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(6, __qtablewidgetitem6)
        __qtablewidgetitem7 = QTableWidgetItem()
        self.tableWidgetErrors.setHorizontalHeaderItem(7, __qtablewidgetitem7)
        self.tableWidgetErrors.setObjectName(u"tableWidgetErrors")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.tableWidgetErrors.sizePolicy().hasHeightForWidth())
        self.tableWidgetErrors.setSizePolicy(sizePolicy)
        self.tableWidgetErrors.setAlternatingRowColors(True)
        self.tableWidgetErrors.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableWidgetErrors.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetErrors.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.tableWidgetErrors.setSortingEnabled(True)
        self.tableWidgetErrors.setWordWrap(False)
        self.tableWidgetErrors.setColumnCount(8)
        self.tableWidgetErrors.horizontalHeader().setVisible(True)
        self.tableWidgetErrors.horizontalHeader().setStretchLastSection(True)
        self.tableWidgetErrors.verticalHeader().setVisible(False)
        self.tableWidgetErrors.verticalHeader().setDefaultSectionSize(24)

        self.verticalLayoutMain.addWidget(self.tableWidgetErrors)

        self.horizontalLayoutPagination = QHBoxLayout()
        self.horizontalLayoutPagination.setObjectName(u"horizontalLayoutPagination")
        self.buttonPreviousPage = QPushButton(ErrorLogViewerWidget)
        self.buttonPreviousPage.setObjectName(u"buttonPreviousPage")

        self.horizontalLayoutPagination.addWidget(self.buttonPreviousPage)

        self.labelPageInfo = QLabel(ErrorLogViewerWidget)
        self.labelPageInfo.setObjectName(u"labelPageInfo")
        self.labelPageInfo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.horizontalLayoutPagination.addWidget(self.labelPageInfo)

        self.buttonNextPage = QPushButton(ErrorLogViewerWidget)
        self.buttonNextPage.setObjectName(u"buttonNextPage")

        self.horizontalLayoutPagination.addWidget(self.buttonNextPage)

        self.horizontalSpacerPagination = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutPagination.addItem(self.horizontalSpacerPagination)

        self.labelPageSize = QLabel(ErrorLogViewerWidget)
        self.labelPageSize.setObjectName(u"labelPageSize")

        self.horizontalLayoutPagination.addWidget(self.labelPageSize)

        self.spinBoxPageSize = QSpinBox(ErrorLogViewerWidget)
        self.spinBoxPageSize.setObjectName(u"spinBoxPageSize")
        self.spinBoxPageSize.setMinimum(10)
        self.spinBoxPageSize.setMaximum(500)
        self.spinBoxPageSize.setValue(100)

        self.horizontalLayoutPagination.addWidget(self.spinBoxPageSize)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutPagination)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.buttonViewDetails = QPushButton(ErrorLogViewerWidget)
        self.buttonViewDetails.setObjectName(u"buttonViewDetails")

        self.horizontalLayoutButtons.addWidget(self.buttonViewDetails)

        self.buttonMarkResolved = QPushButton(ErrorLogViewerWidget)
        self.buttonMarkResolved.setObjectName(u"buttonMarkResolved")

        self.horizontalLayoutButtons.addWidget(self.buttonMarkResolved)

        self.buttonExportLog = QPushButton(ErrorLogViewerWidget)
        self.buttonExportLog.setObjectName(u"buttonExportLog")

        self.horizontalLayoutButtons.addWidget(self.buttonExportLog)

        self.horizontalSpacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(ErrorLogViewerWidget)

        QMetaObject.connectSlotsByName(ErrorLogViewerWidget)
    # setupUi

    def retranslateUi(self, ErrorLogViewerWidget: QWidget) -> None:
        ErrorLogViewerWidget.setWindowTitle(QCoreApplication.translate("ErrorLogViewerWidget", u"Error Log Viewer", None))
        self.groupBoxFilters.setTitle(QCoreApplication.translate("ErrorLogViewerWidget", u"\u30d5\u30a3\u30eb\u30bf", None))
        self.labelOperationType.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u64cd\u4f5c\u7a2e\u5225:", None))
        self.comboOperationType.setItemText(0, QCoreApplication.translate("ErrorLogViewerWidget", u"\u5168\u3066", None))
        self.comboOperationType.setItemText(1, QCoreApplication.translate("ErrorLogViewerWidget", u"registration", None))
        self.comboOperationType.setItemText(2, QCoreApplication.translate("ErrorLogViewerWidget", u"annotation", None))
        self.comboOperationType.setItemText(3, QCoreApplication.translate("ErrorLogViewerWidget", u"processing", None))
        self.comboOperationType.setItemText(4, QCoreApplication.translate("ErrorLogViewerWidget", u"search", None))
        self.comboOperationType.setItemText(5, QCoreApplication.translate("ErrorLogViewerWidget", u"thumbnail", None))

        self.checkBoxShowResolved.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u89e3\u6c7a\u6e08\u307f\u3092\u8868\u793a", None))
        self.buttonRefresh.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u66f4\u65b0", None))
        ___qtablewidgetitem = self.tableWidgetErrors.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"ID", None))
        ___qtablewidgetitem1 = self.tableWidgetErrors.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u4f5c\u6210\u65e5\u6642", None))
        ___qtablewidgetitem2 = self.tableWidgetErrors.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u64cd\u4f5c\u7a2e\u5225", None))
        ___qtablewidgetitem3 = self.tableWidgetErrors.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u30a8\u30e9\u30fc\u7a2e\u5225", None))
        ___qtablewidgetitem4 = self.tableWidgetErrors.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u30a8\u30e9\u30fc\u30e1\u30c3\u30bb\u30fc\u30b8", None))
        ___qtablewidgetitem5 = self.tableWidgetErrors.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u753b\u50cf\u30d5\u30a1\u30a4\u30eb\u540d", None))
        ___qtablewidgetitem6 = self.tableWidgetErrors.horizontalHeaderItem(6)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u30e2\u30c7\u30eb\u540d", None))
        ___qtablewidgetitem7 = self.tableWidgetErrors.horizontalHeaderItem(7)
        ___qtablewidgetitem7.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u72b6\u614b", None))
        self.tableWidgetErrors.setStyleSheet(QCoreApplication.translate("ErrorLogViewerWidget", u"QTableWidget {\n"
"    font-size: 9px;\n"
"    gridline-color: #e0e0e0;\n"
"    selection-background-color: #e3f2fd;\n"
"}\n"
"QTableWidget::item {\n"
"    padding: 4px;\n"
"    color: palette(text);\n"
"}\n"
"QHeaderView::section {\n"
"    font-size: 9px;\n"
"    font-weight: bold;\n"
"    background-color: palette(button);\n"
"    color: palette(buttonText);\n"
"    border: 1px solid palette(mid);\n"
"    padding: 4px;\n"
"}", None))
        self.buttonPreviousPage.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"< \u524d\u30da\u30fc\u30b8", None))
        self.labelPageInfo.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"Page 1 / 1", None))
        self.buttonNextPage.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u6b21\u30da\u30fc\u30b8 >", None))
        self.labelPageSize.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u8868\u793a\u4ef6\u6570:", None))
        self.buttonViewDetails.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u8a73\u7d30\u8868\u793a", None))
        self.buttonMarkResolved.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u89e3\u6c7a\u6e08\u307f\u306b\u30de\u30fc\u30af", None))
        self.buttonExportLog.setText(QCoreApplication.translate("ErrorLogViewerWidget", u"\u30ed\u30b0\u3092\u30a8\u30af\u30b9\u30dd\u30fc\u30c8", None))
    # retranslateUi
