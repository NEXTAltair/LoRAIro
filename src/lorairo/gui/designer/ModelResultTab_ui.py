# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ModelResultTab.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
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
from PySide6.QtWidgets import (QApplication, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QProgressBar, QScrollArea, QSizePolicy,
    QSpacerItem, QStackedWidget, QTextEdit, QVBoxLayout,
    QWidget)

class Ui_ModelResultTab(object):
    def setupUi(self, ModelResultTab):
        if not ModelResultTab.objectName():
            ModelResultTab.setObjectName(u"ModelResultTab")
        ModelResultTab.resize(500, 400)
        self.verticalLayout = QVBoxLayout(ModelResultTab)
        self.verticalLayout.setSpacing(10)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(10, 10, 10, 10)
        self.frameModelHeader = QFrame(ModelResultTab)
        self.frameModelHeader.setObjectName(u"frameModelHeader")
        self.frameModelHeader.setFrameShape(QFrame.StyledPanel)
        self.frameModelHeader.setMaximumSize(QSize(16777215, 60))
        self.horizontalLayoutHeader = QHBoxLayout(self.frameModelHeader)
        self.horizontalLayoutHeader.setObjectName(u"horizontalLayoutHeader")
        self.labelModelName = QLabel(self.frameModelHeader)
        self.labelModelName.setObjectName(u"labelModelName")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.labelModelName.setFont(font)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelModelName.sizePolicy().hasHeightForWidth())
        self.labelModelName.setSizePolicy(sizePolicy)

        self.horizontalLayoutHeader.addWidget(self.labelModelName)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutHeader.addItem(self.horizontalSpacer)

        self.labelProcessingTime = QLabel(self.frameModelHeader)
        self.labelProcessingTime.setObjectName(u"labelProcessingTime")
        font1 = QFont()
        font1.setPointSize(8)
        self.labelProcessingTime.setFont(font1)
        sizePolicy.setHeightForWidth(self.labelProcessingTime.sizePolicy().hasHeightForWidth())
        self.labelProcessingTime.setSizePolicy(sizePolicy)

        self.horizontalLayoutHeader.addWidget(self.labelProcessingTime)

        self.labelStatus = QLabel(self.frameModelHeader)
        self.labelStatus.setObjectName(u"labelStatus")
        font2 = QFont()
        font2.setPointSize(9)
        font2.setBold(True)
        self.labelStatus.setFont(font2)
        self.labelStatus.setStyleSheet(u"color: green;")
        sizePolicy.setHeightForWidth(self.labelStatus.sizePolicy().hasHeightForWidth())
        self.labelStatus.setSizePolicy(sizePolicy)

        self.horizontalLayoutHeader.addWidget(self.labelStatus)


        self.verticalLayout.addWidget(self.frameModelHeader)

        self.stackedWidgetContent = QStackedWidget(ModelResultTab)
        self.stackedWidgetContent.setObjectName(u"stackedWidgetContent")
        self.pageSuccess = QWidget()
        self.pageSuccess.setObjectName(u"pageSuccess")
        self.verticalLayoutSuccess = QVBoxLayout(self.pageSuccess)
        self.verticalLayoutSuccess.setObjectName(u"verticalLayoutSuccess")
        self.groupBoxTags = QGroupBox(self.pageSuccess)
        self.groupBoxTags.setObjectName(u"groupBoxTags")
        self.groupBoxTags.setMaximumSize(QSize(16777215, 120))
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName(u"verticalLayoutTags")
        self.scrollAreaTags = QScrollArea(self.groupBoxTags)
        self.scrollAreaTags.setObjectName(u"scrollAreaTags")
        self.scrollAreaTags.setWidgetResizable(True)
        self.scrollAreaTags.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.scrollAreaTags.sizePolicy().hasHeightForWidth())
        self.scrollAreaTags.setSizePolicy(sizePolicy1)
        self.scrollAreaWidgetContentsTags = QWidget()
        self.scrollAreaWidgetContentsTags.setObjectName(u"scrollAreaWidgetContentsTags")
        self.scrollAreaWidgetContentsTags.setGeometry(QRect(0, 0, 476, 69))
        self.verticalLayoutTagsContent = QVBoxLayout(self.scrollAreaWidgetContentsTags)
        self.verticalLayoutTagsContent.setObjectName(u"verticalLayoutTagsContent")
        self.labelTagsPlaceholder = QLabel(self.scrollAreaWidgetContentsTags)
        self.labelTagsPlaceholder.setObjectName(u"labelTagsPlaceholder")
        self.labelTagsPlaceholder.setStyleSheet(u"color: #888;")
        sizePolicy.setHeightForWidth(self.labelTagsPlaceholder.sizePolicy().hasHeightForWidth())
        self.labelTagsPlaceholder.setSizePolicy(sizePolicy)

        self.verticalLayoutTagsContent.addWidget(self.labelTagsPlaceholder)

        self.scrollAreaTags.setWidget(self.scrollAreaWidgetContentsTags)

        self.verticalLayoutTags.addWidget(self.scrollAreaTags)


        self.verticalLayoutSuccess.addWidget(self.groupBoxTags)

        self.groupBoxCaptions = QGroupBox(self.pageSuccess)
        self.groupBoxCaptions.setObjectName(u"groupBoxCaptions")
        self.groupBoxCaptions.setMaximumSize(QSize(16777215, 120))
        self.verticalLayoutCaptions = QVBoxLayout(self.groupBoxCaptions)
        self.verticalLayoutCaptions.setObjectName(u"verticalLayoutCaptions")
        self.textEditCaptions = QTextEdit(self.groupBoxCaptions)
        self.textEditCaptions.setObjectName(u"textEditCaptions")
        self.textEditCaptions.setReadOnly(True)
        self.textEditCaptions.setMaximumSize(QSize(16777215, 90))

        self.verticalLayoutCaptions.addWidget(self.textEditCaptions)


        self.verticalLayoutSuccess.addWidget(self.groupBoxCaptions)

        self.groupBoxScores = QGroupBox(self.pageSuccess)
        self.groupBoxScores.setObjectName(u"groupBoxScores")
        self.groupBoxScores.setMaximumSize(QSize(16777215, 80))
        self.verticalLayoutScores = QVBoxLayout(self.groupBoxScores)
        self.verticalLayoutScores.setObjectName(u"verticalLayoutScores")
        self.frameScoreContent = QFrame(self.groupBoxScores)
        self.frameScoreContent.setObjectName(u"frameScoreContent")
        self.frameScoreContent.setFrameShape(QFrame.NoFrame)
        self.horizontalLayoutScore = QHBoxLayout(self.frameScoreContent)
        self.horizontalLayoutScore.setObjectName(u"horizontalLayoutScore")
        self.labelScoreValue = QLabel(self.frameScoreContent)
        self.labelScoreValue.setObjectName(u"labelScoreValue")
        font3 = QFont()
        font3.setPointSize(16)
        font3.setBold(True)
        self.labelScoreValue.setFont(font3)
        self.labelScoreValue.setAlignment(Qt.AlignCenter)
        sizePolicy.setHeightForWidth(self.labelScoreValue.sizePolicy().hasHeightForWidth())
        self.labelScoreValue.setSizePolicy(sizePolicy)

        self.horizontalLayoutScore.addWidget(self.labelScoreValue)

        self.progressBarScore = QProgressBar(self.frameScoreContent)
        self.progressBarScore.setObjectName(u"progressBarScore")
        self.progressBarScore.setMinimum(0)
        self.progressBarScore.setMaximum(100)
        self.progressBarScore.setValue(85)
        self.progressBarScore.setTextVisible(False)
        self.progressBarScore.setOrientation(Qt.Horizontal)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.progressBarScore.sizePolicy().hasHeightForWidth())
        self.progressBarScore.setSizePolicy(sizePolicy2)

        self.horizontalLayoutScore.addWidget(self.progressBarScore)


        self.verticalLayoutScores.addWidget(self.frameScoreContent)


        self.verticalLayoutSuccess.addWidget(self.groupBoxScores)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutSuccess.addItem(self.verticalSpacer)

        self.stackedWidgetContent.addWidget(self.pageSuccess)
        self.pageError = QWidget()
        self.pageError.setObjectName(u"pageError")
        self.verticalLayoutError = QVBoxLayout(self.pageError)
        self.verticalLayoutError.setObjectName(u"verticalLayoutError")
        self.frameErrorHeader = QFrame(self.pageError)
        self.frameErrorHeader.setObjectName(u"frameErrorHeader")
        self.frameErrorHeader.setFrameShape(QFrame.StyledPanel)
        self.frameErrorHeader.setStyleSheet(u"QFrame {\n"
"    background-color: #ffe6e6;\n"
"    border: 2px solid #ff6b6b;\n"
"    border-radius: 8px;\n"
"}")
        self.frameErrorHeader.setMaximumSize(QSize(16777215, 50))
        self.horizontalLayoutErrorHeader = QHBoxLayout(self.frameErrorHeader)
        self.horizontalLayoutErrorHeader.setObjectName(u"horizontalLayoutErrorHeader")
        self.labelErrorIcon = QLabel(self.frameErrorHeader)
        self.labelErrorIcon.setObjectName(u"labelErrorIcon")
        font4 = QFont()
        font4.setPointSize(16)
        self.labelErrorIcon.setFont(font4)
        sizePolicy.setHeightForWidth(self.labelErrorIcon.sizePolicy().hasHeightForWidth())
        self.labelErrorIcon.setSizePolicy(sizePolicy)

        self.horizontalLayoutErrorHeader.addWidget(self.labelErrorIcon)

        self.labelErrorTitle = QLabel(self.frameErrorHeader)
        self.labelErrorTitle.setObjectName(u"labelErrorTitle")
        font5 = QFont()
        font5.setPointSize(12)
        font5.setBold(True)
        self.labelErrorTitle.setFont(font5)
        self.labelErrorTitle.setStyleSheet(u"color: #d32f2f;")
        sizePolicy.setHeightForWidth(self.labelErrorTitle.sizePolicy().hasHeightForWidth())
        self.labelErrorTitle.setSizePolicy(sizePolicy)

        self.horizontalLayoutErrorHeader.addWidget(self.labelErrorTitle)

        self.horizontalSpacerError = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutErrorHeader.addItem(self.horizontalSpacerError)


        self.verticalLayoutError.addWidget(self.frameErrorHeader)

        self.groupBoxErrorDetails = QGroupBox(self.pageError)
        self.groupBoxErrorDetails.setObjectName(u"groupBoxErrorDetails")
        self.verticalLayoutErrorDetails = QVBoxLayout(self.groupBoxErrorDetails)
        self.verticalLayoutErrorDetails.setObjectName(u"verticalLayoutErrorDetails")
        self.textEditErrorMessage = QTextEdit(self.groupBoxErrorDetails)
        self.textEditErrorMessage.setObjectName(u"textEditErrorMessage")
        self.textEditErrorMessage.setReadOnly(True)
        self.textEditErrorMessage.setStyleSheet(u"QTextEdit {\n"
"    background-color: #fff5f5;\n"
"    border: 1px solid #ffcccb;\n"
"    color: #d32f2f;\n"
"    font-family: monospace;\n"
"}")
        sizePolicy1.setHeightForWidth(self.textEditErrorMessage.sizePolicy().hasHeightForWidth())
        self.textEditErrorMessage.setSizePolicy(sizePolicy1)

        self.verticalLayoutErrorDetails.addWidget(self.textEditErrorMessage)


        self.verticalLayoutError.addWidget(self.groupBoxErrorDetails)

        self.verticalSpacerError = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutError.addItem(self.verticalSpacerError)

        self.stackedWidgetContent.addWidget(self.pageError)

        self.verticalLayout.addWidget(self.stackedWidgetContent)


        self.retranslateUi(ModelResultTab)

        self.stackedWidgetContent.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(ModelResultTab)
    # setupUi

    def retranslateUi(self, ModelResultTab):
        self.labelModelName.setText(QCoreApplication.translate("ModelResultTab", u"\u30e2\u30c7\u30eb\u540d: GPT-4o", None))
        self.labelProcessingTime.setText(QCoreApplication.translate("ModelResultTab", u"\u51e6\u7406\u6642\u9593: 2.3s", None))
        self.labelStatus.setText(QCoreApplication.translate("ModelResultTab", u"\u2713 \u6210\u529f", None))
        self.groupBoxTags.setTitle(QCoreApplication.translate("ModelResultTab", u"\u30bf\u30b0", None))
        self.labelTagsPlaceholder.setText(QCoreApplication.translate("ModelResultTab", u"\u30bf\u30b0\u306a\u3057", None))
        self.groupBoxCaptions.setTitle(QCoreApplication.translate("ModelResultTab", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.textEditCaptions.setPlaceholderText(QCoreApplication.translate("ModelResultTab", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u306a\u3057", None))
        self.groupBoxScores.setTitle(QCoreApplication.translate("ModelResultTab", u"\u30b9\u30b3\u30a2", None))
        self.labelScoreValue.setText(QCoreApplication.translate("ModelResultTab", u"0.85", None))
        self.labelErrorIcon.setText(QCoreApplication.translate("ModelResultTab", u"\u26a0\ufe0f", None))
        self.labelErrorTitle.setText(QCoreApplication.translate("ModelResultTab", u"\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u51e6\u7406\u30a8\u30e9\u30fc", None))
        self.groupBoxErrorDetails.setTitle(QCoreApplication.translate("ModelResultTab", u"\u30a8\u30e9\u30fc\u8a73\u7d30", None))
        self.textEditErrorMessage.setPlaceholderText(QCoreApplication.translate("ModelResultTab", u"\u30a8\u30e9\u30fc\u60c5\u5831\u304c\u8aad\u307f\u8fbc\u307e\u308c\u307e\u3059...", None))
        pass
    # retranslateUi

