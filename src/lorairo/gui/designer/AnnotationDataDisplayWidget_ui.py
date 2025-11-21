################################################################################
## Form generated from reading UI file 'AnnotationDataDisplayWidget.ui'
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
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class Ui_AnnotationDataDisplayWidget:
    def setupUi(self, AnnotationDataDisplayWidget):
        if not AnnotationDataDisplayWidget.objectName():
            AnnotationDataDisplayWidget.setObjectName("AnnotationDataDisplayWidget")
        AnnotationDataDisplayWidget.resize(400, 600)
        self.verticalLayoutMain = QVBoxLayout(AnnotationDataDisplayWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(9, 9, 9, 9)
        self.groupBoxTags = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxTags.setObjectName("groupBoxTags")
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName("verticalLayoutTags")
        self.tableWidgetTags = QTableWidget(self.groupBoxTags)
        if self.tableWidgetTags.columnCount() < 5:
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
        self.tableWidgetTags.setObjectName("tableWidgetTags")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(2)
        sizePolicy.setHeightForWidth(self.tableWidgetTags.sizePolicy().hasHeightForWidth())
        self.tableWidgetTags.setSizePolicy(sizePolicy)
        self.tableWidgetTags.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableWidgetTags.setAlternatingRowColors(True)
        self.tableWidgetTags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidgetTags.setSortingEnabled(True)
        self.tableWidgetTags.setColumnCount(5)
        self.tableWidgetTags.horizontalHeader().setStretchLastSection(True)

        self.verticalLayoutTags.addWidget(self.tableWidgetTags)

        self.verticalLayoutMain.addWidget(self.groupBoxTags)

        self.groupBoxCaption = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxCaption.setObjectName("groupBoxCaption")
        self.verticalLayoutCaption = QVBoxLayout(self.groupBoxCaption)
        self.verticalLayoutCaption.setObjectName("verticalLayoutCaption")
        self.textEditCaption = QTextEdit(self.groupBoxCaption)
        self.textEditCaption.setObjectName("textEditCaption")
        sizePolicy.setHeightForWidth(self.textEditCaption.sizePolicy().hasHeightForWidth())
        self.textEditCaption.setSizePolicy(sizePolicy)

        self.verticalLayoutCaption.addWidget(self.textEditCaption)

        self.verticalLayoutMain.addWidget(self.groupBoxCaption)

        self.groupBoxScores = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxScores.setObjectName("groupBoxScores")
        self.gridLayoutScores = QGridLayout(self.groupBoxScores)
        self.gridLayoutScores.setObjectName("gridLayoutScores")
        self.labelScoreType = QLabel(self.groupBoxScores)
        self.labelScoreType.setObjectName("labelScoreType")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelScoreType.sizePolicy().hasHeightForWidth())
        self.labelScoreType.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelScoreType, 0, 0, 1, 1)

        self.labelScoreTypeValue = QLabel(self.groupBoxScores)
        self.labelScoreTypeValue.setObjectName("labelScoreTypeValue")
        self.labelScoreTypeValue.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        sizePolicy1.setHeightForWidth(self.labelScoreTypeValue.sizePolicy().hasHeightForWidth())
        self.labelScoreTypeValue.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelScoreTypeValue, 0, 1, 1, 1)

        self.labelOverallScore = QLabel(self.groupBoxScores)
        self.labelOverallScore.setObjectName("labelOverallScore")
        sizePolicy1.setHeightForWidth(self.labelOverallScore.sizePolicy().hasHeightForWidth())
        self.labelOverallScore.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelOverallScore, 1, 0, 1, 1)

        self.labelOverallValue = QLabel(self.groupBoxScores)
        self.labelOverallValue.setObjectName("labelOverallValue")
        self.labelOverallValue.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        sizePolicy1.setHeightForWidth(self.labelOverallValue.sizePolicy().hasHeightForWidth())
        self.labelOverallValue.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelOverallValue, 1, 1, 1, 1)

        self.verticalLayoutMain.addWidget(self.groupBoxScores)

        self.retranslateUi(AnnotationDataDisplayWidget)

        QMetaObject.connectSlotsByName(AnnotationDataDisplayWidget)

    # setupUi

    def retranslateUi(self, AnnotationDataDisplayWidget):
        AnnotationDataDisplayWidget.setWindowTitle(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Annotation Data Display", None)
        )
        self.groupBoxTags.setTitle(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "\u30bf\u30b0", None)
        )
        ___qtablewidgetitem = self.tableWidgetTags.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", "Tag", None))
        ___qtablewidgetitem1 = self.tableWidgetTags.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Model", None)
        )
        ___qtablewidgetitem2 = self.tableWidgetTags.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Source", None)
        )
        ___qtablewidgetitem3 = self.tableWidgetTags.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Confidence", None)
        )
        ___qtablewidgetitem4 = self.tableWidgetTags.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Edited", None)
        )
        self.groupBoxCaption.setTitle(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None
            )
        )
        self.textEditCaption.setPlaceholderText(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget",
                "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u8868\u793a\u3055\u308c\u307e\u3059",
                None,
            )
        )
        self.textEditCaption.setStyleSheet(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget",
                "QTextEdit {\n"
                "    font-size: 10px;\n"
                "    background-color: palette(base);\n"
                "    border: 1px solid palette(mid);\n"
                "    border-radius: 4px;\n"
                "    padding: 6px;\n"
                "    color: palette(text);\n"
                "}",
                None,
            )
        )
        self.groupBoxScores.setTitle(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget", "\u54c1\u8cea\u30b9\u30b3\u30a2", None
            )
        )
        self.labelScoreType.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "Aesthetic:", None)
        )
        self.labelScoreTypeValue.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "-", None)
        )
        self.labelScoreTypeValue.setStyleSheet(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget",
                "font-size: 10px; font-weight: bold; color: palette(text);",
                None,
            )
        )
        self.labelOverallScore.setText(
            QCoreApplication.translate("AnnotationDataDisplayWidget", "\u30b9\u30b3\u30a2:", None)
        )
        self.labelOverallValue.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", "0", None))
        self.labelOverallValue.setStyleSheet(
            QCoreApplication.translate(
                "AnnotationDataDisplayWidget",
                "font-size: 10px; font-weight: bold; color: palette(text);",
                None,
            )
        )

    # retranslateUi
