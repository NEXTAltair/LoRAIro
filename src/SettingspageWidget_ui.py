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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from FilePickerWidget import FilePickerWidget

class Ui_SettingspageWidget(object):
    def setupUi(self, SettingspageWidget):
        if not SettingspageWidget.objectName():
            SettingspageWidget.setObjectName(u"SettingspageWidget")
        SettingspageWidget.resize(705, 935)
        self.verticalLayout_2 = QVBoxLayout(SettingspageWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.scrollAreaMain = QScrollArea(SettingspageWidget)
        self.scrollAreaMain.setObjectName(u"scrollAreaMain")
        self.scrollAreaMain.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 681, 911))
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName(u"layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName(u"groupBoxFolders")
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName(u"layoutFolders")
        self.dirPickerOutput = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerOutput.setObjectName(u"dirPickerOutput")
        self.layoutOutputFolder = QHBoxLayout(self.dirPickerOutput)
        self.layoutOutputFolder.setObjectName(u"layoutOutputFolder")

        self.layoutFolders.addWidget(self.dirPickerOutput)

        self.dirPickerResponse = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerResponse.setObjectName(u"dirPickerResponse")
        self._2 = QHBoxLayout(self.dirPickerResponse)
        self._2.setObjectName(u"_2")

        self.layoutFolders.addWidget(self.dirPickerResponse)

        self.dirPickerEditedOutput = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerEditedOutput.setObjectName(u"dirPickerEditedOutput")
        self.layoutEditedOutputFolder = QHBoxLayout(self.dirPickerEditedOutput)
        self.layoutEditedOutputFolder.setObjectName(u"layoutEditedOutputFolder")

        self.layoutFolders.addWidget(self.dirPickerEditedOutput)


        self.layoutScrollArea.addWidget(self.groupBoxFolders)

        self.groupBoxApiSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxApiSettings.setObjectName(u"groupBoxApiSettings")
        self.layoutAPI = QVBoxLayout(self.groupBoxApiSettings)
        self.layoutAPI.setObjectName(u"layoutAPI")
        self.groupBoxOpenAI = QGroupBox(self.groupBoxApiSettings)
        self.groupBoxOpenAI.setObjectName(u"groupBoxOpenAI")
        self.layoutOpenAI = QFormLayout(self.groupBoxOpenAI)
        self.layoutOpenAI.setObjectName(u"layoutOpenAI")
        self.labelOpenAiKey = QLabel(self.groupBoxOpenAI)
        self.labelOpenAiKey.setObjectName(u"labelOpenAiKey")

        self.layoutOpenAI.setWidget(0, QFormLayout.LabelRole, self.labelOpenAiKey)

        self.lineEditOpenAiKey = QLineEdit(self.groupBoxOpenAI)
        self.lineEditOpenAiKey.setObjectName(u"lineEditOpenAiKey")

        self.layoutOpenAI.setWidget(0, QFormLayout.FieldRole, self.lineEditOpenAiKey)


        self.layoutAPI.addWidget(self.groupBoxOpenAI)

        self.groupBoxGoogleVision = QGroupBox(self.groupBoxApiSettings)
        self.groupBoxGoogleVision.setObjectName(u"groupBoxGoogleVision")
        self.layoutGoogleVision = QFormLayout(self.groupBoxGoogleVision)
        self.layoutGoogleVision.setObjectName(u"layoutGoogleVision")
        self.labelGoogleKey = QLabel(self.groupBoxGoogleVision)
        self.labelGoogleKey.setObjectName(u"labelGoogleKey")

        self.layoutGoogleVision.setWidget(0, QFormLayout.LabelRole, self.labelGoogleKey)

        self.lineEditGoogleVisionKey = QLineEdit(self.groupBoxGoogleVision)
        self.lineEditGoogleVisionKey.setObjectName(u"lineEditGoogleVisionKey")

        self.layoutGoogleVision.setWidget(0, QFormLayout.FieldRole, self.lineEditGoogleVisionKey)


        self.layoutAPI.addWidget(self.groupBoxGoogleVision)

        self.groupBoxAnthropic = QGroupBox(self.groupBoxApiSettings)
        self.groupBoxAnthropic.setObjectName(u"groupBoxAnthropic")
        self.layoutAnthropic = QFormLayout(self.groupBoxAnthropic)
        self.layoutAnthropic.setObjectName(u"layoutAnthropic")
        self.labelAnthropicKey = QLabel(self.groupBoxAnthropic)
        self.labelAnthropicKey.setObjectName(u"labelAnthropicKey")

        self.layoutAnthropic.setWidget(0, QFormLayout.LabelRole, self.labelAnthropicKey)

        self.lineEditAnthropicKey = QLineEdit(self.groupBoxAnthropic)
        self.lineEditAnthropicKey.setObjectName(u"lineEditAnthropicKey")

        self.layoutAnthropic.setWidget(0, QFormLayout.FieldRole, self.lineEditAnthropicKey)


        self.layoutAPI.addWidget(self.groupBoxAnthropic)


        self.layoutScrollArea.addWidget(self.groupBoxApiSettings)

        self.groupBoxHuggingFaceSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxHuggingFaceSettings.setObjectName(u"groupBoxHuggingFaceSettings")
        self.layoutHuggingFace = QFormLayout(self.groupBoxHuggingFaceSettings)
        self.layoutHuggingFace.setObjectName(u"layoutHuggingFace")
        self.labelHfUsername = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfUsername.setObjectName(u"labelHfUsername")

        self.layoutHuggingFace.setWidget(0, QFormLayout.LabelRole, self.labelHfUsername)

        self.lineEditHfUsername = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfUsername.setObjectName(u"lineEditHfUsername")

        self.layoutHuggingFace.setWidget(0, QFormLayout.FieldRole, self.lineEditHfUsername)

        self.labelHfRepoName = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfRepoName.setObjectName(u"labelHfRepoName")

        self.layoutHuggingFace.setWidget(1, QFormLayout.LabelRole, self.labelHfRepoName)

        self.lineEditHfRepoName = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfRepoName.setObjectName(u"lineEditHfRepoName")

        self.layoutHuggingFace.setWidget(1, QFormLayout.FieldRole, self.lineEditHfRepoName)

        self.labelHfToken = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfToken.setObjectName(u"labelHfToken")

        self.layoutHuggingFace.setWidget(2, QFormLayout.LabelRole, self.labelHfToken)

        self.lineEditHfToken = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfToken.setObjectName(u"lineEditHfToken")

        self.layoutHuggingFace.setWidget(2, QFormLayout.FieldRole, self.lineEditHfToken)


        self.layoutScrollArea.addWidget(self.groupBoxHuggingFaceSettings)

        self.groupBoxLogSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxLogSettings.setObjectName(u"groupBoxLogSettings")
        self.verticalLayout = QVBoxLayout(self.groupBoxLogSettings)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.LoglLevel = QWidget(self.groupBoxLogSettings)
        self.LoglLevel.setObjectName(u"LoglLevel")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.LoglLevel.sizePolicy().hasHeightForWidth())
        self.LoglLevel.setSizePolicy(sizePolicy)
        self.horizontalLayout_2 = QHBoxLayout(self.LoglLevel)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.labelLogLevel = QLabel(self.LoglLevel)
        self.labelLogLevel.setObjectName(u"labelLogLevel")

        self.horizontalLayout_2.addWidget(self.labelLogLevel)

        self.comboBoxLogLevel = QComboBox(self.LoglLevel)
        self.comboBoxLogLevel.setObjectName(u"comboBoxLogLevel")

        self.horizontalLayout_2.addWidget(self.comboBoxLogLevel)

        self.HSpacerLogLevel = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.HSpacerLogLevel)


        self.verticalLayout.addWidget(self.LoglLevel)

        self.filePickerLogFile = FilePickerWidget(self.groupBoxLogSettings)
        self.filePickerLogFile.setObjectName(u"filePickerLogFile")
        sizePolicy.setHeightForWidth(self.filePickerLogFile.sizePolicy().hasHeightForWidth())
        self.filePickerLogFile.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.filePickerLogFile)


        self.layoutScrollArea.addWidget(self.groupBoxLogSettings)

        self.SaveSettings = QWidget(self.scrollAreaWidgetContents)
        self.SaveSettings.setObjectName(u"SaveSettings")
        self.layoutButtons = QHBoxLayout(self.SaveSettings)
        self.layoutButtons.setObjectName(u"layoutButtons")
        self.HSpacerSaveButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layoutButtons.addItem(self.HSpacerSaveButtons)

        self.buttonSave = QPushButton(self.SaveSettings)
        self.buttonSave.setObjectName(u"buttonSave")

        self.layoutButtons.addWidget(self.buttonSave)

        self.buttonSaveAs = QPushButton(self.SaveSettings)
        self.buttonSaveAs.setObjectName(u"buttonSaveAs")

        self.layoutButtons.addWidget(self.buttonSaveAs)


        self.layoutScrollArea.addWidget(self.SaveSettings)

        self.scrollAreaMain.setWidget(self.scrollAreaWidgetContents)

        self.verticalLayout_2.addWidget(self.scrollAreaMain)


        self.retranslateUi(SettingspageWidget)

        QMetaObject.connectSlotsByName(SettingspageWidget)
    # setupUi

    def retranslateUi(self, SettingspageWidget):
        SettingspageWidget.setWindowTitle(QCoreApplication.translate("SettingspageWidget", u"Form", None))
        self.groupBoxFolders.setTitle(QCoreApplication.translate("SettingspageWidget", u"\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None))
        self.groupBoxApiSettings.setTitle(QCoreApplication.translate("SettingspageWidget", u"API\u8a2d\u5b9a", None))
        self.groupBoxOpenAI.setTitle(QCoreApplication.translate("SettingspageWidget", u"OpenAI", None))
        self.labelOpenAiKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.groupBoxGoogleVision.setTitle(QCoreApplication.translate("SettingspageWidget", u"Google Vision API", None))
        self.labelGoogleKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.groupBoxAnthropic.setTitle(QCoreApplication.translate("SettingspageWidget", u"Anthropic", None))
        self.labelAnthropicKey.setText(QCoreApplication.translate("SettingspageWidget", u"API\u30ad\u30fc:", None))
        self.groupBoxHuggingFaceSettings.setTitle(QCoreApplication.translate("SettingspageWidget", u"Hugging Face", None))
        self.labelHfUsername.setText(QCoreApplication.translate("SettingspageWidget", u"\u30e6\u30fc\u30b6\u30fc\u540d:", None))
        self.labelHfRepoName.setText(QCoreApplication.translate("SettingspageWidget", u"\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None))
        self.labelHfToken.setText(QCoreApplication.translate("SettingspageWidget", u"\u30c8\u30fc\u30af\u30f3:", None))
        self.groupBoxLogSettings.setTitle(QCoreApplication.translate("SettingspageWidget", u"\u30ed\u30b0\u8a2d\u5b9a", None))
        self.labelLogLevel.setText(QCoreApplication.translate("SettingspageWidget", u"\u30ed\u30b0\u30ec\u30d9\u30eb:", None))
        self.buttonSave.setText(QCoreApplication.translate("SettingspageWidget", u"\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(QCoreApplication.translate("SettingspageWidget", u"\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None))
    # retranslateUi

