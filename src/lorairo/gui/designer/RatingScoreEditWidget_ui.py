# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'RatingScoreEditWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSlider, QSpacerItem, QVBoxLayout, QWidget)

class Ui_RatingScoreEditWidget(object):
    def setupUi(self, RatingScoreEditWidget: QWidget) -> None:
        if not RatingScoreEditWidget.objectName():
            RatingScoreEditWidget.setObjectName(u"RatingScoreEditWidget")
        RatingScoreEditWidget.resize(250, 200)
        self.verticalLayoutMain = QVBoxLayout(RatingScoreEditWidget)
        self.verticalLayoutMain.setSpacing(8)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(8, 8, 8, 8)
        self.groupBoxRatingScore = QGroupBox(RatingScoreEditWidget)
        self.groupBoxRatingScore.setObjectName(u"groupBoxRatingScore")
        self.gridLayoutRatingScore = QGridLayout(self.groupBoxRatingScore)
        self.gridLayoutRatingScore.setSpacing(6)
        self.gridLayoutRatingScore.setObjectName(u"gridLayoutRatingScore")
        self.labelRating = QLabel(self.groupBoxRatingScore)
        self.labelRating.setObjectName(u"labelRating")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelRating.sizePolicy().hasHeightForWidth())
        self.labelRating.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelRating, 0, 0, 1, 1)

        self.comboBoxRating = QComboBox(self.groupBoxRatingScore)
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.setObjectName(u"comboBoxRating")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.comboBoxRating.sizePolicy().hasHeightForWidth())
        self.comboBoxRating.setSizePolicy(sizePolicy1)

        self.gridLayoutRatingScore.addWidget(self.comboBoxRating, 0, 1, 1, 1)

        self.labelScore = QLabel(self.groupBoxRatingScore)
        self.labelScore.setObjectName(u"labelScore")
        sizePolicy.setHeightForWidth(self.labelScore.sizePolicy().hasHeightForWidth())
        self.labelScore.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelScore, 1, 0, 1, 1)

        self.horizontalLayoutScore = QHBoxLayout()
        self.horizontalLayoutScore.setSpacing(8)
        self.horizontalLayoutScore.setObjectName(u"horizontalLayoutScore")
        self.sliderScore = QSlider(self.groupBoxRatingScore)
        self.sliderScore.setObjectName(u"sliderScore")
        self.sliderScore.setMinimum(0)
        self.sliderScore.setMaximum(1000)
        self.sliderScore.setValue(500)
        self.sliderScore.setOrientation(Qt.Orientation.Horizontal)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.sliderScore.sizePolicy().hasHeightForWidth())
        self.sliderScore.setSizePolicy(sizePolicy2)

        self.horizontalLayoutScore.addWidget(self.sliderScore)

        self.labelScoreValue = QLabel(self.groupBoxRatingScore)
        self.labelScoreValue.setObjectName(u"labelScoreValue")
        self.labelScoreValue.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.labelScoreValue.setMinimumWidth(40)
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.labelScoreValue.sizePolicy().hasHeightForWidth())
        self.labelScoreValue.setSizePolicy(sizePolicy3)

        self.horizontalLayoutScore.addWidget(self.labelScoreValue)


        self.gridLayoutRatingScore.addLayout(self.horizontalLayoutScore, 1, 1, 1, 1)


        self.verticalLayoutMain.addWidget(self.groupBoxRatingScore)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacer)

        self.pushButtonSave = QPushButton(RatingScoreEditWidget)
        self.pushButtonSave.setObjectName(u"pushButtonSave")
        self.pushButtonSave.setMinimumWidth(80)
        sizePolicy3.setHeightForWidth(self.pushButtonSave.sizePolicy().hasHeightForWidth())
        self.pushButtonSave.setSizePolicy(sizePolicy3)

        self.horizontalLayoutButtons.addWidget(self.pushButtonSave)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutButtons)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutMain.addItem(self.verticalSpacer)


        self.retranslateUi(RatingScoreEditWidget)
        self.pushButtonSave.clicked.connect(RatingScoreEditWidget._on_save_clicked)

        QMetaObject.connectSlotsByName(RatingScoreEditWidget)
    # setupUi

    def retranslateUi(self, RatingScoreEditWidget: QWidget) -> None:
        RatingScoreEditWidget.setWindowTitle(QCoreApplication.translate("RatingScoreEditWidget", u"Rating/Score Edit", None))
        self.groupBoxRatingScore.setTitle(QCoreApplication.translate("RatingScoreEditWidget", u"\u8a55\u4fa1\u30fb\u30b9\u30b3\u30a2\u7de8\u96c6", None))
        self.labelRating.setText(QCoreApplication.translate("RatingScoreEditWidget", u"Rating:", None))
        self.comboBoxRating.setItemText(0, QCoreApplication.translate("RatingScoreEditWidget", u"PG", None))
        self.comboBoxRating.setItemText(1, QCoreApplication.translate("RatingScoreEditWidget", u"PG-13", None))
        self.comboBoxRating.setItemText(2, QCoreApplication.translate("RatingScoreEditWidget", u"R", None))
        self.comboBoxRating.setItemText(3, QCoreApplication.translate("RatingScoreEditWidget", u"X", None))
        self.comboBoxRating.setItemText(4, QCoreApplication.translate("RatingScoreEditWidget", u"XXX", None))

        self.labelScore.setText(QCoreApplication.translate("RatingScoreEditWidget", u"\u30b9\u30b3\u30a2:", None))
        self.labelScoreValue.setText(QCoreApplication.translate("RatingScoreEditWidget", u"5.00", None))
        self.pushButtonSave.setText(QCoreApplication.translate("RatingScoreEditWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

