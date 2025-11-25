# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ConfigurationWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.10.0
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

from ..widgets.directory_picker import DirectoryPickerWidget
from ..widgets.file_picker import FilePickerWidget

class Ui_ConfigurationWindow(object):
    def setupUi(self, ConfigurationWindow):
        if not ConfigurationWindow.objectName():
            ConfigurationWindow.setObjectName(u"ConfigurationWindow")
        ConfigurationWindow.resize(718, 681)
        self.verticalLayout_2 = QVBoxLayout(ConfigurationWindow)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.scrollAreaMain = QScrollArea(ConfigurationWindow)
        self.scrollAreaMain.setObjectName(u"scrollAreaMain")
        self.scrollAreaMain.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 694, 657))
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName(u"layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName(u"groupBoxFolders")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBoxFolders.sizePolicy().hasHeightForWidth())
        self.groupBoxFolders.setSizePolicy(sizePolicy)
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName(u"layoutFolders")
        self.dirPickerExportDir = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerExportDir.setObjectName(u"dirPickerExportDir")

        self.layoutFolders.addWidget(self.dirPickerExportDir)

        self.dirPickerBatchResults = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerBatchResults.setObjectName(u"dirPickerBatchResults")

        self.layoutFolders.addWidget(self.dirPickerBatchResults)

        self.dirPickerDatabaseDir = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerDatabaseDir.setObjectName(u"dirPickerDatabaseDir")

        self.layoutFolders.addWidget(self.dirPickerDatabaseDir)


        self.layoutScrollArea.addWidget(self.groupBoxFolders)

        self.groupBoxApiSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxApiSettings.setObjectName(u"groupBoxApiSettings")
        self.formLayout = QFormLayout(self.groupBoxApiSettings)
        self.formLayout.setObjectName(u"formLayout")
        self.labelOpenAiKey = QLabel(self.groupBoxApiSettings)
        self.labelOpenAiKey.setObjectName(u"labelOpenAiKey")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelOpenAiKey.sizePolicy().hasHeightForWidth())
        self.labelOpenAiKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelOpenAiKey)

        self.lineEditOpenAiKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditOpenAiKey.setObjectName(u"lineEditOpenAiKey")
        sizePolicy.setHeightForWidth(self.lineEditOpenAiKey.sizePolicy().hasHeightForWidth())
        self.lineEditOpenAiKey.setSizePolicy(sizePolicy)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditOpenAiKey)

        self.labelGoogleKey = QLabel(self.groupBoxApiSettings)
        self.labelGoogleKey.setObjectName(u"labelGoogleKey")
        sizePolicy1.setHeightForWidth(self.labelGoogleKey.sizePolicy().hasHeightForWidth())
        self.labelGoogleKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelGoogleKey)

        self.lineEditGoogleVisionKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditGoogleVisionKey.setObjectName(u"lineEditGoogleVisionKey")
        sizePolicy.setHeightForWidth(self.lineEditGoogleVisionKey.sizePolicy().hasHeightForWidth())
        self.lineEditGoogleVisionKey.setSizePolicy(sizePolicy)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditGoogleVisionKey)

        self.labelAnthropicKey = QLabel(self.groupBoxApiSettings)
        self.labelAnthropicKey.setObjectName(u"labelAnthropicKey")
        sizePolicy1.setHeightForWidth(self.labelAnthropicKey.sizePolicy().hasHeightForWidth())
        self.labelAnthropicKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.labelAnthropicKey)

        self.lineEditAnthropicKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditAnthropicKey.setObjectName(u"lineEditAnthropicKey")
        sizePolicy.setHeightForWidth(self.lineEditAnthropicKey.sizePolicy().hasHeightForWidth())
        self.lineEditAnthropicKey.setSizePolicy(sizePolicy)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lineEditAnthropicKey)


        self.layoutScrollArea.addWidget(self.groupBoxApiSettings)

        self.groupBoxHuggingFaceSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxHuggingFaceSettings.setObjectName(u"groupBoxHuggingFaceSettings")
        self.layoutHuggingFace = QFormLayout(self.groupBoxHuggingFaceSettings)
        self.layoutHuggingFace.setObjectName(u"layoutHuggingFace")
        self.labelHfUsername = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfUsername.setObjectName(u"labelHfUsername")
        sizePolicy1.setHeightForWidth(self.labelHfUsername.sizePolicy().hasHeightForWidth())
        self.labelHfUsername.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelHfUsername)

        self.lineEditHfUsername = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfUsername.setObjectName(u"lineEditHfUsername")
        sizePolicy.setHeightForWidth(self.lineEditHfUsername.sizePolicy().hasHeightForWidth())
        self.lineEditHfUsername.setSizePolicy(sizePolicy)

        self.layoutHuggingFace.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditHfUsername)

        self.labelHfRepoName = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfRepoName.setObjectName(u"labelHfRepoName")
        sizePolicy1.setHeightForWidth(self.labelHfRepoName.sizePolicy().hasHeightForWidth())
        self.labelHfRepoName.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelHfRepoName)

        self.lineEditHfRepoName = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfRepoName.setObjectName(u"lineEditHfRepoName")
        sizePolicy.setHeightForWidth(self.lineEditHfRepoName.sizePolicy().hasHeightForWidth())
        self.lineEditHfRepoName.setSizePolicy(sizePolicy)

        self.layoutHuggingFace.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditHfRepoName)

        self.labelHfToken = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfToken.setObjectName(u"labelHfToken")
        sizePolicy1.setHeightForWidth(self.labelHfToken.sizePolicy().hasHeightForWidth())
        self.labelHfToken.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(2, QFormLayout.ItemRole.LabelRole, self.labelHfToken)

        self.lineEditHfToken = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfToken.setObjectName(u"lineEditHfToken")
        sizePolicy.setHeightForWidth(self.lineEditHfToken.sizePolicy().hasHeightForWidth())
        self.lineEditHfToken.setSizePolicy(sizePolicy)

        self.layoutHuggingFace.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lineEditHfToken)


        self.layoutScrollArea.addWidget(self.groupBoxHuggingFaceSettings)

        self.groupBoxLogSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxLogSettings.setObjectName(u"groupBoxLogSettings")
        self.verticalLayout = QVBoxLayout(self.groupBoxLogSettings)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.LoglLevel = QWidget(self.groupBoxLogSettings)
        self.LoglLevel.setObjectName(u"LoglLevel")
        sizePolicy.setHeightForWidth(self.LoglLevel.sizePolicy().hasHeightForWidth())
        self.LoglLevel.setSizePolicy(sizePolicy)
        self.horizontalLayout_2 = QHBoxLayout(self.LoglLevel)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.labelLogLevel = QLabel(self.LoglLevel)
        self.labelLogLevel.setObjectName(u"labelLogLevel")
        sizePolicy1.setHeightForWidth(self.labelLogLevel.sizePolicy().hasHeightForWidth())
        self.labelLogLevel.setSizePolicy(sizePolicy1)

        self.horizontalLayout_2.addWidget(self.labelLogLevel)

        self.comboBoxLogLevel = QComboBox(self.LoglLevel)
        self.comboBoxLogLevel.setObjectName(u"comboBoxLogLevel")
        sizePolicy.setHeightForWidth(self.comboBoxLogLevel.sizePolicy().hasHeightForWidth())
        self.comboBoxLogLevel.setSizePolicy(sizePolicy)

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
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.buttonSave.sizePolicy().hasHeightForWidth())
        self.buttonSave.setSizePolicy(sizePolicy2)

        self.layoutButtons.addWidget(self.buttonSave)

        self.buttonSaveAs = QPushButton(self.SaveSettings)
        self.buttonSaveAs.setObjectName(u"buttonSaveAs")
        sizePolicy2.setHeightForWidth(self.buttonSaveAs.sizePolicy().hasHeightForWidth())
        self.buttonSaveAs.setSizePolicy(sizePolicy2)

        self.layoutButtons.addWidget(self.buttonSaveAs)


        self.layoutScrollArea.addWidget(self.SaveSettings)

        self.scrollAreaMain.setWidget(self.scrollAreaWidgetContents)

        self.verticalLayout_2.addWidget(self.scrollAreaMain)


        self.retranslateUi(ConfigurationWindow)

        QMetaObject.connectSlotsByName(ConfigurationWindow)
    # setupUi

    def retranslateUi(self, ConfigurationWindow):
        ConfigurationWindow.setWindowTitle(QCoreApplication.translate("ConfigurationWindow", u"Form", None))
        self.groupBoxFolders.setTitle(QCoreApplication.translate("ConfigurationWindow", u"\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None))
        self.groupBoxApiSettings.setTitle(QCoreApplication.translate("ConfigurationWindow", u"API KEY", None))
        self.labelOpenAiKey.setText(QCoreApplication.translate("ConfigurationWindow", u"OpenAI", None))
        self.labelGoogleKey.setText(QCoreApplication.translate("ConfigurationWindow", u"Google AI Studio", None))
        self.labelAnthropicKey.setText(QCoreApplication.translate("ConfigurationWindow", u"Anthropic", None))
        self.groupBoxHuggingFaceSettings.setTitle(QCoreApplication.translate("ConfigurationWindow", u"Hugging Face", None))
        self.labelHfUsername.setText(QCoreApplication.translate("ConfigurationWindow", u"\u30e6\u30fc\u30b6\u30fc\u540d:", None))
        self.labelHfRepoName.setText(QCoreApplication.translate("ConfigurationWindow", u"\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None))
        self.labelHfToken.setText(QCoreApplication.translate("ConfigurationWindow", u"\u30c8\u30fc\u30af\u30f3:", None))
        self.groupBoxLogSettings.setTitle(QCoreApplication.translate("ConfigurationWindow", u"\u30ed\u30b0\u8a2d\u5b9a", None))
        self.labelLogLevel.setText(QCoreApplication.translate("ConfigurationWindow", u"\u30ed\u30b0\u30ec\u30d9\u30eb:", None))
        self.buttonSave.setText(QCoreApplication.translate("ConfigurationWindow", u"\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(QCoreApplication.translate("ConfigurationWindow", u"\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None))
    # retranslateUi

