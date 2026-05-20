# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'TagManagementWidget.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSizePolicy, QSpacerItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_TagManagementWidget(object):
    def setupUi(self, TagManagementWidget: QWidget) -> None:
        if not TagManagementWidget.objectName():
            TagManagementWidget.setObjectName(u"TagManagementWidget")
        TagManagementWidget.resize(800, 600)
        self.verticalLayoutMain = QVBoxLayout(TagManagementWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(6, 6, 6, 6)
        self.labelTitle = QLabel(TagManagementWidget)
        self.labelTitle.setObjectName(u"labelTitle")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.labelTitle.setFont(font)

        self.verticalLayoutMain.addWidget(self.labelTitle)

        self.tableWidgetTags = QTableWidget(TagManagementWidget)
        if (self.tableWidgetTags.columnCount() < 5):
            self.tableWidgetTags.setColumnCount(5)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        self.tableWidgetTags.setObjectName(u"tableWidgetTags")
        self.tableWidgetTags.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableWidgetTags.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tableWidgetTags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetTags.setSortingEnabled(False)

        self.verticalLayoutMain.addWidget(self.tableWidgetTags)

        self.horizontalLayoutBottom = QHBoxLayout()
        self.horizontalLayoutBottom.setObjectName(u"horizontalLayoutBottom")
        self.labelStatus = QLabel(TagManagementWidget)
        self.labelStatus.setObjectName(u"labelStatus")

        self.horizontalLayoutBottom.addWidget(self.labelStatus)

        self.horizontalSpacerBottom = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutBottom.addItem(self.horizontalSpacerBottom)

        self.buttonUpdate = QPushButton(TagManagementWidget)
        self.buttonUpdate.setObjectName(u"buttonUpdate")
        self.buttonUpdate.setEnabled(False)

        self.horizontalLayoutBottom.addWidget(self.buttonUpdate)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutBottom)


        self.retranslateUi(TagManagementWidget)

        QMetaObject.connectSlotsByName(TagManagementWidget)
    # setupUi

    def retranslateUi(self, TagManagementWidget: QWidget) -> None:
        TagManagementWidget.setWindowTitle(QCoreApplication.translate("TagManagementWidget", u"Tag Management", None))
        self.labelTitle.setText(QCoreApplication.translate("TagManagementWidget", u"Unknown Type \u30bf\u30b0\u4e00\u89a7", None))
        ___qtablewidgetitem = self.tableWidgetTags.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("TagManagementWidget", u"\u9078\u629e", None))
        ___qtablewidgetitem1 = self.tableWidgetTags.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("TagManagementWidget", u"Tag", None))
        ___qtablewidgetitem2 = self.tableWidgetTags.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("TagManagementWidget", u"Source Tag", None))
        ___qtablewidgetitem3 = self.tableWidgetTags.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("TagManagementWidget", u"Current Type", None))
        ___qtablewidgetitem4 = self.tableWidgetTags.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("TagManagementWidget", u"New Type", None))
        self.labelStatus.setText(QCoreApplication.translate("TagManagementWidget", u"Status: Ready", None))
        self.buttonUpdate.setText(QCoreApplication.translate("TagManagementWidget", u"\u66f4\u65b0\u5b9f\u884c", None))
    # retranslateUi
