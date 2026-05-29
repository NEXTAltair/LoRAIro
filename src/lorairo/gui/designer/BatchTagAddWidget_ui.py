# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'BatchTagAddWidget.ui'
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
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QSplitter, QVBoxLayout, QWidget)

from lorairo.gui.widgets.staging_widget import StagingWidget

class Ui_BatchTagAddWidget(object):
    def setupUi(self, BatchTagAddWidget: QWidget) -> None:
        if not BatchTagAddWidget.objectName():
            BatchTagAddWidget.setObjectName(u"BatchTagAddWidget")
        BatchTagAddWidget.resize(250, 500)
        self.verticalLayoutMain = QVBoxLayout(BatchTagAddWidget)
        self.verticalLayoutMain.setSpacing(8)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(8, 8, 8, 8)
        self.splitterBatchTagStaging = QSplitter(BatchTagAddWidget)
        self.splitterBatchTagStaging.setObjectName(u"splitterBatchTagStaging")
        self.splitterBatchTagStaging.setOrientation(Qt.Orientation.Horizontal)
        self.splitterBatchTagStaging.setChildrenCollapsible(False)
        self.stagingWidget = StagingWidget(self.splitterBatchTagStaging)
        self.stagingWidget.setObjectName(u"stagingWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.stagingWidget.sizePolicy().hasHeightForWidth())
        self.stagingWidget.setSizePolicy(sizePolicy)
        self.splitterBatchTagStaging.addWidget(self.stagingWidget)
        self.groupBoxTagInput = QGroupBox(self.splitterBatchTagStaging)
        self.groupBoxTagInput.setObjectName(u"groupBoxTagInput")
        self.verticalLayoutTag = QVBoxLayout(self.groupBoxTagInput)
        self.verticalLayoutTag.setObjectName(u"verticalLayoutTag")
        self.labelTagInstruction = QLabel(self.groupBoxTagInput)
        self.labelTagInstruction.setObjectName(u"labelTagInstruction")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelTagInstruction.sizePolicy().hasHeightForWidth())
        self.labelTagInstruction.setSizePolicy(sizePolicy1)

        self.verticalLayoutTag.addWidget(self.labelTagInstruction)

        self.lineEditTag = QLineEdit(self.groupBoxTagInput)
        self.lineEditTag.setObjectName(u"lineEditTag")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.lineEditTag.sizePolicy().hasHeightForWidth())
        self.lineEditTag.setSizePolicy(sizePolicy2)

        self.verticalLayoutTag.addWidget(self.lineEditTag)

        self.horizontalLayoutTagButtons = QHBoxLayout()
        self.horizontalLayoutTagButtons.setObjectName(u"horizontalLayoutTagButtons")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutTagButtons.addItem(self.horizontalSpacer)

        self.pushButtonAddTag = QPushButton(self.groupBoxTagInput)
        self.pushButtonAddTag.setObjectName(u"pushButtonAddTag")
        self.pushButtonAddTag.setMinimumWidth(80)
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.pushButtonAddTag.sizePolicy().hasHeightForWidth())
        self.pushButtonAddTag.setSizePolicy(sizePolicy3)

        self.horizontalLayoutTagButtons.addWidget(self.pushButtonAddTag)


        self.verticalLayoutTag.addLayout(self.horizontalLayoutTagButtons)

        self.splitterBatchTagStaging.addWidget(self.groupBoxTagInput)

        self.verticalLayoutMain.addWidget(self.splitterBatchTagStaging)


        self.retranslateUi(BatchTagAddWidget)
        self.pushButtonAddTag.clicked.connect(BatchTagAddWidget._on_add_tag_clicked)

        QMetaObject.connectSlotsByName(BatchTagAddWidget)
    # setupUi

    def retranslateUi(self, BatchTagAddWidget: QWidget) -> None:
        BatchTagAddWidget.setWindowTitle(QCoreApplication.translate("BatchTagAddWidget", u"Batch Tag Add", None))
        self.groupBoxTagInput.setTitle(QCoreApplication.translate("BatchTagAddWidget", u"\u30bf\u30b0\u8ffd\u52a0", None))
        self.labelTagInstruction.setText(QCoreApplication.translate("BatchTagAddWidget", u"\u8ffd\u52a0\u3059\u308b\u30bf\u30b0\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044:", None))
        self.lineEditTag.setPlaceholderText(QCoreApplication.translate("BatchTagAddWidget", u"\u4f8b: landscape", None))
        self.pushButtonAddTag.setText(QCoreApplication.translate("BatchTagAddWidget", u"\u8ffd\u52a0", None))
    # retranslateUi

