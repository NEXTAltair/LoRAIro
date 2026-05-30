# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ProviderBatchJobWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget)

from lorairo.gui.widgets.staging_widget import StagingWidget

class Ui_ProviderBatchJobWidget(object):
    def setupUi(self, ProviderBatchJobWidget: QWidget) -> None:
        if not ProviderBatchJobWidget.objectName():
            ProviderBatchJobWidget.setObjectName(u"ProviderBatchJobWidget")
        ProviderBatchJobWidget.resize(960, 640)
        self.rootLayout = QHBoxLayout(ProviderBatchJobWidget)
        self.rootLayout.setSpacing(8)
        self.rootLayout.setObjectName(u"rootLayout")
        self.rootLayout.setContentsMargins(8, 8, 8, 8)
        self.splitterMain = QSplitter(ProviderBatchJobWidget)
        self.splitterMain.setObjectName(u"splitterMain")
        self.splitterMain.setOrientation(Qt.Orientation.Horizontal)
        self.splitterMain.setChildrenCollapsible(False)
        self.leftContainer = QWidget(self.splitterMain)
        self.leftContainer.setObjectName(u"leftContainer")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.leftContainer.sizePolicy().hasHeightForWidth())
        self.leftContainer.setSizePolicy(sizePolicy)
        self.leftLayout = QVBoxLayout(self.leftContainer)
        self.leftLayout.setObjectName(u"leftLayout")
        self.leftLayout.setContentsMargins(0, 0, 0, 0)
        self.stagingWidget = StagingWidget(self.leftContainer)
        self.stagingWidget.setObjectName(u"stagingWidget")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.stagingWidget.sizePolicy().hasHeightForWidth())
        self.stagingWidget.setSizePolicy(sizePolicy1)

        self.leftLayout.addWidget(self.stagingWidget)

        self.stagingButtonsLayout = QHBoxLayout()
        self.stagingButtonsLayout.setObjectName(u"stagingButtonsLayout")
        self.horizontalSpacerStaging = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.stagingButtonsLayout.addItem(self.horizontalSpacerStaging)

        self.buttonAddSelected = QPushButton(self.leftContainer)
        self.buttonAddSelected.setObjectName(u"buttonAddSelected")

        self.stagingButtonsLayout.addWidget(self.buttonAddSelected)


        self.leftLayout.addLayout(self.stagingButtonsLayout)

        self.labelStatus = QLabel(self.leftContainer)
        self.labelStatus.setObjectName(u"labelStatus")

        self.leftLayout.addWidget(self.labelStatus)

        self.splitterMain.addWidget(self.leftContainer)
        self.splitterRight = QSplitter(self.splitterMain)
        self.splitterRight.setObjectName(u"splitterRight")
        self.splitterRight.setOrientation(Qt.Orientation.Vertical)
        self.splitterRight.setChildrenCollapsible(False)
        self.groupBoxExecution = QGroupBox(self.splitterRight)
        self.groupBoxExecution.setObjectName(u"groupBoxExecution")
        self.executionLayout = QVBoxLayout(self.groupBoxExecution)
        self.executionLayout.setObjectName(u"executionLayout")
        self.labelTarget = QLabel(self.groupBoxExecution)
        self.labelTarget.setObjectName(u"labelTarget")

        self.executionLayout.addWidget(self.labelTarget)

        self.taskTypeLayout = QHBoxLayout()
        self.taskTypeLayout.setObjectName(u"taskTypeLayout")
        self.labelTaskType = QLabel(self.groupBoxExecution)
        self.labelTaskType.setObjectName(u"labelTaskType")

        self.taskTypeLayout.addWidget(self.labelTaskType)

        self.comboBoxTaskType = QComboBox(self.groupBoxExecution)
        self.comboBoxTaskType.setObjectName(u"comboBoxTaskType")

        self.taskTypeLayout.addWidget(self.comboBoxTaskType)

        self.horizontalSpacerTaskType = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.taskTypeLayout.addItem(self.horizontalSpacerTaskType)


        self.executionLayout.addLayout(self.taskTypeLayout)

        self.modelSelectionPlaceholder = QWidget(self.groupBoxExecution)
        self.modelSelectionPlaceholder.setObjectName(u"modelSelectionPlaceholder")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.modelSelectionPlaceholder.sizePolicy().hasHeightForWidth())
        self.modelSelectionPlaceholder.setSizePolicy(sizePolicy2)

        self.executionLayout.addWidget(self.modelSelectionPlaceholder)

        self.paramsLayout = QFormLayout()
        self.paramsLayout.setObjectName(u"paramsLayout")
        self.labelPromptProfile = QLabel(self.groupBoxExecution)
        self.labelPromptProfile.setObjectName(u"labelPromptProfile")

        self.paramsLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.labelPromptProfile)

        self.lineEditPromptProfile = QLineEdit(self.groupBoxExecution)
        self.lineEditPromptProfile.setObjectName(u"lineEditPromptProfile")

        self.paramsLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lineEditPromptProfile)

        self.labelDescription = QLabel(self.groupBoxExecution)
        self.labelDescription.setObjectName(u"labelDescription")

        self.paramsLayout.setWidget(1, QFormLayout.ItemRole.LabelRole, self.labelDescription)

        self.lineEditDescription = QLineEdit(self.groupBoxExecution)
        self.lineEditDescription.setObjectName(u"lineEditDescription")

        self.paramsLayout.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lineEditDescription)


        self.executionLayout.addLayout(self.paramsLayout)

        self.submitLayout = QHBoxLayout()
        self.submitLayout.setObjectName(u"submitLayout")
        self.horizontalSpacerSubmit = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.submitLayout.addItem(self.horizontalSpacerSubmit)

        self.buttonSubmit = QPushButton(self.groupBoxExecution)
        self.buttonSubmit.setObjectName(u"buttonSubmit")

        self.submitLayout.addWidget(self.buttonSubmit)


        self.executionLayout.addLayout(self.submitLayout)

        self.splitterRight.addWidget(self.groupBoxExecution)
        self.groupBoxStatus = QGroupBox(self.splitterRight)
        self.groupBoxStatus.setObjectName(u"groupBoxStatus")
        self.statusLayout = QVBoxLayout(self.groupBoxStatus)
        self.statusLayout.setObjectName(u"statusLayout")
        self.jobButtonsLayout = QHBoxLayout()
        self.jobButtonsLayout.setObjectName(u"jobButtonsLayout")
        self.buttonRefreshJobs = QPushButton(self.groupBoxStatus)
        self.buttonRefreshJobs.setObjectName(u"buttonRefreshJobs")

        self.jobButtonsLayout.addWidget(self.buttonRefreshJobs)

        self.buttonRefreshStatus = QPushButton(self.groupBoxStatus)
        self.buttonRefreshStatus.setObjectName(u"buttonRefreshStatus")

        self.jobButtonsLayout.addWidget(self.buttonRefreshStatus)

        self.buttonCancel = QPushButton(self.groupBoxStatus)
        self.buttonCancel.setObjectName(u"buttonCancel")

        self.jobButtonsLayout.addWidget(self.buttonCancel)

        self.buttonFetch = QPushButton(self.groupBoxStatus)
        self.buttonFetch.setObjectName(u"buttonFetch")

        self.jobButtonsLayout.addWidget(self.buttonFetch)

        self.buttonImport = QPushButton(self.groupBoxStatus)
        self.buttonImport.setObjectName(u"buttonImport")

        self.jobButtonsLayout.addWidget(self.buttonImport)

        self.horizontalSpacerJobButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.jobButtonsLayout.addItem(self.horizontalSpacerJobButtons)


        self.statusLayout.addLayout(self.jobButtonsLayout)

        self.tableJobs = QTableWidget(self.groupBoxStatus)
        self.tableJobs.setObjectName(u"tableJobs")

        self.statusLayout.addWidget(self.tableJobs)

        self.detailRow = QHBoxLayout()
        self.detailRow.setObjectName(u"detailRow")
        self.groupBoxDetail = QGroupBox(self.groupBoxStatus)
        self.groupBoxDetail.setObjectName(u"groupBoxDetail")
        self.detailLayout = QVBoxLayout(self.groupBoxDetail)
        self.detailLayout.setObjectName(u"detailLayout")
        self.textEditJobDetail = QTextEdit(self.groupBoxDetail)
        self.textEditJobDetail.setObjectName(u"textEditJobDetail")
        self.textEditJobDetail.setReadOnly(True)

        self.detailLayout.addWidget(self.textEditJobDetail)


        self.detailRow.addWidget(self.groupBoxDetail)

        self.groupBoxItems = QGroupBox(self.groupBoxStatus)
        self.groupBoxItems.setObjectName(u"groupBoxItems")
        self.itemsLayout = QVBoxLayout(self.groupBoxItems)
        self.itemsLayout.setObjectName(u"itemsLayout")
        self.itemFilterLayout = QHBoxLayout()
        self.itemFilterLayout.setObjectName(u"itemFilterLayout")
        self.labelItemStatus = QLabel(self.groupBoxItems)
        self.labelItemStatus.setObjectName(u"labelItemStatus")

        self.itemFilterLayout.addWidget(self.labelItemStatus)

        self.comboBoxItemStatus = QComboBox(self.groupBoxItems)
        self.comboBoxItemStatus.setObjectName(u"comboBoxItemStatus")

        self.itemFilterLayout.addWidget(self.comboBoxItemStatus)

        self.horizontalSpacerItemFilter = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.itemFilterLayout.addItem(self.horizontalSpacerItemFilter)


        self.itemsLayout.addLayout(self.itemFilterLayout)

        self.tableItems = QTableWidget(self.groupBoxItems)
        self.tableItems.setObjectName(u"tableItems")

        self.itemsLayout.addWidget(self.tableItems)


        self.detailRow.addWidget(self.groupBoxItems)


        self.statusLayout.addLayout(self.detailRow)

        self.splitterRight.addWidget(self.groupBoxStatus)
        self.splitterMain.addWidget(self.splitterRight)

        self.rootLayout.addWidget(self.splitterMain)


        self.retranslateUi(ProviderBatchJobWidget)

        QMetaObject.connectSlotsByName(ProviderBatchJobWidget)
    # setupUi

    def retranslateUi(self, ProviderBatchJobWidget: QWidget) -> None:
        ProviderBatchJobWidget.setWindowTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30d0\u30c3\u30c1API", None))
        self.buttonAddSelected.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u9078\u629e\u3092\u8ffd\u52a0", None))
        self.buttonAddSelected.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchAddSelected", None))
        self.labelStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"Ready", None))
        self.labelStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"labelProviderBatchStatus", None))
        self.groupBoxExecution.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u5b9f\u884c\u8a2d\u5b9a", None))
        self.labelTarget.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u25ce \u30b9\u30c6\u30fc\u30b8\u30f3\u30b0: 0 \u679a", None))
        self.labelTaskType.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30bf\u30b9\u30af", None))
        self.comboBoxTaskType.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"comboBoxProviderBatchTaskType", None))
        self.labelPromptProfile.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30d7\u30ed\u30f3\u30d7\u30c8", None))
        self.lineEditPromptProfile.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"default", None))
        self.lineEditPromptProfile.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"lineEditProviderBatchPromptProfile", None))
        self.labelDescription.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u8aac\u660e", None))
        self.lineEditDescription.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"lineEditProviderBatchDescription", None))
        self.buttonSubmit.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u9001\u4fe1", None))
        self.buttonSubmit.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchSubmit", None))
        self.groupBoxStatus.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30d0\u30c3\u30c1\u30b8\u30e7\u30d6\u72b6\u614b", None))
        self.buttonRefreshJobs.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u66f4\u65b0", None))
        self.buttonRefreshJobs.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchRefreshJobs", None))
        self.buttonRefreshStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u72b6\u614b\u66f4\u65b0", None))
        self.buttonRefreshStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchRefreshStatus", None))
        self.buttonCancel.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30ad\u30e3\u30f3\u30bb\u30eb", None))
        self.buttonCancel.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchCancel", None))
        self.buttonFetch.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u53d6\u5f97", None))
        self.buttonFetch.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchFetch", None))
        self.buttonImport.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u53d6\u308a\u8fbc\u307f", None))
        self.buttonImport.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchImport", None))
        self.tableJobs.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"tableProviderBatchJobs", None))
        self.groupBoxDetail.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u8a73\u7d30", None))
        self.textEditJobDetail.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"textEditProviderBatchJobDetail", None))
        self.groupBoxItems.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u9805\u76ee", None))
        self.labelItemStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u72b6\u614b", None))
        self.comboBoxItemStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"comboBoxProviderBatchItemStatus", None))
        self.tableItems.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"tableProviderBatchItems", None))
    # retranslateUi

