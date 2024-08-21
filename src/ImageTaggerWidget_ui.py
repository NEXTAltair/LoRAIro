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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSplitter, QTextEdit, QVBoxLayout,
    QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from ImagePreviewWidget import ImagePreviewWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_ImageTaggerWidget(object):
    def setupUi(self, ImageTaggerWidget):
        if not ImageTaggerWidget.objectName():
            ImageTaggerWidget.setObjectName(u"ImageTaggerWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ImageTaggerWidget.sizePolicy().hasHeightForWidth())
        ImageTaggerWidget.setSizePolicy(sizePolicy)
        self.horizontalLayout = QHBoxLayout(ImageTaggerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.splitterMain = QSplitter(ImageTaggerWidget)
        self.splitterMain.setObjectName(u"splitterMain")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.splitterMain.sizePolicy().hasHeightForWidth())
        self.splitterMain.setSizePolicy(sizePolicy1)
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.splitterMain.setProperty("sizes", 667)
        self.taggingAreaWidget = QWidget(self.splitterMain)
        self.taggingAreaWidget.setObjectName(u"taggingAreaWidget")
        self.verticalLayoutTaggingArea = QVBoxLayout(self.taggingAreaWidget)
        self.verticalLayoutTaggingArea.setObjectName(u"verticalLayoutTaggingArea")
        self.gridLayoutApiOptions = QGridLayout()
        self.gridLayoutApiOptions.setObjectName(u"gridLayoutApiOptions")
        self.labelAPI = QLabel(self.taggingAreaWidget)
        self.labelAPI.setObjectName(u"labelAPI")

        self.gridLayoutApiOptions.addWidget(self.labelAPI, 0, 0, 1, 1)

        self.comboBoxAPI = QComboBox(self.taggingAreaWidget)
        self.comboBoxAPI.setObjectName(u"comboBoxAPI")

        self.gridLayoutApiOptions.addWidget(self.comboBoxAPI, 0, 1, 1, 1)

        self.labelModel = QLabel(self.taggingAreaWidget)
        self.labelModel.setObjectName(u"labelModel")

        self.gridLayoutApiOptions.addWidget(self.labelModel, 1, 0, 1, 1)

        self.comboBoxModel = QComboBox(self.taggingAreaWidget)
        self.comboBoxModel.setObjectName(u"comboBoxModel")

        self.gridLayoutApiOptions.addWidget(self.comboBoxModel, 1, 1, 1, 1)

        self.labelTagFormat = QLabel(self.taggingAreaWidget)
        self.labelTagFormat.setObjectName(u"labelTagFormat")

        self.gridLayoutApiOptions.addWidget(self.labelTagFormat, 2, 0, 1, 1)

        self.comboBoxTagFormat = QComboBox(self.taggingAreaWidget)
        self.comboBoxTagFormat.setObjectName(u"comboBoxTagFormat")

        self.gridLayoutApiOptions.addWidget(self.comboBoxTagFormat, 2, 1, 1, 1)


        self.verticalLayoutTaggingArea.addLayout(self.gridLayoutApiOptions)

        self.groupBoxPrompt = QGroupBox(self.taggingAreaWidget)
        self.groupBoxPrompt.setObjectName(u"groupBoxPrompt")
        self.verticalLayoutPrompt = QVBoxLayout(self.groupBoxPrompt)
        self.verticalLayoutPrompt.setObjectName(u"verticalLayoutPrompt")
        self.textEditMainPrompt = QTextEdit(self.groupBoxPrompt)
        self.textEditMainPrompt.setObjectName(u"textEditMainPrompt")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(2)
        sizePolicy2.setHeightForWidth(self.textEditMainPrompt.sizePolicy().hasHeightForWidth())
        self.textEditMainPrompt.setSizePolicy(sizePolicy2)

        self.verticalLayoutPrompt.addWidget(self.textEditMainPrompt)

        self.textEditAddPrompt = QTextEdit(self.groupBoxPrompt)
        self.textEditAddPrompt.setObjectName(u"textEditAddPrompt")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(1)
        sizePolicy3.setHeightForWidth(self.textEditAddPrompt.sizePolicy().hasHeightForWidth())
        self.textEditAddPrompt.setSizePolicy(sizePolicy3)

        self.verticalLayoutPrompt.addWidget(self.textEditAddPrompt)

        self.pushButtonGenerate = QPushButton(self.groupBoxPrompt)
        self.pushButtonGenerate.setObjectName(u"pushButtonGenerate")

        self.verticalLayoutPrompt.addWidget(self.pushButtonGenerate)


        self.verticalLayoutTaggingArea.addWidget(self.groupBoxPrompt)

        self.groupBoxResults = QGroupBox(self.taggingAreaWidget)
        self.groupBoxResults.setObjectName(u"groupBoxResults")
        self.verticalLayoutResults = QVBoxLayout(self.groupBoxResults)
        self.verticalLayoutResults.setObjectName(u"verticalLayoutResults")
        self.textEditTags = QTextEdit(self.groupBoxResults)
        self.textEditTags.setObjectName(u"textEditTags")

        self.verticalLayoutResults.addWidget(self.textEditTags)

        self.textEditCaption = QTextEdit(self.groupBoxResults)
        self.textEditCaption.setObjectName(u"textEditCaption")

        self.verticalLayoutResults.addWidget(self.textEditCaption)

        self.DirectoryPickerSave = DirectoryPickerWidget(self.groupBoxResults)
        self.DirectoryPickerSave.setObjectName(u"DirectoryPickerSave")

        self.verticalLayoutResults.addWidget(self.DirectoryPickerSave, 0, Qt.AlignmentFlag.AlignLeft)

        self.horizontalLayoutResultButtons = QHBoxLayout()
        self.horizontalLayoutResultButtons.setObjectName(u"horizontalLayoutResultButtons")
        self.checkBoxText = QCheckBox(self.groupBoxResults)
        self.checkBoxText.setObjectName(u"checkBoxText")

        self.horizontalLayoutResultButtons.addWidget(self.checkBoxText)

        self.checkBoxJson = QCheckBox(self.groupBoxResults)
        self.checkBoxJson.setObjectName(u"checkBoxJson")

        self.horizontalLayoutResultButtons.addWidget(self.checkBoxJson)

        self.checkBoxDB = QCheckBox(self.groupBoxResults)
        self.checkBoxDB.setObjectName(u"checkBoxDB")

        self.horizontalLayoutResultButtons.addWidget(self.checkBoxDB)

        self.pushButtonSave = QPushButton(self.groupBoxResults)
        self.pushButtonSave.setObjectName(u"pushButtonSave")

        self.horizontalLayoutResultButtons.addWidget(self.pushButtonSave)


        self.verticalLayoutResults.addLayout(self.horizontalLayoutResultButtons)


        self.verticalLayoutTaggingArea.addWidget(self.groupBoxResults)

        self.splitterMain.addWidget(self.taggingAreaWidget)
        self.imageAreaWidget = QWidget(self.splitterMain)
        self.imageAreaWidget.setObjectName(u"imageAreaWidget")
        sizePolicy.setHeightForWidth(self.imageAreaWidget.sizePolicy().hasHeightForWidth())
        self.imageAreaWidget.setSizePolicy(sizePolicy)
        self.verticalLayoutImageArea = QVBoxLayout(self.imageAreaWidget)
        self.verticalLayoutImageArea.setObjectName(u"verticalLayoutImageArea")
        self.splitterImage = QSplitter(self.imageAreaWidget)
        self.splitterImage.setObjectName(u"splitterImage")
        self.splitterImage.setOrientation(Qt.Orientation.Vertical)
        self.splitterImage.setProperty("sizes", 250)
        self.ImagePreview = ImagePreviewWidget(self.splitterImage)
        self.ImagePreview.setObjectName(u"ImagePreview")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy4.setHorizontalStretch(1)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy4)
        self.splitterImage.addWidget(self.ImagePreview)
        self.ThumbnailSelector = ThumbnailSelectorWidget(self.splitterImage)
        self.ThumbnailSelector.setObjectName(u"ThumbnailSelector")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy5.setHorizontalStretch(2)
        sizePolicy5.setVerticalStretch(2)
        sizePolicy5.setHeightForWidth(self.ThumbnailSelector.sizePolicy().hasHeightForWidth())
        self.ThumbnailSelector.setSizePolicy(sizePolicy5)
        self.splitterImage.addWidget(self.ThumbnailSelector)

        self.verticalLayoutImageArea.addWidget(self.splitterImage)

        self.splitterMain.addWidget(self.imageAreaWidget)

        self.horizontalLayout.addWidget(self.splitterMain)


        self.retranslateUi(ImageTaggerWidget)

        QMetaObject.connectSlotsByName(ImageTaggerWidget)
    # setupUi

    def retranslateUi(self, ImageTaggerWidget):
        ImageTaggerWidget.setWindowTitle(QCoreApplication.translate("ImageTaggerWidget", u"Image Tagger", None))
        self.labelAPI.setText(QCoreApplication.translate("ImageTaggerWidget", u"API:", None))
        self.labelModel.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u30e2\u30c7\u30eb:", None))
        self.labelTagFormat.setText(QCoreApplication.translate("ImageTaggerWidget", u"FORMAT", None))
        self.groupBoxPrompt.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.textEditMainPrompt.setPlaceholderText(QCoreApplication.translate("ImageTaggerWidget", u"\u8a73\u7d30\u306a\u30d7\u30ed\u30f3\u30d7\u30c8\u3092\u5165\u529b (\u4f8b: \u9ad8\u753b\u8cea, \u5177\u4f53\u7684\u306a\u63cf\u5199\u306a\u3069)", None))
        self.textEditAddPrompt.setPlaceholderText(QCoreApplication.translate("ImageTaggerWidget", u"\u9078\u629e\u3057\u305f\u753b\u50cf\u306e\u5927\u307e\u304b\u306a\u50be\u5411\u3092\u6307\u793a\u3059\u308b\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.pushButtonGenerate.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u751f\u6210", None))
        self.groupBoxResults.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u7d50\u679c", None))
        self.checkBoxText.setText(QCoreApplication.translate("ImageTaggerWidget", u"Text", None))
        self.checkBoxJson.setText(QCoreApplication.translate("ImageTaggerWidget", u"Json", None))
        self.checkBoxDB.setText(QCoreApplication.translate("ImageTaggerWidget", u"DataBase", None))
        self.pushButtonSave.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

