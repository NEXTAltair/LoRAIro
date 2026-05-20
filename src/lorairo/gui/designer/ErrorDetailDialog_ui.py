# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ErrorDetailDialog.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
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
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpacerItem, QTextEdit, QVBoxLayout,
    QWidget)

class Ui_ErrorDetailDialog(object):
    def setupUi(self, ErrorDetailDialog: QWidget) -> None:
        if not ErrorDetailDialog.objectName():
            ErrorDetailDialog.setObjectName(u"ErrorDetailDialog")
        ErrorDetailDialog.resize(600, 700)
        ErrorDetailDialog.setModal(True)
        self.verticalLayoutMain = QVBoxLayout(ErrorDetailDialog)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(12, 12, 12, 12)
        self.groupBoxBasicInfo = QGroupBox(ErrorDetailDialog)
        self.groupBoxBasicInfo.setObjectName(u"groupBoxBasicInfo")
        self.formLayoutBasicInfo = QFormLayout(self.groupBoxBasicInfo)
        self.formLayoutBasicInfo.setObjectName(u"formLayoutBasicInfo")
        self.formLayoutBasicInfo.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.labelOperationTypeText = QLabel(self.groupBoxBasicInfo)
        self.labelOperationTypeText.setObjectName(u"labelOperationTypeText")

        self.formLayoutBasicInfo.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelOperationTypeText)

        self.lineEditOperationType = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditOperationType.setObjectName(u"lineEditOperationType")
        self.lineEditOperationType.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditOperationType)

        self.labelErrorTypeText = QLabel(self.groupBoxBasicInfo)
        self.labelErrorTypeText.setObjectName(u"labelErrorTypeText")

        self.formLayoutBasicInfo.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelErrorTypeText)

        self.lineEditErrorType = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditErrorType.setObjectName(u"lineEditErrorType")
        self.lineEditErrorType.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditErrorType)

        self.labelErrorMessageText = QLabel(self.groupBoxBasicInfo)
        self.labelErrorMessageText.setObjectName(u"labelErrorMessageText")

        self.formLayoutBasicInfo.setWidget(2, QFormLayout.ItemRole.LabelRole, self.labelErrorMessageText)

        self.textEditErrorMessage = QTextEdit(self.groupBoxBasicInfo)
        self.textEditErrorMessage.setObjectName(u"textEditErrorMessage")
        self.textEditErrorMessage.setMaximumSize(QSize(16777215, 60))
        self.textEditErrorMessage.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(2, QFormLayout.ItemRole.FieldRole, self.textEditErrorMessage)

        self.labelFilePathText = QLabel(self.groupBoxBasicInfo)
        self.labelFilePathText.setObjectName(u"labelFilePathText")

        self.formLayoutBasicInfo.setWidget(3, QFormLayout.ItemRole.LabelRole, self.labelFilePathText)

        self.lineEditFilePath = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditFilePath.setObjectName(u"lineEditFilePath")
        self.lineEditFilePath.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lineEditFilePath)

        self.labelModelNameText = QLabel(self.groupBoxBasicInfo)
        self.labelModelNameText.setObjectName(u"labelModelNameText")

        self.formLayoutBasicInfo.setWidget(4, QFormLayout.ItemRole.LabelRole, self.labelModelNameText)

        self.lineEditModelName = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditModelName.setObjectName(u"lineEditModelName")
        self.lineEditModelName.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lineEditModelName)

        self.labelCreatedAtText = QLabel(self.groupBoxBasicInfo)
        self.labelCreatedAtText.setObjectName(u"labelCreatedAtText")

        self.formLayoutBasicInfo.setWidget(5, QFormLayout.ItemRole.LabelRole, self.labelCreatedAtText)

        self.lineEditCreatedAt = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditCreatedAt.setObjectName(u"lineEditCreatedAt")
        self.lineEditCreatedAt.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(5, QFormLayout.ItemRole.FieldRole, self.lineEditCreatedAt)

        self.labelRetryCountText = QLabel(self.groupBoxBasicInfo)
        self.labelRetryCountText.setObjectName(u"labelRetryCountText")

        self.formLayoutBasicInfo.setWidget(6, QFormLayout.ItemRole.LabelRole, self.labelRetryCountText)

        self.lineEditRetryCount = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditRetryCount.setObjectName(u"lineEditRetryCount")
        self.lineEditRetryCount.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(6, QFormLayout.ItemRole.FieldRole, self.lineEditRetryCount)

        self.labelResolvedAtText = QLabel(self.groupBoxBasicInfo)
        self.labelResolvedAtText.setObjectName(u"labelResolvedAtText")

        self.formLayoutBasicInfo.setWidget(7, QFormLayout.ItemRole.LabelRole, self.labelResolvedAtText)

        self.lineEditResolvedAt = QLineEdit(self.groupBoxBasicInfo)
        self.lineEditResolvedAt.setObjectName(u"lineEditResolvedAt")
        self.lineEditResolvedAt.setReadOnly(True)

        self.formLayoutBasicInfo.setWidget(7, QFormLayout.ItemRole.FieldRole, self.lineEditResolvedAt)


        self.verticalLayoutMain.addWidget(self.groupBoxBasicInfo)

        self.groupBoxStackTrace = QGroupBox(ErrorDetailDialog)
        self.groupBoxStackTrace.setObjectName(u"groupBoxStackTrace")
        self.verticalLayoutStackTrace = QVBoxLayout(self.groupBoxStackTrace)
        self.verticalLayoutStackTrace.setObjectName(u"verticalLayoutStackTrace")
        self.textEditStackTrace = QTextEdit(self.groupBoxStackTrace)
        self.textEditStackTrace.setObjectName(u"textEditStackTrace")
        self.textEditStackTrace.setReadOnly(True)
        self.textEditStackTrace.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self.verticalLayoutStackTrace.addWidget(self.textEditStackTrace)


        self.verticalLayoutMain.addWidget(self.groupBoxStackTrace)

        self.groupBoxImagePreview = QGroupBox(ErrorDetailDialog)
        self.groupBoxImagePreview.setObjectName(u"groupBoxImagePreview")
        self.verticalLayoutImagePreview = QVBoxLayout(self.groupBoxImagePreview)
        self.verticalLayoutImagePreview.setObjectName(u"verticalLayoutImagePreview")
        self.labelImagePreview = QLabel(self.groupBoxImagePreview)
        self.labelImagePreview.setObjectName(u"labelImagePreview")
        self.labelImagePreview.setMinimumSize(QSize(400, 300))
        self.labelImagePreview.setMaximumSize(QSize(400, 400))
        self.labelImagePreview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.labelImagePreview.setScaledContents(False)

        self.verticalLayoutImagePreview.addWidget(self.labelImagePreview)


        self.verticalLayoutMain.addWidget(self.groupBoxImagePreview)

        self.horizontalLayoutButtons = QHBoxLayout()
        self.horizontalLayoutButtons.setObjectName(u"horizontalLayoutButtons")
        self.buttonMarkResolved = QPushButton(ErrorDetailDialog)
        self.buttonMarkResolved.setObjectName(u"buttonMarkResolved")

        self.horizontalLayoutButtons.addWidget(self.buttonMarkResolved)

        self.horizontalSpacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutButtons.addItem(self.horizontalSpacerButtons)

        self.buttonClose = QPushButton(ErrorDetailDialog)
        self.buttonClose.setObjectName(u"buttonClose")

        self.horizontalLayoutButtons.addWidget(self.buttonClose)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutButtons)


        self.retranslateUi(ErrorDetailDialog)
        self.buttonClose.clicked.connect(ErrorDetailDialog.accept)

        QMetaObject.connectSlotsByName(ErrorDetailDialog)
    # setupUi

    def retranslateUi(self, ErrorDetailDialog: QWidget) -> None:
        ErrorDetailDialog.setWindowTitle(QCoreApplication.translate("ErrorDetailDialog", u"\u30a8\u30e9\u30fc\u8a73\u7d30", None))
        self.groupBoxBasicInfo.setTitle(QCoreApplication.translate("ErrorDetailDialog", u"\u57fa\u672c\u60c5\u5831", None))
        self.labelOperationTypeText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u64cd\u4f5c\u7a2e\u5225:", None))
        self.labelErrorTypeText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u30a8\u30e9\u30fc\u7a2e\u5225:", None))
        self.labelErrorMessageText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u30a8\u30e9\u30fc\u30e1\u30c3\u30bb\u30fc\u30b8:", None))
        self.labelFilePathText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u753b\u50cf\u30d1\u30b9:", None))
        self.labelModelNameText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u30e2\u30c7\u30eb\u540d:", None))
        self.labelCreatedAtText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u4f5c\u6210\u65e5\u6642:", None))
        self.labelRetryCountText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u518d\u8a66\u884c\u56de\u6570:", None))
        self.labelResolvedAtText.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u89e3\u6c7a\u65e5\u6642:", None))
        self.groupBoxStackTrace.setTitle(QCoreApplication.translate("ErrorDetailDialog", u"\u30b9\u30bf\u30c3\u30af\u30c8\u30ec\u30fc\u30b9", None))
        self.groupBoxImagePreview.setTitle(QCoreApplication.translate("ErrorDetailDialog", u"\u753b\u50cf\u30d7\u30ec\u30d3\u30e5\u30fc", None))
        self.labelImagePreview.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u753b\u50cf\u30d7\u30ec\u30d3\u30e5\u30fc\u306a\u3057", None))
        self.buttonMarkResolved.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u89e3\u6c7a\u6e08\u307f\u306b\u30de\u30fc\u30af", None))
        self.buttonClose.setText(QCoreApplication.translate("ErrorDetailDialog", u"\u9589\u3058\u308b", None))
    # retranslateUi
