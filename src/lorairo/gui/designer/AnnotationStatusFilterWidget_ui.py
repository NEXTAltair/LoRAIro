
################################################################################
## Form generated from reading UI file 'AnnotationStatusFilterWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.0
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
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_AnnotationStatusFilterWidget:
    def setupUi(self, AnnotationStatusFilterWidget):
        if not AnnotationStatusFilterWidget.objectName():
            AnnotationStatusFilterWidget.setObjectName("AnnotationStatusFilterWidget")
        AnnotationStatusFilterWidget.resize(251, 167)
        self.verticalLayoutMain = QVBoxLayout(AnnotationStatusFilterWidget)
        self.verticalLayoutMain.setSpacing(4)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(6, 6, 6, 6)
        self.groupBoxStatusFilter = QGroupBox(AnnotationStatusFilterWidget)
        self.groupBoxStatusFilter.setObjectName("groupBoxStatusFilter")
        self.gridLayoutStatus = QGridLayout(self.groupBoxStatusFilter)
        self.gridLayoutStatus.setSpacing(3)
        self.gridLayoutStatus.setObjectName("gridLayoutStatus")
        self.checkBoxError = QCheckBox(self.groupBoxStatusFilter)
        self.checkBoxError.setObjectName("checkBoxError")
        self.checkBoxError.setChecked(False)

        self.gridLayoutStatus.addWidget(self.checkBoxError, 1, 0, 1, 1)

        self.labelCompletedCount = QLabel(self.groupBoxStatusFilter)
        self.labelCompletedCount.setObjectName("labelCompletedCount")
        self.labelCompletedCount.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelCompletedCount.sizePolicy().hasHeightForWidth())
        self.labelCompletedCount.setSizePolicy(sizePolicy)

        self.gridLayoutStatus.addWidget(self.labelCompletedCount, 0, 1, 1, 1)

        self.checkBoxCompleted = QCheckBox(self.groupBoxStatusFilter)
        self.checkBoxCompleted.setObjectName("checkBoxCompleted")
        self.checkBoxCompleted.setMouseTracking(True)
        self.checkBoxCompleted.setChecked(False)

        self.gridLayoutStatus.addWidget(self.checkBoxCompleted, 0, 0, 1, 1)

        self.labelErrorCount = QLabel(self.groupBoxStatusFilter)
        self.labelErrorCount.setObjectName("labelErrorCount")
        self.labelErrorCount.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        sizePolicy.setHeightForWidth(self.labelErrorCount.sizePolicy().hasHeightForWidth())
        self.labelErrorCount.setSizePolicy(sizePolicy)

        self.gridLayoutStatus.addWidget(self.labelErrorCount, 1, 1, 1, 1)


        self.verticalLayoutMain.addWidget(self.groupBoxStatusFilter)

        self.horizontalLayoutActions = QHBoxLayout()
        self.horizontalLayoutActions.setObjectName("horizontalLayoutActions")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutActions.addItem(self.horizontalSpacer)

        self.pushButtonRefresh = QPushButton(AnnotationStatusFilterWidget)
        self.pushButtonRefresh.setObjectName("pushButtonRefresh")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.pushButtonRefresh.sizePolicy().hasHeightForWidth())
        self.pushButtonRefresh.setSizePolicy(sizePolicy1)

        self.horizontalLayoutActions.addWidget(self.pushButtonRefresh)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutActions)


        self.retranslateUi(AnnotationStatusFilterWidget)

        QMetaObject.connectSlotsByName(AnnotationStatusFilterWidget)
    # setupUi

    def retranslateUi(self, AnnotationStatusFilterWidget):
        AnnotationStatusFilterWidget.setWindowTitle(QCoreApplication.translate("AnnotationStatusFilterWidget", "Annotation Status Filter", None))
        self.groupBoxStatusFilter.setTitle(QCoreApplication.translate("AnnotationStatusFilterWidget", "\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u72b6\u614b", None))
        self.checkBoxError.setText(QCoreApplication.translate("AnnotationStatusFilterWidget", "\u30a8\u30e9\u30fc", None))
        self.labelCompletedCount.setText(QCoreApplication.translate("AnnotationStatusFilterWidget", "(0)", None))
        self.checkBoxCompleted.setText(QCoreApplication.translate("AnnotationStatusFilterWidget", "\u5b8c\u4e86", None))
        self.labelErrorCount.setText(QCoreApplication.translate("AnnotationStatusFilterWidget", "(0)", None))
#if QT_CONFIG(tooltip)
        self.pushButtonRefresh.setToolTip(QCoreApplication.translate("AnnotationStatusFilterWidget", "\u7d71\u8a08\u60c5\u5831\u3092\u66f4\u65b0", None))
#endif // QT_CONFIG(tooltip)
        self.pushButtonRefresh.setText(QCoreApplication.translate("AnnotationStatusFilterWidget", "\u66f4\u65b0", None))
    # retranslateUi

