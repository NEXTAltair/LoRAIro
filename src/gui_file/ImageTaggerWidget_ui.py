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
    QSizePolicy, QSlider, QSplitter, QTextEdit,
    QVBoxLayout, QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from ImagePreviewWidget import ImagePreviewWidget
from TagFilterWidget import TagFilterWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_ImageTaggerWidget(object):
    def setupUi(self, ImageTaggerWidget):
        if not ImageTaggerWidget.objectName():
            ImageTaggerWidget.setObjectName(u"ImageTaggerWidget")
        ImageTaggerWidget.resize(355, 1116)
        self.horizontalLayout = QHBoxLayout(ImageTaggerWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.splitterMain = QSplitter(ImageTaggerWidget)
        self.splitterMain.setObjectName(u"splitterMain")
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

        self.lowRescheckBox = QCheckBox(self.taggingAreaWidget)
        self.lowRescheckBox.setObjectName(u"lowRescheckBox")

        self.verticalLayoutTaggingArea.addWidget(self.lowRescheckBox)

        self.groupBoxPrompt = QGroupBox(self.taggingAreaWidget)
        self.groupBoxPrompt.setObjectName(u"groupBoxPrompt")
        self.verticalLayoutPrompt = QVBoxLayout(self.groupBoxPrompt)
        self.verticalLayoutPrompt.setObjectName(u"verticalLayoutPrompt")
        self.textEditMainPrompt = QTextEdit(self.groupBoxPrompt)
        self.textEditMainPrompt.setObjectName(u"textEditMainPrompt")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(2)
        sizePolicy.setHeightForWidth(self.textEditMainPrompt.sizePolicy().hasHeightForWidth())
        self.textEditMainPrompt.setSizePolicy(sizePolicy)

        self.verticalLayoutPrompt.addWidget(self.textEditMainPrompt)

        self.textEditAddPrompt = QTextEdit(self.groupBoxPrompt)
        self.textEditAddPrompt.setObjectName(u"textEditAddPrompt")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.textEditAddPrompt.sizePolicy().hasHeightForWidth())
        self.textEditAddPrompt.setSizePolicy(sizePolicy1)

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

        self.scoreSlider = QSlider(self.groupBoxResults)
        self.scoreSlider.setObjectName(u"scoreSlider")
        self.scoreSlider.setMaximum(1000)
        self.scoreSlider.setSingleStep(1)
        self.scoreSlider.setOrientation(Qt.Orientation.Horizontal)

        self.verticalLayoutResults.addWidget(self.scoreSlider)

        self.savecheckWidget = QWidget(self.groupBoxResults)
        self.savecheckWidget.setObjectName(u"savecheckWidget")
        self.horizontalLayout_2 = QHBoxLayout(self.savecheckWidget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.checkBoxText = QCheckBox(self.savecheckWidget)
        self.checkBoxText.setObjectName(u"checkBoxText")

        self.horizontalLayout_2.addWidget(self.checkBoxText)

        self.checkBoxJson = QCheckBox(self.savecheckWidget)
        self.checkBoxJson.setObjectName(u"checkBoxJson")

        self.horizontalLayout_2.addWidget(self.checkBoxJson)

        self.checkBoxDB = QCheckBox(self.savecheckWidget)
        self.checkBoxDB.setObjectName(u"checkBoxDB")

        self.horizontalLayout_2.addWidget(self.checkBoxDB)


        self.verticalLayoutResults.addWidget(self.savecheckWidget)

        self.horizontalLayoutSave = QHBoxLayout()
        self.horizontalLayoutSave.setObjectName(u"horizontalLayoutSave")
        self.DirectoryPickerSave = DirectoryPickerWidget(self.groupBoxResults)
        self.DirectoryPickerSave.setObjectName(u"DirectoryPickerSave")

        self.horizontalLayoutSave.addWidget(self.DirectoryPickerSave)

        self.pushButtonSave = QPushButton(self.groupBoxResults)
        self.pushButtonSave.setObjectName(u"pushButtonSave")

        self.horizontalLayoutSave.addWidget(self.pushButtonSave)


        self.verticalLayoutResults.addLayout(self.horizontalLayoutSave)


        self.verticalLayoutTaggingArea.addWidget(self.groupBoxResults)

        self.splitterMain.addWidget(self.taggingAreaWidget)
        self.imageAreaWidget = QWidget(self.splitterMain)
        self.imageAreaWidget.setObjectName(u"imageAreaWidget")
        self.verticalLayoutImageArea = QVBoxLayout(self.imageAreaWidget)
        self.verticalLayoutImageArea.setObjectName(u"verticalLayoutImageArea")
        self.dbSearchWidget = TagFilterWidget(self.imageAreaWidget)
        self.dbSearchWidget.setObjectName(u"dbSearchWidget")

        self.verticalLayoutImageArea.addWidget(self.dbSearchWidget)

        self.splitterImage = QSplitter(self.imageAreaWidget)
        self.splitterImage.setObjectName(u"splitterImage")
        self.splitterImage.setOrientation(Qt.Orientation.Vertical)
        self.splitterImage.setProperty("sizes", 100)
        self.ImagePreview = ImagePreviewWidget(self.splitterImage)
        self.ImagePreview.setObjectName(u"ImagePreview")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy2)
        self.splitterImage.addWidget(self.ImagePreview)
        self.ThumbnailSelector = ThumbnailSelectorWidget(self.splitterImage)
        self.ThumbnailSelector.setObjectName(u"ThumbnailSelector")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(2)
        sizePolicy3.setVerticalStretch(2)
        sizePolicy3.setHeightForWidth(self.ThumbnailSelector.sizePolicy().hasHeightForWidth())
        self.ThumbnailSelector.setSizePolicy(sizePolicy3)
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
        self.labelTagFormat.setText(QCoreApplication.translate("ImageTaggerWidget", u"FORMT:", None))
        self.lowRescheckBox.setText(QCoreApplication.translate("ImageTaggerWidget", u"API\u8ca0\u8377\u8efd\u6e1b\u7528\u4f4e\u89e3\u50cf\u5ea6\u753b\u50cf\u3092\u4f7f\u7528", None))
        self.groupBoxPrompt.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.textEditMainPrompt.setPlaceholderText(QCoreApplication.translate("ImageTaggerWidget", u"\u30d7\u30ed\u30f3\u30d7\u30c8\u3092\u5165\u529b (\u4f8b: \u9ad8\u753b\u8cea, \u5177\u4f53\u7684\u306a\u63cf\u5199\u306a\u3069)", None))
        self.textEditAddPrompt.setPlaceholderText(QCoreApplication.translate("ImageTaggerWidget", u"\u9078\u629e\u3057\u305f\u753b\u50cf\u306e\u5927\u307e\u304b\u306a\u50be\u5411\u3092\u6307\u793a\u3059\u308b\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.pushButtonGenerate.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u30bf\u30b0/\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u751f\u6210", None))
        self.groupBoxResults.setTitle(QCoreApplication.translate("ImageTaggerWidget", u"\u7d50\u679c", None))
#if QT_CONFIG(tooltip)
        self.scoreSlider.setToolTip(QCoreApplication.translate("ImageTaggerWidget", u"<html><head/><body><p>\u30b9\u30b3\u30a2</p></body></html>", None))
#endif // QT_CONFIG(tooltip)
        self.checkBoxText.setText(QCoreApplication.translate("ImageTaggerWidget", u"txt", None))
        self.checkBoxJson.setText(QCoreApplication.translate("ImageTaggerWidget", u"Json", None))
        self.checkBoxDB.setText(QCoreApplication.translate("ImageTaggerWidget", u"DataBase", None))
        self.pushButtonSave.setText(QCoreApplication.translate("ImageTaggerWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

