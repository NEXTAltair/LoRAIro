# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'StagingWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QGroupBox, QHBoxLayout, QLabel,
    QListView, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_StagingWidget(object):
    def setupUi(self, StagingWidget: QWidget) -> None:
        if not StagingWidget.objectName():
            StagingWidget.setObjectName(u"StagingWidget")
        StagingWidget.resize(250, 400)
        self.verticalLayoutStagingMain = QVBoxLayout(StagingWidget)
        self.verticalLayoutStagingMain.setSpacing(4)
        self.verticalLayoutStagingMain.setObjectName(u"verticalLayoutStagingMain")
        self.verticalLayoutStagingMain.setContentsMargins(0, 0, 0, 0)
        self.groupBoxStagingList = QGroupBox(StagingWidget)
        self.groupBoxStagingList.setObjectName(u"groupBoxStagingList")
        self.verticalLayoutStaging = QVBoxLayout(self.groupBoxStagingList)
        self.verticalLayoutStaging.setObjectName(u"verticalLayoutStaging")
        self.labelStagingCount = QLabel(self.groupBoxStagingList)
        self.labelStagingCount.setObjectName(u"labelStagingCount")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelStagingCount.sizePolicy().hasHeightForWidth())
        self.labelStagingCount.setSizePolicy(sizePolicy)

        self.verticalLayoutStaging.addWidget(self.labelStagingCount)

        self.listWidgetStaging = QListWidget(self.groupBoxStagingList)
        self.listWidgetStaging.setObjectName(u"listWidgetStaging")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.listWidgetStaging.sizePolicy().hasHeightForWidth())
        self.listWidgetStaging.setSizePolicy(sizePolicy1)
        self.listWidgetStaging.setMinimumHeight(150)
        self.listWidgetStaging.setViewMode(QListView.ViewMode.IconMode)
        self.listWidgetStaging.setMovement(QListView.Movement.Static)
        self.listWidgetStaging.setResizeMode(QListView.ResizeMode.Adjust)
        self.listWidgetStaging.setSpacing(6)
        self.listWidgetStaging.setIconSize(QSize(96, 96))
        self.listWidgetStaging.setWordWrap(True)

        self.verticalLayoutStaging.addWidget(self.listWidgetStaging)

        self.horizontalLayoutStagingButtons = QHBoxLayout()
        self.horizontalLayoutStagingButtons.setObjectName(u"horizontalLayoutStagingButtons")
        self.horizontalSpacerStagingButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutStagingButtons.addItem(self.horizontalSpacerStagingButtons)

        self.pushButtonClearStaging = QPushButton(self.groupBoxStagingList)
        self.pushButtonClearStaging.setObjectName(u"pushButtonClearStaging")
        self.pushButtonClearStaging.setMinimumWidth(60)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pushButtonClearStaging.sizePolicy().hasHeightForWidth())
        self.pushButtonClearStaging.setSizePolicy(sizePolicy2)

        self.horizontalLayoutStagingButtons.addWidget(self.pushButtonClearStaging)


        self.verticalLayoutStaging.addLayout(self.horizontalLayoutStagingButtons)


        self.verticalLayoutStagingMain.addWidget(self.groupBoxStagingList)


        self.retranslateUi(StagingWidget)
        self.pushButtonClearStaging.clicked.connect(StagingWidget._on_clear_staging_clicked)

        QMetaObject.connectSlotsByName(StagingWidget)
    # setupUi

    def retranslateUi(self, StagingWidget: QWidget) -> None:
        StagingWidget.setWindowTitle(QCoreApplication.translate("StagingWidget", u"Staging", None))
        self.groupBoxStagingList.setTitle(QCoreApplication.translate("StagingWidget", u"\u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u4e00\u89a7", None))
        self.labelStagingCount.setText(QCoreApplication.translate("StagingWidget", u"0 / 500 \u679a", None))
        self.pushButtonClearStaging.setText(QCoreApplication.translate("StagingWidget", u"\u30af\u30ea\u30a2", None))
    # retranslateUi

