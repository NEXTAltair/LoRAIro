################################################################################
## Form generated from reading UI file 'ConfigurationWindow.ui'
##
## Created by: Qt User Interface Compiler version 6.9.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTime,
    QUrl,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ..widgets.directory_picker import DirectoryPickerWidget
from ..widgets.file_picker import FilePickerWidget


class Ui_ConfigurationWindow:
    def setupUi(self, ConfigurationWindow):
        if not ConfigurationWindow.objectName():
            ConfigurationWindow.setObjectName("ConfigurationWindow")
        ConfigurationWindow.resize(718, 681)
        self.verticalLayout_2 = QVBoxLayout(ConfigurationWindow)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.scrollAreaMain = QScrollArea(ConfigurationWindow)
        self.scrollAreaMain.setObjectName("scrollAreaMain")
        self.scrollAreaMain.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 694, 657))
        self.layoutScrollArea = QVBoxLayout(self.scrollAreaWidgetContents)
        self.layoutScrollArea.setObjectName("layoutScrollArea")
        self.groupBoxFolders = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxFolders.setObjectName("groupBoxFolders")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBoxFolders.sizePolicy().hasHeightForWidth())
        self.groupBoxFolders.setSizePolicy(sizePolicy)
        self.layoutFolders = QVBoxLayout(self.groupBoxFolders)
        self.layoutFolders.setObjectName("layoutFolders")
        self.dirPickerExportDir = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerExportDir.setObjectName("dirPickerExportDir")

        self.layoutFolders.addWidget(self.dirPickerExportDir)

        self.dirPickerBatchResults = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerBatchResults.setObjectName("dirPickerBatchResults")

        self.layoutFolders.addWidget(self.dirPickerBatchResults)

        self.dirPickerDatabaseDir = DirectoryPickerWidget(self.groupBoxFolders)
        self.dirPickerDatabaseDir.setObjectName("dirPickerDatabaseDir")

        self.layoutFolders.addWidget(self.dirPickerDatabaseDir)

        self.layoutScrollArea.addWidget(self.groupBoxFolders)

        self.groupBoxApiSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxApiSettings.setObjectName("groupBoxApiSettings")
        self.formLayout = QFormLayout(self.groupBoxApiSettings)
        self.formLayout.setObjectName("formLayout")
        self.labelOpenAiKey = QLabel(self.groupBoxApiSettings)
        self.labelOpenAiKey.setObjectName("labelOpenAiKey")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelOpenAiKey.sizePolicy().hasHeightForWidth())
        self.labelOpenAiKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelOpenAiKey)

        self.lineEditOpenAiKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditOpenAiKey.setObjectName("lineEditOpenAiKey")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.lineEditOpenAiKey.sizePolicy().hasHeightForWidth())
        self.lineEditOpenAiKey.setSizePolicy(sizePolicy2)

        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditOpenAiKey)

        self.labelGoogleKey = QLabel(self.groupBoxApiSettings)
        self.labelGoogleKey.setObjectName("labelGoogleKey")
        sizePolicy1.setHeightForWidth(self.labelGoogleKey.sizePolicy().hasHeightForWidth())
        self.labelGoogleKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelGoogleKey)

        self.lineEditGoogleVisionKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditGoogleVisionKey.setObjectName("lineEditGoogleVisionKey")
        sizePolicy2.setHeightForWidth(self.lineEditGoogleVisionKey.sizePolicy().hasHeightForWidth())
        self.lineEditGoogleVisionKey.setSizePolicy(sizePolicy2)

        self.formLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditGoogleVisionKey)

        self.labelAnthropicKey = QLabel(self.groupBoxApiSettings)
        self.labelAnthropicKey.setObjectName("labelAnthropicKey")
        sizePolicy1.setHeightForWidth(self.labelAnthropicKey.sizePolicy().hasHeightForWidth())
        self.labelAnthropicKey.setSizePolicy(sizePolicy1)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.LabelRole, self.labelAnthropicKey)

        self.lineEditAnthropicKey = QLineEdit(self.groupBoxApiSettings)
        self.lineEditAnthropicKey.setObjectName("lineEditAnthropicKey")
        sizePolicy2.setHeightForWidth(self.lineEditAnthropicKey.sizePolicy().hasHeightForWidth())
        self.lineEditAnthropicKey.setSizePolicy(sizePolicy2)

        self.formLayout.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lineEditAnthropicKey)

        self.layoutScrollArea.addWidget(self.groupBoxApiSettings)

        self.groupBoxHuggingFaceSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxHuggingFaceSettings.setObjectName("groupBoxHuggingFaceSettings")
        self.layoutHuggingFace = QFormLayout(self.groupBoxHuggingFaceSettings)
        self.layoutHuggingFace.setObjectName("layoutHuggingFace")
        self.labelHfUsername = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfUsername.setObjectName("labelHfUsername")
        sizePolicy1.setHeightForWidth(self.labelHfUsername.sizePolicy().hasHeightForWidth())
        self.labelHfUsername.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelHfUsername)

        self.lineEditHfUsername = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfUsername.setObjectName("lineEditHfUsername")
        sizePolicy2.setHeightForWidth(self.lineEditHfUsername.sizePolicy().hasHeightForWidth())
        self.lineEditHfUsername.setSizePolicy(sizePolicy2)

        self.layoutHuggingFace.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditHfUsername)

        self.labelHfRepoName = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfRepoName.setObjectName("labelHfRepoName")
        sizePolicy1.setHeightForWidth(self.labelHfRepoName.sizePolicy().hasHeightForWidth())
        self.labelHfRepoName.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelHfRepoName)

        self.lineEditHfRepoName = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfRepoName.setObjectName("lineEditHfRepoName")
        sizePolicy2.setHeightForWidth(self.lineEditHfRepoName.sizePolicy().hasHeightForWidth())
        self.lineEditHfRepoName.setSizePolicy(sizePolicy2)

        self.layoutHuggingFace.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditHfRepoName)

        self.labelHfToken = QLabel(self.groupBoxHuggingFaceSettings)
        self.labelHfToken.setObjectName("labelHfToken")
        sizePolicy1.setHeightForWidth(self.labelHfToken.sizePolicy().hasHeightForWidth())
        self.labelHfToken.setSizePolicy(sizePolicy1)

        self.layoutHuggingFace.setWidget(2, QFormLayout.ItemRole.LabelRole, self.labelHfToken)

        self.lineEditHfToken = QLineEdit(self.groupBoxHuggingFaceSettings)
        self.lineEditHfToken.setObjectName("lineEditHfToken")
        sizePolicy2.setHeightForWidth(self.lineEditHfToken.sizePolicy().hasHeightForWidth())
        self.lineEditHfToken.setSizePolicy(sizePolicy2)

        self.layoutHuggingFace.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lineEditHfToken)

        self.layoutScrollArea.addWidget(self.groupBoxHuggingFaceSettings)

        self.groupBoxLogSettings = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBoxLogSettings.setObjectName("groupBoxLogSettings")
        self.verticalLayout = QVBoxLayout(self.groupBoxLogSettings)
        self.verticalLayout.setObjectName("verticalLayout")
        self.LoglLevel = QWidget(self.groupBoxLogSettings)
        self.LoglLevel.setObjectName("LoglLevel")
        sizePolicy2.setHeightForWidth(self.LoglLevel.sizePolicy().hasHeightForWidth())
        self.LoglLevel.setSizePolicy(sizePolicy2)
        self.horizontalLayout_2 = QHBoxLayout(self.LoglLevel)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.labelLogLevel = QLabel(self.LoglLevel)
        self.labelLogLevel.setObjectName("labelLogLevel")
        sizePolicy1.setHeightForWidth(self.labelLogLevel.sizePolicy().hasHeightForWidth())
        self.labelLogLevel.setSizePolicy(sizePolicy1)

        self.horizontalLayout_2.addWidget(self.labelLogLevel)

        self.comboBoxLogLevel = QComboBox(self.LoglLevel)
        self.comboBoxLogLevel.setObjectName("comboBoxLogLevel")
        sizePolicy2.setHeightForWidth(self.comboBoxLogLevel.sizePolicy().hasHeightForWidth())
        self.comboBoxLogLevel.setSizePolicy(sizePolicy2)

        self.horizontalLayout_2.addWidget(self.comboBoxLogLevel)

        self.HSpacerLogLevel = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_2.addItem(self.HSpacerLogLevel)

        self.verticalLayout.addWidget(self.LoglLevel)

        self.filePickerLogFile = FilePickerWidget(self.groupBoxLogSettings)
        self.filePickerLogFile.setObjectName("filePickerLogFile")
        sizePolicy2.setHeightForWidth(self.filePickerLogFile.sizePolicy().hasHeightForWidth())
        self.filePickerLogFile.setSizePolicy(sizePolicy2)

        self.verticalLayout.addWidget(self.filePickerLogFile)

        self.layoutScrollArea.addWidget(self.groupBoxLogSettings)

        self.SaveSettings = QWidget(self.scrollAreaWidgetContents)
        self.SaveSettings.setObjectName("SaveSettings")
        self.layoutButtons = QHBoxLayout(self.SaveSettings)
        self.layoutButtons.setObjectName("layoutButtons")
        self.HSpacerSaveButtons = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.layoutButtons.addItem(self.HSpacerSaveButtons)

        self.buttonSave = QPushButton(self.SaveSettings)
        self.buttonSave.setObjectName("buttonSave")
        sizePolicy.setHeightForWidth(self.buttonSave.sizePolicy().hasHeightForWidth())
        self.buttonSave.setSizePolicy(sizePolicy)

        self.layoutButtons.addWidget(self.buttonSave)

        self.buttonSaveAs = QPushButton(self.SaveSettings)
        self.buttonSaveAs.setObjectName("buttonSaveAs")
        sizePolicy.setHeightForWidth(self.buttonSaveAs.sizePolicy().hasHeightForWidth())
        self.buttonSaveAs.setSizePolicy(sizePolicy)

        self.layoutButtons.addWidget(self.buttonSaveAs)

        self.layoutScrollArea.addWidget(self.SaveSettings)

        self.scrollAreaMain.setWidget(self.scrollAreaWidgetContents)

        self.verticalLayout_2.addWidget(self.scrollAreaMain)

        self.retranslateUi(ConfigurationWindow)

        QMetaObject.connectSlotsByName(ConfigurationWindow)

    # setupUi

    def retranslateUi(self, ConfigurationWindow):
        ConfigurationWindow.setWindowTitle(QCoreApplication.translate("ConfigurationWindow", "Form", None))
        self.groupBoxFolders.setTitle(
            QCoreApplication.translate("ConfigurationWindow", "\u30d5\u30a9\u30eb\u30c0\u8a2d\u5b9a", None)
        )
        self.groupBoxApiSettings.setTitle(
            QCoreApplication.translate("ConfigurationWindow", "API KEY", None)
        )
        self.labelOpenAiKey.setText(QCoreApplication.translate("ConfigurationWindow", "OpenAI", None))
        self.labelGoogleKey.setText(
            QCoreApplication.translate("ConfigurationWindow", "Google AI Studio", None)
        )
        self.labelAnthropicKey.setText(QCoreApplication.translate("ConfigurationWindow", "Anthropic", None))
        self.groupBoxHuggingFaceSettings.setTitle(
            QCoreApplication.translate("ConfigurationWindow", "Hugging Face", None)
        )
        self.labelHfUsername.setText(
            QCoreApplication.translate("ConfigurationWindow", "\u30e6\u30fc\u30b6\u30fc\u540d:", None)
        )
        self.labelHfRepoName.setText(
            QCoreApplication.translate("ConfigurationWindow", "\u30ea\u30dd\u30b8\u30c8\u30ea\u540d:", None)
        )
        self.labelHfToken.setText(
            QCoreApplication.translate("ConfigurationWindow", "\u30c8\u30fc\u30af\u30f3:", None)
        )
        self.groupBoxLogSettings.setTitle(
            QCoreApplication.translate("ConfigurationWindow", "\u30ed\u30b0\u8a2d\u5b9a", None)
        )
        self.labelLogLevel.setText(
            QCoreApplication.translate("ConfigurationWindow", "\u30ed\u30b0\u30ec\u30d9\u30eb:", None)
        )
        self.buttonSave.setText(QCoreApplication.translate("ConfigurationWindow", "\u4fdd\u5b58", None))
        self.buttonSaveAs.setText(
            QCoreApplication.translate(
                "ConfigurationWindow", "\u540d\u524d\u3092\u4ed8\u3051\u3066\u4fdd\u5b58", None
            )
        )

    # retranslateUi
