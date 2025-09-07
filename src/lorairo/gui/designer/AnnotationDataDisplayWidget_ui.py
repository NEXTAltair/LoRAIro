# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'AnnotationDataDisplayWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QGroupBox, QLabel,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

class Ui_AnnotationDataDisplayWidget(object):
    def setupUi(self, AnnotationDataDisplayWidget):
        if not AnnotationDataDisplayWidget.objectName():
            AnnotationDataDisplayWidget.setObjectName(u"AnnotationDataDisplayWidget")
        AnnotationDataDisplayWidget.resize(400, 600)
        self.verticalLayoutMain = QVBoxLayout(AnnotationDataDisplayWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(9, 9, 9, 9)
        self.groupBoxTags = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxTags.setObjectName(u"groupBoxTags")
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName(u"verticalLayoutTags")
        self.textEditTags = QTextEdit(self.groupBoxTags)
        self.textEditTags.setObjectName(u"textEditTags")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(2)
        sizePolicy.setHeightForWidth(self.textEditTags.sizePolicy().hasHeightForWidth())
        self.textEditTags.setSizePolicy(sizePolicy)

        self.verticalLayoutTags.addWidget(self.textEditTags)


        self.verticalLayoutMain.addWidget(self.groupBoxTags)

        self.groupBoxCaption = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxCaption.setObjectName(u"groupBoxCaption")
        self.verticalLayoutCaption = QVBoxLayout(self.groupBoxCaption)
        self.verticalLayoutCaption.setObjectName(u"verticalLayoutCaption")
        self.textEditCaption = QTextEdit(self.groupBoxCaption)
        self.textEditCaption.setObjectName(u"textEditCaption")
        sizePolicy.setHeightForWidth(self.textEditCaption.sizePolicy().hasHeightForWidth())
        self.textEditCaption.setSizePolicy(sizePolicy)

        self.verticalLayoutCaption.addWidget(self.textEditCaption)


        self.verticalLayoutMain.addWidget(self.groupBoxCaption)

        self.groupBoxScores = QGroupBox(AnnotationDataDisplayWidget)
        self.groupBoxScores.setObjectName(u"groupBoxScores")
        self.gridLayoutScores = QGridLayout(self.groupBoxScores)
        self.gridLayoutScores.setObjectName(u"gridLayoutScores")
        self.labelScoreType = QLabel(self.groupBoxScores)
        self.labelScoreType.setObjectName(u"labelScoreType")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelScoreType.sizePolicy().hasHeightForWidth())
        self.labelScoreType.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelScoreType, 0, 0, 1, 1)

        self.labelScoreTypeValue = QLabel(self.groupBoxScores)
        self.labelScoreTypeValue.setObjectName(u"labelScoreTypeValue")
        self.labelScoreTypeValue.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        sizePolicy1.setHeightForWidth(self.labelScoreTypeValue.sizePolicy().hasHeightForWidth())
        self.labelScoreTypeValue.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelScoreTypeValue, 0, 1, 1, 1)

        self.labelOverallScore = QLabel(self.groupBoxScores)
        self.labelOverallScore.setObjectName(u"labelOverallScore")
        sizePolicy1.setHeightForWidth(self.labelOverallScore.sizePolicy().hasHeightForWidth())
        self.labelOverallScore.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelOverallScore, 1, 0, 1, 1)

        self.labelOverallValue = QLabel(self.groupBoxScores)
        self.labelOverallValue.setObjectName(u"labelOverallValue")
        self.labelOverallValue.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        sizePolicy1.setHeightForWidth(self.labelOverallValue.sizePolicy().hasHeightForWidth())
        self.labelOverallValue.setSizePolicy(sizePolicy1)

        self.gridLayoutScores.addWidget(self.labelOverallValue, 1, 1, 1, 1)


        self.verticalLayoutMain.addWidget(self.groupBoxScores)


        self.retranslateUi(AnnotationDataDisplayWidget)

        QMetaObject.connectSlotsByName(AnnotationDataDisplayWidget)
    # setupUi

    def retranslateUi(self, AnnotationDataDisplayWidget):
        AnnotationDataDisplayWidget.setWindowTitle(QCoreApplication.translate("AnnotationDataDisplayWidget", u"Annotation Data Display", None))
        self.groupBoxTags.setTitle(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u30bf\u30b0", None))
        self.textEditTags.setPlaceholderText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u30bf\u30b0\u304c\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.groupBoxCaption.setTitle(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.textEditCaption.setPlaceholderText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.groupBoxScores.setTitle(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u54c1\u8cea\u30b9\u30b3\u30a2", None))
        self.labelScoreType.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"Aesthetic:", None))
        self.labelScoreTypeValue.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"-", None))
        self.labelOverallScore.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"\u30b9\u30b3\u30a2:", None))
        self.labelOverallValue.setText(QCoreApplication.translate("AnnotationDataDisplayWidget", u"0", None))
    # retranslateUi

