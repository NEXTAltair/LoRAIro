# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SettingspageWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from FilePickerWidget import FilePickerWidget

class Ui_SettingspageWidget(object):
    def setupUi(self, SettingspageWidget):
        if not SettingspageWidget.objectName():
            SettingspageWidget.setObjectName(u"SettingspageWidget")
        SettingspageWidget.resize(705, 935)
        self.horizontalLayout = QHBoxLayout(SettingspageWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.scrollAreaSettings = QScrollArea(SettingspageWidget)
        self.scrollAreaSettings.setObjectName(u"scrollAreaSettings")
        self.scrollAreaSettings.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 685, 915))
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName(u"layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName(u"groupBoxFolders")
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName(u"layoutFolders")
        self.dataset_DirPickerWidget = DirectoryPickerWidget(self.groupBoxFolders)
        self.dataset_DirPickerWidget.setObjectName(u"dataset_DirPickerWidget")
        self.layoutDatasetFolder = QHBoxLayout(self.dataset_DirPickerWidget)
        self.layoutDatasetFolder.setObjectName(u"layoutDatasetFolder")

        self.layoutFolders.addWidget(self.dataset_DirPickerWidget)

        self.output_DirPickerWidget = DirectoryPickerWidget(self.groupBoxFolders)
        self.output_DirPickerWidget.setObjectName(u"output_DirPickerWidget")
        self.layoutOutputFolder = QHBoxLayout(self.output_DirPickerWidget)
        self.layoutOutputFolder.setObjectName(u"layoutOutputFolder")

        self.layoutFolders.addWidget(self.output_DirPickerWidget)

        self.response_DirPickerWidget = DirectoryPickerWidget(self.groupBoxFolders)
        self.response_DirPickerWidget.setObjectName(u"response_DirPickerWidget")
        self._2 = QHBoxLayout(self.response_DirPickerWidget)
        self._2.setObjectName(u"_2")

        self.layoutFolders.addWidget(self.response_DirPickerWidget)

        self.new_output_DirPickerWidget = DirectoryPickerWidget(self.groupBoxFolders)
        self.new_output_DirPickerWidget.setObjectName(u"new_output_DirPickerWidget")
        self.layoutEditedOutputFolder = QHBoxLayout(self.new_output_DirPickerWidget)
        self.layoutEditedOutputFolder.setObjectName(u"layoutEditedOutputFolder")

        self.layoutFolders.addWidget(self.new_output_DirPickerWidget)


        self.layoutScrollArea.addWidget(self.groupBoxFolders)

        self.groupBoxAPI = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxAPI.setObjectName(u"groupBoxAPI")
        self.layoutAPI = QVBoxLayout(self.groupBoxAPI)
        self.layoutAPI.setObjectName(u"layoutAPI")
        self.groupBoxOpenAI = QGroupBox(self.groupBoxAPI)
        self.groupBoxOpenAI.setObjectName(u"groupBoxOpenAI")
        self.layoutOpenAI = QFormLayout(self.groupBoxOpenAI)
        self.layoutOpenAI.setObjectName(u"layoutOpenAI")
        self.labelOpenAIApiKey = QLabel(self.groupBoxOpenAI)
        self.labelOpenAIApiKey.setObjectName(u"labelOpenAIApiKey")

        self.layoutOpenAI.setWidget(0, QFormLayout.LabelRole, self.labelOpenAIApiKey)

        self.lineEditOpenAIApiKey = QLineEdit(self.groupBoxOpenAI)
        self.lineEditOpenAIApiKey.setObjectName(u"lineEditOpenAIApiKey")

        self.layoutOpenAI.setWidget(0, QFormLayout.FieldRole, self.lineEditOpenAIApiKey)

        self.labelOpenAIModel = QLabel(self.groupBoxOpenAI)
        self.labelOpenAIModel.setObjectName(u"labelOpenAIModel")

        self.layoutOpenAI.setWidget(1, QFormLayout.LabelRole, self.labelOpenAIModel)

        self.lineEditOpenAIModel = QLineEdit(self.groupBoxOpenAI)
        self.lineEditOpenAIModel.setObjectName(u"lineEditOpenAIModel")

        self.layoutOpenAI.setWidget(1, QFormLayout.FieldRole, self.lineEditOpenAIModel)


        self.layoutAPI.addWidget(self.groupBoxOpenAI)

        self.groupBoxGoogleVision = QGroupBox(self.groupBoxAPI)
        self.groupBoxGoogleVision.setObjectName(u"groupBoxGoogleVision")
        self.layoutGoogleVision = QFormLayout(self.groupBoxGoogleVision)
        self.layoutGoogleVision.setObjectName(u"layoutGoogleVision")
        self.labelGoogleApiKey = QLabel(self.groupBoxGoogleVision)
        self.labelGoogleApiKey.setObjectName(u"labelGoogleApiKey")

        self.layoutGoogleVision.setWidget(0, QFormLayout.LabelRole, self.labelGoogleApiKey)

        self.lineEditGoogleApiKey = QLineEdit(self.groupBoxGoogleVision)
        self.lineEditGoogleApiKey.setObjectName(u"lineEditGoogleApiKey")

        self.layoutGoogleVision.setWidget(0, QFormLayout.FieldRole, self.lineEditGoogleApiKey)

        self.labelGoogleApiModel = QLabel(self.groupBoxGoogleVision)
        self.labelGoogleApiModel.setObjectName(u"labelGoogleApiModel")

        self.layoutGoogleVision.setWidget(1, QFormLayout.LabelRole, self.labelGoogleApiModel)

        self.lineEditGoogleApiModel = QLineEdit(self.groupBoxGoogleVision)
        self.lineEditGoogleApiModel.setObjectName(u"lineEditGoogleApiModel")

        self.layoutGoogleVision.setWidget(1, QFormLayout.FieldRole, self.lineEditGoogleApiModel)


        self.layoutAPI.addWidget(self.groupBoxGoogleVision)

        self.groupBoxAnthropic = QGroupBox(self.groupBoxAPI)
        self.groupBoxAnthropic.setObjectName(u"groupBoxAnthropic")
        self.layoutAnthropic = QFormLayout(self.groupBoxAnthropic)
        self.layoutAnthropic.setObjectName(u"layoutAnthropic")
        self.labelAnthropicApiKey = QLabel(self.groupBoxAnthropic)
        self.labelAnthropicApiKey.setObjectName(u"labelAnthropicApiKey")

        self.layoutAnthropic.setWidget(0, QFormLayout.LabelRole, self.labelAnthropicApiKey)

        self.lineEditAnthropicApiKey = QLineEdit(self.groupBoxAnthropic)
        self.lineEditAnthropicApiKey.setObjectName(u"lineEditAnthropicApiKey")

        self.layoutAnthropic.setWidget(0, QFormLayout.FieldRole, self.lineEditAnthropicApiKey)

        self.labelAnthropicApiModel = QLabel(self.groupBoxAnthropic)
        self.labelAnthropicApiModel.setObjectName(u"labelAnthropicApiModel")

        self.layoutAnthropic.setWidget(1, QFormLayout.LabelRole, self.labelAnthropicApiModel)

        self.lineEditAnthropicApiModel = QLineEdit(self.groupBoxAnthropic)
        self.lineEditAnthropicApiModel.setObjectName(u"lineEditAnthropicApiModel")

        self.layoutAnthropic.setWidget(1, QFormLayout.FieldRole, self.lineEditAnthropicApiModel)


        self.layoutAPI.addWidget(self.groupBoxAnthropic)


        self.layoutScrollArea.addWidget(self.groupBoxAPI)

        self.groupBoxHuggingFace = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxHuggingFace.setObjectName(u"groupBoxHuggingFace")
        self.layoutHuggingFace = QFormLayout(self.groupBoxHuggingFace)
        self.layoutHuggingFace.setObjectName(u"layoutHuggingFace")
        self.labelHuggingFaceUsername = QLabel(self.groupBoxHuggingFace)
        self.labelHuggingFaceUsername.setObjectName(u"labelHuggingFaceUsername")

        self.layoutHuggingFace.setWidget(0, QFormLayout.LabelRole, self.labelHuggingFaceUsername)

        self.lineEditHuggingFaceUsername = QLineEdit(self.groupBoxHuggingFace)
        self.lineEditHuggingFaceUsername.setObjectName(u"lineEditHuggingFaceUsername")

        self.layoutHuggingFace.setWidget(0, QFormLayout.FieldRole, self.lineEditHuggingFaceUsername)

        self.labelHuggingFaceRepoName = QLabel(self.groupBoxHuggingFace)
        self.labelHuggingFaceRepoName.setObjectName(u"labelHuggingFaceRepoName")

        self.layoutHuggingFace.setWidget(1, QFormLayout.LabelRole, self.labelHuggingFaceRepoName)

        self.lineEditHuggingFaceRepoName = QLineEdit(self.groupBoxHuggingFace)
        self.lineEditHuggingFaceRepoName.setObjectName(u"lineEditHuggingFaceRepoName")

        self.layoutHuggingFace.setWidget(1, QFormLayout.FieldRole, self.lineEditHuggingFaceRepoName)

        self.labelHuggingFaceToken = QLabel(self.groupBoxHuggingFace)
        self.labelHuggingFaceToken.setObjectName(u"labelHuggingFaceToken")

        self.layoutHuggingFace.setWidget(2, QFormLayout.LabelRole, self.labelHuggingFaceToken)

        self.lineEditHuggingFaceToken = QLineEdit(self.groupBoxHuggingFace)
        self.lineEditHuggingFaceToken.setObjectName(u"lineEditHuggingFaceToken")

        self.layoutHuggingFace.setWidget(2, QFormLayout.FieldRole, self.lineEditHuggingFaceToken)


        self.layoutScrollArea.addWidget(self.groupBoxHuggingFace)

        self.groupBoxLogging = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxLogging.setObjectName(u"groupBoxLogging")
        self.layoutLogging = QGridLayout(self.groupBoxLogging)
        self.layoutLogging.setObjectName(u"layoutLogging")
        self.labelLogLevel = QLabel(self.groupBoxLogging)
        self.labelLogLevel.setObjectName(u"labelLogLevel")

        self.layoutLogging.addWidget(self.labelLogLevel, 0, 0, 1, 1)

        self.comboBoxLogLevel = QComboBox(self.groupBoxLogging)
        self.comboBoxLogLevel.setObjectName(u"comboBoxLogLevel")

        self.layoutLogging.addWidget(self.comboBoxLogLevel, 0, 1, 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.log_PilePickerWidget = FilePickerWidget(self.groupBoxLogging)
        self.log_PilePickerWidget.setObjectName(u"log_PilePickerWidget")

        self.layoutLogging.addWidget(self.log_PilePickerWidget, 1, 0, 1, 1)


        self.layoutScrollArea.addWidget(self.groupBoxLogging)

        self.widgetButtons = QWidget(self.scrollAreaWidgetContents)
        self.widgetButtons.setObjectName(u"widgetButtons")
        self.layoutButtons = QHBoxLayout(self.widgetButtons)
        self.layoutButtons.setObjectName(u"layoutButtons")
        self.spacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layoutButtons.addItem(self.spacerButtons)

        self.buttonSave = QPushButton(self.widgetButtons)
        self.buttonSave.setObjectName(u"buttonSave")

        self.layoutButtons.addWidget(self.buttonSave)

        self.buttonSaveAs = QPushButton(self.widgetButtons)
        self.buttonSaveAs.setObjectName(u"buttonSaveAs")

        self.layoutButtons.addWidget(self.buttonSaveAs)


        self.layoutScrollArea.addWidget(self.widgetButtons)

        self.scrollAreaSettings.setWidget(self.scrollAreaWidgetContents)

        self.horizontalLayout.addWidget(self.scrollAreaSettings)


        self.retranslateUi(SettingspageWidget)

        QMetaObject.connectSlotsByName(SettingspageWidget)
    # setupUi

    def retranslateUi(self, SettingspageWidget):
        SettingspageWidget.setWindowTitle(QCoreApplication.translate("SettingspageWidget", u"Form", None))
        self.groupBoxFolders.setTitle(QCoreApplication.translate("SettingspageWidget", u"\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None))
        self.groupBoxAPI.setTitle(QCoreApplication.translate("SettingspageWidget", u"API\u8a2d\u5b9a", None))
        self.groupBoxOpenAI.setTitle(QCoreApplication.translate("SettingspageWidget", u"OpenAI", None))
        self.labelOpenAIApiKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.labelOpenAIModel.setText(QCoreApplication.translate("SettingspageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxGoogleVision.setTitle(QCoreApplication.translate("SettingspageWidget", u"Google Vision API", None))
        self.labelGoogleApiKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.labelGoogleApiModel.setText(QCoreApplication.translate("SettingspageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxAnthropic.setTitle(QCoreApplication.translate("SettingspageWidget", u"Anthropic", None))
        self.labelAnthropicApiKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.labelAnthropicApiModel.setText(QCoreApplication.translate("SettingspageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxHuggingFace.setTitle(QCoreApplication.translate("SettingspageWidget", u"Hugging Face", None))
        self.labelHuggingFaceUsername.setText(QCoreApplication.translate("SettingspageWidget", u"\u30e6\u30fc\u30b6\u30fc\u540d:", None))
        self.labelHuggingFaceRepoName.setText(QCoreApplication.translate("SettingspageWidget", u"\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None))
        self.labelHuggingFaceToken.setText(QCoreApplication.translate("SettingspageWidget", u"\u30c8\u30fc\u30af\u30f3:", None))
        self.groupBoxLogging.setTitle(QCoreApplication.translate("SettingspageWidget", u"\u30ed\u30b0\u8a2d\u5b9a", None))
        self.labelLogLevel.setText(QCoreApplication.translate("SettingspageWidget", u"\u30ed\u30b0\u30ec\u30d9\u30eb:", None))
        self.buttonSave.setText(QCoreApplication.translate("SettingspageWidget", u"\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(QCoreApplication.translate("SettingspageWidget", u"\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None))
    # retranslateUi

