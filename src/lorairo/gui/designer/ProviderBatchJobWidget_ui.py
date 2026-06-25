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
from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget)

class Ui_ProviderBatchJobWidget(object):
    def setupUi(self, ProviderBatchJobWidget: QWidget) -> None:
        if not ProviderBatchJobWidget.objectName():
            ProviderBatchJobWidget.setObjectName(u"ProviderBatchJobWidget")
        ProviderBatchJobWidget.resize(960, 640)
        self.rootLayout = QVBoxLayout(ProviderBatchJobWidget)
        self.rootLayout.setSpacing(8)
        self.rootLayout.setObjectName(u"rootLayout")
        self.rootLayout.setContentsMargins(8, 8, 8, 8)
        self.splitterRight = QSplitter(ProviderBatchJobWidget)
        self.splitterRight.setObjectName(u"splitterRight")
        self.splitterRight.setOrientation(Qt.Orientation.Vertical)
        self.splitterRight.setChildrenCollapsible(False)
        self.groupBoxStatus = QGroupBox(self.splitterRight)
        self.groupBoxStatus.setObjectName(u"groupBoxStatus")
        self.statusLayout = QVBoxLayout(self.groupBoxStatus)
        self.statusLayout.setObjectName(u"statusLayout")
        self.labelMonitorOnlyHint = QLabel(self.groupBoxStatus)
        self.labelMonitorOnlyHint.setObjectName(u"labelMonitorOnlyHint")
        self.labelMonitorOnlyHint.setWordWrap(True)

        self.statusLayout.addWidget(self.labelMonitorOnlyHint)

        self.jobButtonsLayout = QHBoxLayout()
        self.jobButtonsLayout.setObjectName(u"jobButtonsLayout")
        self.buttonRefreshStatus = QPushButton(self.groupBoxStatus)
        self.buttonRefreshStatus.setObjectName(u"buttonRefreshStatus")

        self.jobButtonsLayout.addWidget(self.buttonRefreshStatus)

        self.buttonCancel = QPushButton(self.groupBoxStatus)
        self.buttonCancel.setObjectName(u"buttonCancel")

        self.jobButtonsLayout.addWidget(self.buttonCancel)

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

        self.rootLayout.addWidget(self.splitterRight)

        self.labelStatus = QLabel(ProviderBatchJobWidget)
        self.labelStatus.setObjectName(u"labelStatus")

        self.rootLayout.addWidget(self.labelStatus)


        self.retranslateUi(ProviderBatchJobWidget)

        QMetaObject.connectSlotsByName(ProviderBatchJobWidget)
    # setupUi

    def retranslateUi(self, ProviderBatchJobWidget: QWidget) -> None:
        ProviderBatchJobWidget.setWindowTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30d0\u30c3\u30c1API", None))
        self.groupBoxStatus.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30d0\u30c3\u30c1\u30b8\u30e7\u30d6\u72b6\u614b (\u76e3\u8996\u5c02\u7528)", None))
        self.labelMonitorOnlyHint.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u76e3\u8996\u5c02\u7528\u30d3\u30e5\u30fc \u2014 \u30d0\u30c3\u30c1API\u30b8\u30e7\u30d6\u306e\u4f5c\u6210\u306f Annotate \u30bf\u30d6\u304b\u3089\u884c\u3044\u307e\u3059\u3002\u3053\u3053\u3067\u306f\u72b6\u614b\u78ba\u8a8d\u30fb\u30ad\u30e3\u30f3\u30bb\u30eb\u30fb\u7d50\u679c\u306e\u53d6\u5f97/\u53d6\u308a\u8fbc\u307f\u306e\u307f\u53ef\u80fd\u3067\u3059\u3002", None))
        self.labelMonitorOnlyHint.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"labelProviderBatchMonitorOnlyHint", None))
        self.buttonRefreshStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u72b6\u614b\u3092\u78ba\u8a8d", None))
        self.buttonRefreshStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchRefreshStatus", None))
        self.buttonCancel.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u30ad\u30e3\u30f3\u30bb\u30eb", None))
        self.buttonCancel.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"buttonProviderBatchCancel", None))
        self.tableJobs.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"tableProviderBatchJobs", None))
        self.groupBoxDetail.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u8a73\u7d30", None))
        self.textEditJobDetail.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"textEditProviderBatchJobDetail", None))
        self.groupBoxItems.setTitle(QCoreApplication.translate("ProviderBatchJobWidget", u"\u9805\u76ee", None))
        self.labelItemStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"\u72b6\u614b", None))
        self.comboBoxItemStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"comboBoxProviderBatchItemStatus", None))
        self.tableItems.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"tableProviderBatchItems", None))
        self.labelStatus.setText(QCoreApplication.translate("ProviderBatchJobWidget", u"Ready", None))
        self.labelStatus.setObjectName(QCoreApplication.translate("ProviderBatchJobWidget", u"labelProviderBatchStatus", None))
    # retranslateUi

