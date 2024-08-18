# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ImageTaggerWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
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
    QSpacerItem, QSplitter, QTextEdit, QVBoxLayout,
    QWidget)

from ImagePreviewWidget import ImagePreviewWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_ImageTaggerWidget(object):
    def setupUi(self, ImageTaggerWidget):
        if not ImageTaggerWidget.objectName():
            ImageTaggerWidget.setObjectName(u"ImageTaggerWidget")
        ImageTaggerWidget.resize(1000, 650)
        self.horizontalLayout = QHBoxLayout(ImageTaggerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.splitterMain = QSplitter(ImageTaggerWidget)
        self.splitterMain.setObjectName(u"splitterMain")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitterMain.sizePolicy().hasHeightForWidth())
        self.splitterMain.setSizePolicy(sizePolicy)
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.taggingAreaWidget = QWidget(self.splitterMain)
        self.taggingAreaWidget.setObjectName(u"taggingAreaWidget")
        self.verticalLayout_2 = QVBoxLayout(self.taggingAreaWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.gridLayoutApiOptions = QGridLayout()
        self.gridLayoutApiOptions.setObjectName(u"gridLayoutApiOptions")
        self.comboBoxModel = QComboBox(self.taggingAreaWidget)
        self.comboBoxModel.setObjectName(u"comboBoxModel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.comboBoxModel.sizePolicy().hasHeightForWidth())
        self.comboBoxModel.setSizePolicy(sizePolicy1)

        self.gridLayoutApiOptions.addWidget(self.comboBoxModel, 1, 1, 1, 1)

        self.labelModel = QLabel(self.taggingAreaWidget)
        self.labelModel.setObjectName(u"labelModel")

        self.gridLayoutApiOptions.addWidget(self.labelModel, 1, 0, 1, 1)

        self.comboBoxAPI = QComboBox(self.taggingAreaWidget)
        self.comboBoxAPI.setObjectName(u"comboBoxAPI")
        sizePolicy1.setHeightForWidth(self.comboBoxAPI.sizePolicy().hasHeightForWidth())
        self.comboBoxAPI.setSizePolicy(sizePolicy1)
        self.comboBoxAPI.setCurrentText(u"")
        self.comboBoxAPI.setPlaceholderText(u"")

        self.gridLayoutApiOptions.addWidget(self.comboBoxAPI, 0, 1, 1, 1)

        self.labelAPI = QLabel(self.taggingAreaWidget)
        self.labelAPI.setObjectName(u"labelAPI")

        self.gridLayoutApiOptions.addWidget(self.labelAPI, 0, 0, 1, 1)


        self.verticalLayout_2.addLayout(self.gridLayoutApiOptions)

        self.groupBoxPrompt = QGroupBox(self.taggingAreaWidget)
        self.groupBoxPrompt.setObjectName(u"groupBoxPrompt")
        self.verticalLayout_prompt = QVBoxLayout(self.groupBoxPrompt)
        self.verticalLayout_prompt.setObjectName(u"verticalLayout_prompt")
        self.textEditPrompt = QTextEdit(self.groupBoxPrompt)
        self.textEditPrompt.setObjectName(u"textEditPrompt")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.textEditPrompt.sizePolicy().hasHeightForWidth())
        self.textEditPrompt.setSizePolicy(sizePolicy2)

        self.verticalLayout_prompt.addWidget(self.textEditPrompt)


        self.verticalLayout_2.addWidget(self.groupBoxPrompt)

        self.groupBoxResults = QGroupBox(self.taggingAreaWidget)
        self.groupBoxResults.setObjectName(u"groupBoxResults")
        self.verticalLayout_results = QVBoxLayout(self.groupBoxResults)
        self.verticalLayout_results.setObjectName(u"verticalLayout_results")
        self.textEditTags = QTextEdit(self.groupBoxResults)
        self.textEditTags.setObjectName(u"textEditTags")

        self.verticalLayout_results.addWidget(self.textEditTags)

        self.textEditCaption = QTextEdit(self.groupBoxResults)
        self.textEditCaption.setObjectName(u"textEditCaption")

        self.verticalLayout_results.addWidget(self.textEditCaption)

        self.horizontalLayoutResultButtons = QHBoxLayout()
        self.horizontalLayoutResultButtons.setObjectName(u"horizontalLayoutResultButtons")
        self.horizontalSpacerResultButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutResultButtons.addItem(self.horizontalSpacerResultButtons)

        self.pushButtonGenerate = QPushButton(self.groupBoxResults)
        self.pushButtonGenerate.setObjectName(u"pushButtonGenerate")

        self.horizontalLayoutResultButtons.addWidget(self.pushButtonGenerate)

        self.pushButtonSave = QPushButton(self.groupBoxResults)
        self.pushButtonSave.setObjectName(u"pushButtonSave")

        self.horizontalLayoutResultButtons.addWidget(self.pushButtonSave)


        self.verticalLayout_results.addLayout(self.horizontalLayoutResultButtons)


        self.verticalLayout_2.addWidget(self.groupBoxResults)

        self.splitterMain.addWidget(self.taggingAreaWidget)
        self.ImageWidget = QWidget(self.splitterMain)
        self.ImageWidget.setObjectName(u"ImageWidget")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(1)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.ImageWidget.sizePolicy().hasHeightForWidth())
        self.ImageWidget.setSizePolicy(sizePolicy3)
        self.verticalLayout = QVBoxLayout(self.ImageWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.splitter = QSplitter(self.ImageWidget)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.ImagePreview = ImagePreviewWidget(self.splitter)
        self.ImagePreview.setObjectName(u"ImagePreview")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(1)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy4)
        self.splitter.addWidget(self.ImagePreview)
        self.ThumbnailSelector = ThumbnailSelectorWidget(self.splitter)
        self.ThumbnailSelector.setObjectName(u"ThumbnailSelector")
        sizePolicy4.setHeightForWidth(self.ThumbnailSelector.sizePolicy().hasHeightForWidth())
        self.ThumbnailSelector.setSizePolicy(sizePolicy4)
        self.splitter.addWidget(self.ThumbnailSelector)

        self.verticalLayout.addWidget(self.splitter)

        self.splitterMain.addWidget(self.ImageWidget)

        self.horizontalLayout.addWidget(self.splitterMain)


        self.retranslateUi(ImageTaggerWidget)
        self.textEditPrompt.textChanged.connect(ImageTaggerWidget.send_vision_prompt)
        self.comboBoxModel.currentTextChanged.connect(ImageTaggerWidget.send_vision_model)

        QMetaObject.connectSlotsByName(ImageTaggerWidget)
    # setupUi

    def retranslateUi(self, ImageTaggerWidget):
        ImageTaggerWidget.setWindowTitle(QCoreApplication.translate("ImageTaggerWidget", u"Image Tagger", None))
        self.labelModel.setText(QCoreApplication.translate("ImageTaggerWidget", u"Model:", None))
        self.labelAPI.setText(QCoreApplication.translate("ImageTaggerWidget", u"API:", None))
        self.groupBoxPrompt.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.textEditPrompt.setPlaceholderText(QCoreApplication.translate("ImageTaggerWidget", u"\u8a73\u7d30\u306a\u30d7\u30ed\u30f3\u30d7\u30c8\u3092\u5165\u529b (\u4f8b: \u9ad8\u753b\u8cea, \u5177\u4f53\u7684\u306a\u63cf\u5199\u306a\u3069)", None))
        self.groupBoxResults.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u7d50\u679c", None))
        self.textEditTags.setPlaceholderText("")
        self.textEditCaption.setPlaceholderText("")
        self.pushButtonGenerate.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u751f\u6210", None))
        self.pushButtonSave.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

