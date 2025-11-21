
################################################################################
## Form generated from reading UI file 'ModelSelectionTableWidget.ui'
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
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class Ui_ModelSelectionTableWidget:
    def setupUi(self, ModelSelectionTableWidget):
        if not ModelSelectionTableWidget.objectName():
            ModelSelectionTableWidget.setObjectName("ModelSelectionTableWidget")
        ModelSelectionTableWidget.resize(400, 300)
        self.verticalLayoutMain = QVBoxLayout(ModelSelectionTableWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(0, 0, 0, 0)
        self.tableWidgetModels = QTableWidget(ModelSelectionTableWidget)
        if (self.tableWidgetModels.columnCount() < 4):
            self.tableWidgetModels.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetModels.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetModels.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetModels.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetModels.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        self.tableWidgetModels.setObjectName("tableWidgetModels")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.tableWidgetModels.sizePolicy().hasHeightForWidth())
        self.tableWidgetModels.setSizePolicy(sizePolicy)
        self.tableWidgetModels.setMinimumSize(QSize(0, 150))
        self.tableWidgetModels.setAlternatingRowColors(True)
        self.tableWidgetModels.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetModels.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.tableWidgetModels.setGridStyle(Qt.PenStyle.SolidLine)
        self.tableWidgetModels.setSortingEnabled(True)
        self.tableWidgetModels.setWordWrap(True)
        self.tableWidgetModels.setColumnCount(4)
        self.tableWidgetModels.horizontalHeader().setVisible(True)
        self.tableWidgetModels.horizontalHeader().setCascadingSectionResizes(False)
        self.tableWidgetModels.horizontalHeader().setHighlightSections(False)
        self.tableWidgetModels.horizontalHeader().setProperty("showSortIndicator", True)
        self.tableWidgetModels.horizontalHeader().setStretchLastSection(False)
        self.tableWidgetModels.verticalHeader().setVisible(False)
        self.tableWidgetModels.verticalHeader().setCascadingSectionResizes(False)
        self.tableWidgetModels.verticalHeader().setDefaultSectionSize(24)
        self.tableWidgetModels.verticalHeader().setStretchLastSection(False)

        self.verticalLayoutMain.addWidget(self.tableWidgetModels)


        self.retranslateUi(ModelSelectionTableWidget)

        QMetaObject.connectSlotsByName(ModelSelectionTableWidget)
    # setupUi

    def retranslateUi(self, ModelSelectionTableWidget):
        ModelSelectionTableWidget.setWindowTitle(QCoreApplication.translate("ModelSelectionTableWidget", "Model Selection Table", None))
        ___qtablewidgetitem = self.tableWidgetModels.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("ModelSelectionTableWidget", "\u9078\u629e", None))
        ___qtablewidgetitem1 = self.tableWidgetModels.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("ModelSelectionTableWidget", "\u30e2\u30c7\u30eb\u540d", None))
        ___qtablewidgetitem2 = self.tableWidgetModels.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("ModelSelectionTableWidget", "\u30d7\u30ed\u30d0\u30a4\u30c0\u30fc", None))
        ___qtablewidgetitem3 = self.tableWidgetModels.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("ModelSelectionTableWidget", "\u6a5f\u80fd", None))
        self.tableWidgetModels.setStyleSheet(QCoreApplication.translate("ModelSelectionTableWidget", "QTableWidget {\n"
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
    # retranslateUi

