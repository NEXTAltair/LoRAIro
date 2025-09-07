# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'AnnotationResultsWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHeaderView, QLabel,
    QSizePolicy, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_AnnotationResultsWidget(object):
    def setupUi(self, AnnotationResultsWidget):
        if not AnnotationResultsWidget.objectName():
            AnnotationResultsWidget.setObjectName(u"AnnotationResultsWidget")
        AnnotationResultsWidget.resize(400, 400)
        self.verticalLayoutMain = QVBoxLayout(AnnotationResultsWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(9, 9, 9, 9)
        self.labelResultsTitle = QLabel(AnnotationResultsWidget)
        self.labelResultsTitle.setObjectName(u"labelResultsTitle")
        font = QFont()
        font.setBold(True)
        self.labelResultsTitle.setFont(font)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelResultsTitle.sizePolicy().hasHeightForWidth())
        self.labelResultsTitle.setSizePolicy(sizePolicy)

        self.verticalLayoutMain.addWidget(self.labelResultsTitle)

        self.tabWidgetResults = QTabWidget(AnnotationResultsWidget)
        self.tabWidgetResults.setObjectName(u"tabWidgetResults")
        self.tabCaption = QWidget()
        self.tabCaption.setObjectName(u"tabCaption")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.tabCaption.sizePolicy().hasHeightForWidth())
        self.tabCaption.setSizePolicy(sizePolicy1)
        self.verticalLayoutCaption = QVBoxLayout(self.tabCaption)
        self.verticalLayoutCaption.setObjectName(u"verticalLayoutCaption")
        self.tableWidgetCaption = QTableWidget(self.tabCaption)
        if (self.tableWidgetCaption.columnCount() < 2):
            self.tableWidgetCaption.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetCaption.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetCaption.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.tableWidgetCaption.setObjectName(u"tableWidgetCaption")
        self.tableWidgetCaption.setAlternatingRowColors(True)
        self.tableWidgetCaption.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetCaption.setSortingEnabled(True)
        self.tableWidgetCaption.setColumnCount(2)
        self.tableWidgetCaption.horizontalHeader().setVisible(True)
        self.tableWidgetCaption.verticalHeader().setVisible(False)

        self.verticalLayoutCaption.addWidget(self.tableWidgetCaption)

        self.tabWidgetResults.addTab(self.tabCaption, "")
        self.tabTags = QWidget()
        self.tabTags.setObjectName(u"tabTags")
        sizePolicy1.setHeightForWidth(self.tabTags.sizePolicy().hasHeightForWidth())
        self.tabTags.setSizePolicy(sizePolicy1)
        self.verticalLayoutTags = QVBoxLayout(self.tabTags)
        self.verticalLayoutTags.setObjectName(u"verticalLayoutTags")
        self.tableWidgetTags = QTableWidget(self.tabTags)
        if (self.tableWidgetTags.columnCount() < 2):
            self.tableWidgetTags.setColumnCount(2)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(0, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetTags.setHorizontalHeaderItem(1, __qtablewidgetitem3)
        self.tableWidgetTags.setObjectName(u"tableWidgetTags")
        self.tableWidgetTags.setAlternatingRowColors(True)
        self.tableWidgetTags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetTags.setSortingEnabled(True)
        self.tableWidgetTags.setColumnCount(2)
        self.tableWidgetTags.horizontalHeader().setVisible(True)
        self.tableWidgetTags.verticalHeader().setVisible(False)

        self.verticalLayoutTags.addWidget(self.tableWidgetTags)

        self.tabWidgetResults.addTab(self.tabTags, "")
        self.tabScores = QWidget()
        self.tabScores.setObjectName(u"tabScores")
        sizePolicy1.setHeightForWidth(self.tabScores.sizePolicy().hasHeightForWidth())
        self.tabScores.setSizePolicy(sizePolicy1)
        self.verticalLayoutScores = QVBoxLayout(self.tabScores)
        self.verticalLayoutScores.setObjectName(u"verticalLayoutScores")
        self.tableWidgetScores = QTableWidget(self.tabScores)
        if (self.tableWidgetScores.columnCount() < 3):
            self.tableWidgetScores.setColumnCount(3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidgetScores.setHorizontalHeaderItem(0, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidgetScores.setHorizontalHeaderItem(1, __qtablewidgetitem5)
        __qtablewidgetitem6 = QTableWidgetItem()
        self.tableWidgetScores.setHorizontalHeaderItem(2, __qtablewidgetitem6)
        self.tableWidgetScores.setObjectName(u"tableWidgetScores")
        self.tableWidgetScores.setAlternatingRowColors(True)
        self.tableWidgetScores.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetScores.setSortingEnabled(True)
        self.tableWidgetScores.setColumnCount(3)
        self.tableWidgetScores.horizontalHeader().setVisible(True)
        self.tableWidgetScores.verticalHeader().setVisible(False)

        self.verticalLayoutScores.addWidget(self.tableWidgetScores)

        self.tabWidgetResults.addTab(self.tabScores, "")

        self.verticalLayoutMain.addWidget(self.tabWidgetResults)


        self.retranslateUi(AnnotationResultsWidget)

        self.tabWidgetResults.setCurrentIndex(2)


        QMetaObject.connectSlotsByName(AnnotationResultsWidget)
    # setupUi

    def retranslateUi(self, AnnotationResultsWidget):
        AnnotationResultsWidget.setWindowTitle(QCoreApplication.translate("AnnotationResultsWidget", u"Annotation Results", None))
        self.labelResultsTitle.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u7d50\u679c", None))
        ___qtablewidgetitem = self.tableWidgetCaption.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30e2\u30c7\u30eb\u540d", None));
        ___qtablewidgetitem1 = self.tableWidgetCaption.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None));
        self.tabWidgetResults.setTabText(self.tabWidgetResults.indexOf(self.tabCaption), QCoreApplication.translate("AnnotationResultsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        ___qtablewidgetitem2 = self.tableWidgetTags.horizontalHeaderItem(0)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30e2\u30c7\u30eb\u540d", None));
        ___qtablewidgetitem3 = self.tableWidgetTags.horizontalHeaderItem(1)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30bf\u30b0", None));
        self.tabWidgetResults.setTabText(self.tabWidgetResults.indexOf(self.tabTags), QCoreApplication.translate("AnnotationResultsWidget", u"\u30bf\u30b0", None))
        ___qtablewidgetitem4 = self.tableWidgetScores.horizontalHeaderItem(0)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30e2\u30c7\u30eb\u540d", None));
        ___qtablewidgetitem5 = self.tableWidgetScores.horizontalHeaderItem(1)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30b9\u30b3\u30a2\u5024", None));
        ___qtablewidgetitem6 = self.tableWidgetScores.horizontalHeaderItem(2)
        ___qtablewidgetitem6.setText(QCoreApplication.translate("AnnotationResultsWidget", u"\u30b9\u30b3\u30a2\u30bf\u30a4\u30d7", None));
        self.tabWidgetResults.setTabText(self.tabWidgetResults.indexOf(self.tabScores), QCoreApplication.translate("AnnotationResultsWidget", u"\u30b9\u30b3\u30a2", None))
    # retranslateUi

