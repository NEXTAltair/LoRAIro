# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SettingsWidget.ui'
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

class Ui_SettingsWidget(object):
    def setupUi(self, SettingsWidget):
        if not SettingsWidget.objectName():
            SettingsWidget.setObjectName(u"SettingsWidget")
        SettingsWidget.resize(718, 681)
        self.verticalLayout_2 = QVBoxLayout(SettingsWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.scrollAreaMain = QScrollArea(SettingsWidget)
        self.scrollAreaMain.setObjectName(u"scrollAreaMain")
        self.scrollAreaMain.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 694, 657))
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName(u"layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName(u"groupBoxFolders")
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName(u"layoutFolders")
        self.dirPickerOutput = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerOutput.setObjectName(u"dirPickerOutput")

        self.layoutFolders.addWidget(self.dirPickerOutput)

        self.dirPickerResponse = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerResponse.setObjectName(u"dirPickerResponse")

        self.layoutFolders.addWidget(self.dirPickerResponse)

        self.dirPickerEditedOutput = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerEditedOutput.setObjectName(u"dirPickerEditedOutput")

        self.layoutFolders.addWidget(self.dirPickerEditedOutput)


        self.layoutScrollArea.addWidget(self.groupBoxFolders)

        self.groupBoxApiSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxApiSettings.setObjectName(u"groupBoxApiSettings")
        self.formLayout = QFormLayout(self.groupBoxApiSettings)
        self.formLayout.setObjectName(u"formLayout")
        self.labelOpenAiKey = QLabel(self.groupBoxApiSettings)
        self.labelOpenAiKey.setObjectName(u"labelOpenAiKey")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.labelOpenAiKey)

        self.lineEditOpenAiKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditOpenAiKey.setObjectName(u"lineEditOpenAiKey")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.lineEditOpenAiKey)

        self.labelGoogleKey = QLabel(self.groupBoxApiSettings)
        self.labelGoogleKey.setObjectName(u"labelGoogleKey")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.labelGoogleKey)

        self.lineEditGoogleVisionKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditGoogleVisionKey.setObjectName(u"lineEditGoogleVisionKey")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.lineEditGoogleVisionKey)

        self.labelAnthropicKey = QLabel(self.groupBoxApiSettings)
        self.labelAnthropicKey.setObjectName(u"labelAnthropicKey")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.labelAnthropicKey)

        self.lineEditAnthropicKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditAnthropicKey.setObjectName(u"lineEditAnthropicKey")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.lineEditAnthropicKey)


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


        self.retranslateUi(SettingsWidget)

        QMetaObject.connectSlotsByName(SettingsWidget)
    # setupUi

    def retranslateUi(self, SettingsWidget):
        SettingsWidget.setWindowTitle(QCoreApplication.translate("SettingsWidget", u"Form", None))
        self.groupBoxFolders.setTitle(QCoreApplication.translate("SettingsWidget", u"\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None))
        self.groupBoxApiSettings.setTitle(QCoreApplication.translate("SettingsWidget", u"API KEY", None))
        self.labelOpenAiKey.setText(QCoreApplication.translate("SettingsWidget", u"OpenAI", None))
        self.labelGoogleKey.setText(QCoreApplication.translate("SettingsWidget", u"Google AI Studio", None))
        self.labelAnthropicKey.setText(QCoreApplication.translate("SettingsWidget", u"Anthropic", None))
        self.groupBoxHuggingFaceSettings.setTitle(QCoreApplication.translate("SettingsWidget", u"Hugging Face", None))
        self.labelHfUsername.setText(QCoreApplication.translate("SettingsWidget", u"\u30e6\u30fc\u30b6\u30fc\u540d:", None))
        self.labelHfRepoName.setText(QCoreApplication.translate("SettingsWidget", u"\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None))
        self.labelHfToken.setText(QCoreApplication.translate("SettingsWidget", u"\u30c8\u30fc\u30af\u30f3:", None))
        self.groupBoxLogSettings.setTitle(QCoreApplication.translate("SettingsWidget", u"\u30ed\u30b0\u8a2d\u5b9a", None))
        self.labelLogLevel.setText(QCoreApplication.translate("SettingsWidget", u"\u30ed\u30b0\u30ec\u30d9\u30eb:", None))
        self.buttonSave.setText(QCoreApplication.translate("SettingsWidget", u"\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(QCoreApplication.translate("SettingsWidget", u"\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None))
    # retranslateUi

