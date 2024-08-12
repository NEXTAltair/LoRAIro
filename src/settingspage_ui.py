# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'settingspage.ui'
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

class Ui_SettingsPageWidget(object):
    def setupUi(self, SettingsPageWidget):
        if not SettingsPageWidget.objectName():
            SettingsPageWidget.setObjectName(u"SettingsPageWidget")
        SettingsPageWidget.resize(797, 930)
        self.mainLayout = QVBoxLayout(SettingsPageWidget)
        self.mainLayout.setObjectName(u"mainLayout")
        self.labelSettingsTitle = QLabel(SettingsPageWidget)
        self.labelSettingsTitle.setObjectName(u"labelSettingsTitle")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.labelSettingsTitle.setFont(font)

        self.mainLayout.addWidget(self.labelSettingsTitle)

        self.scrollAreaSettings = QScrollArea(SettingsPageWidget)
        self.scrollAreaSettings.setObjectName(u"scrollAreaSettings")
        self.scrollAreaSettings.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName(u"layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName(u"groupBoxFolders")
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName(u"layoutFolders")
        self.layoutDatasetFolder = QHBoxLayout()
        self.layoutDatasetFolder.setObjectName(u"layoutDatasetFolder")
        self.labelDatasetFolder = QLabel(self.groupBoxFolders)
        self.labelDatasetFolder.setObjectName(u"labelDatasetFolder")

        self.layoutDatasetFolder.addWidget(self.labelDatasetFolder)

        self.lineEditDatasetFolder = QLineEdit(self.groupBoxFolders)
        self.lineEditDatasetFolder.setObjectName(u"lineEditDatasetFolder")

        self.layoutDatasetFolder.addWidget(self.lineEditDatasetFolder)

        self.buttonBrowseDataset = QPushButton(self.groupBoxFolders)
        self.buttonBrowseDataset.setObjectName(u"buttonBrowseDataset")

        self.layoutDatasetFolder.addWidget(self.buttonBrowseDataset)


        self.layoutFolders.addLayout(self.layoutDatasetFolder)

        self.layoutOutputFolder = QHBoxLayout()
        self.layoutOutputFolder.setObjectName(u"layoutOutputFolder")
        self.labelOutputFolder = QLabel(self.groupBoxFolders)
        self.labelOutputFolder.setObjectName(u"labelOutputFolder")

        self.layoutOutputFolder.addWidget(self.labelOutputFolder)

        self.lineEditOutputFolder = QLineEdit(self.groupBoxFolders)
        self.lineEditOutputFolder.setObjectName(u"lineEditOutputFolder")

        self.layoutOutputFolder.addWidget(self.lineEditOutputFolder)

        self.buttonBrowseOutput = QPushButton(self.groupBoxFolders)
        self.buttonBrowseOutput.setObjectName(u"buttonBrowseOutput")

        self.layoutOutputFolder.addWidget(self.buttonBrowseOutput)


        self.layoutFolders.addLayout(self.layoutOutputFolder)

        self.layoutResponseFolder = QHBoxLayout()
        self.layoutResponseFolder.setObjectName(u"layoutResponseFolder")
        self.labelResponseFolder = QLabel(self.groupBoxFolders)
        self.labelResponseFolder.setObjectName(u"labelResponseFolder")

        self.layoutResponseFolder.addWidget(self.labelResponseFolder)

        self.lineEditResponseFolder = QLineEdit(self.groupBoxFolders)
        self.lineEditResponseFolder.setObjectName(u"lineEditResponseFolder")

        self.layoutResponseFolder.addWidget(self.lineEditResponseFolder)

        self.buttonBrowseResponse = QPushButton(self.groupBoxFolders)
        self.buttonBrowseResponse.setObjectName(u"buttonBrowseResponse")

        self.layoutResponseFolder.addWidget(self.buttonBrowseResponse)


        self.layoutFolders.addLayout(self.layoutResponseFolder)

        self.layoutEditedOutputFolder = QHBoxLayout()
        self.layoutEditedOutputFolder.setObjectName(u"layoutEditedOutputFolder")
        self.labelEditedOutputFolder = QLabel(self.groupBoxFolders)
        self.labelEditedOutputFolder.setObjectName(u"labelEditedOutputFolder")

        self.layoutEditedOutputFolder.addWidget(self.labelEditedOutputFolder)

        self.lineEditEditedOutputFolder = QLineEdit(self.groupBoxFolders)
        self.lineEditEditedOutputFolder.setObjectName(u"lineEditEditedOutputFolder")

        self.layoutEditedOutputFolder.addWidget(self.lineEditEditedOutputFolder)

        self.buttonBrowseEditedOutput = QPushButton(self.groupBoxFolders)
        self.buttonBrowseEditedOutput.setObjectName(u"buttonBrowseEditedOutput")

        self.layoutEditedOutputFolder.addWidget(self.buttonBrowseEditedOutput)


        self.layoutFolders.addLayout(self.layoutEditedOutputFolder)


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

        self.layoutLogging.addWidget(self.comboBoxLogLevel, 0, 1, 1, 1)

        self.labelLogFile = QLabel(self.groupBoxLogging)
        self.labelLogFile.setObjectName(u"labelLogFile")

        self.layoutLogging.addWidget(self.labelLogFile, 1, 0, 1, 1)

        self.lineEditLogFile = QLineEdit(self.groupBoxLogging)
        self.lineEditLogFile.setObjectName(u"lineEditLogFile")

        self.layoutLogging.addWidget(self.lineEditLogFile, 1, 1, 1, 1)

        self.buttonBrowseLogFile = QPushButton(self.groupBoxLogging)
        self.buttonBrowseLogFile.setObjectName(u"buttonBrowseLogFile")

        self.layoutLogging.addWidget(self.buttonBrowseLogFile, 1, 2, 1, 1)


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

        self.mainLayout.addWidget(self.scrollAreaSettings)


        self.retranslateUi(SettingsPageWidget)

        QMetaObject.connectSlotsByName(SettingsPageWidget)
    # setupUi

    def retranslateUi(self, SettingsPageWidget):
        SettingsPageWidget.setWindowTitle(QCoreApplication.translate("SettingsPageWidget", u"\u8a2d\u5b9a", None))
        self.labelSettingsTitle.setText(QCoreApplication.translate("SettingsPageWidget", u"\u8a2d\u5b9a", None))
        self.groupBoxFolders.setTitle(QCoreApplication.translate("SettingsPageWidget", u"\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None))
        self.labelDatasetFolder.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30d5\u30a9\u30eb\u30c0:", None))
        self.buttonBrowseDataset.setText(QCoreApplication.translate("SettingsPageWidget", u"\u53c2\u7167", None))
        self.labelOutputFolder.setText(QCoreApplication.translate("SettingsPageWidget", u"\u51fa\u529b\u30d5\u30a9\u30eb\u30c0:", None))
        self.buttonBrowseOutput.setText(QCoreApplication.translate("SettingsPageWidget", u"\u53c2\u7167", None))
        self.labelResponseFolder.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30ec\u30b9\u30dd\u30f3\u30b9\u30d5\u30a9\u30eb\u30c0:", None))
        self.buttonBrowseResponse.setText(QCoreApplication.translate("SettingsPageWidget", u"\u53c2\u7167", None))
        self.labelEditedOutputFolder.setText(QCoreApplication.translate("SettingsPageWidget", u"\u7de8\u96c6\u6e08\u307f\u30d5\u30a1\u30a4\u30eb\u51fa\u529b\u30d5\u30a9\u30eb\u30c0:", None))
        self.buttonBrowseEditedOutput.setText(QCoreApplication.translate("SettingsPageWidget", u"\u53c2\u7167", None))
        self.groupBoxAPI.setTitle(QCoreApplication.translate("SettingsPageWidget", u"API\u8a2d\u5b9a", None))
        self.groupBoxOpenAI.setTitle(QCoreApplication.translate("SettingsPageWidget", u"OpenAI", None))
        self.labelOpenAIApiKey.setText(QCoreApplication.translate("SettingsPageWidget", u"API\u30ad\u30fc:", None))
        self.labelOpenAIModel.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxGoogleVision.setTitle(QCoreApplication.translate("SettingsPageWidget", u"Google Vision API", None))
        self.labelGoogleApiKey.setText(QCoreApplication.translate("SettingsPageWidget", u"API\u30ad\u30fc:", None))
        self.labelGoogleApiModel.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxAnthropic.setTitle(QCoreApplication.translate("SettingsPageWidget", u"Anthropic", None))
        self.labelAnthropicApiKey.setText(QCoreApplication.translate("SettingsPageWidget", u"API\u30ad\u30fc:", None))
        self.labelAnthropicApiModel.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30e2\u30c7\u30eb:", None))
        self.groupBoxHuggingFace.setTitle(QCoreApplication.translate("SettingsPageWidget", u"Hugging Face", None))
        self.labelHuggingFaceUsername.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30e6\u30fc\u30b6\u30fc\u540d:", None))
        self.labelHuggingFaceRepoName.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None))
        self.labelHuggingFaceToken.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30c8\u30fc\u30af\u30f3:", None))
        self.groupBoxLogging.setTitle(QCoreApplication.translate("SettingsPageWidget", u"\u30ed\u30b0\u8a2d\u5b9a", None))
        self.labelLogLevel.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30ed\u30b0\u30ec\u30d9\u30eb:", None))
        self.labelLogFile.setText(QCoreApplication.translate("SettingsPageWidget", u"\u30ed\u30b0\u30d5\u30a1\u30a4\u30eb:", None))
        self.buttonBrowseLogFile.setText(QCoreApplication.translate("SettingsPageWidget", u"\u53c2\u7167", None))
        self.buttonSave.setText(QCoreApplication.translate("SettingsPageWidget", u"\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(QCoreApplication.translate("SettingsPageWidget", u"\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None))
    # retranslateUi

