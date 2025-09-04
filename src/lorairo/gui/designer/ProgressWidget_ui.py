################################################################################
## Form generated from reading UI file 'ProgressWidget.ui'
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
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Ui_ProgressWidget:
    def setupUi(self, ProgressWidget):
        if not ProgressWidget.objectName():
            ProgressWidget.setObjectName("ProgressWidget")
        ProgressWidget.setWindowModality(Qt.WindowModality.WindowModal)
        ProgressWidget.resize(400, 113)
        self.verticalLayout = QVBoxLayout(ProgressWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.statusLabel = QLabel(ProgressWidget)
        self.statusLabel.setObjectName("statusLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.statusLabel.sizePolicy().hasHeightForWidth())
        self.statusLabel.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.statusLabel, 0, Qt.AlignmentFlag.AlignLeft)

        self.progressBar = QProgressBar(ProgressWidget)
        self.progressBar.setObjectName("progressBar")
        self.progressBar.setValue(0)
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.progressBar.sizePolicy().hasHeightForWidth())
        self.progressBar.setSizePolicy(sizePolicy1)

        self.verticalLayout.addWidget(self.progressBar)

        self.cancelButton = QPushButton(ProgressWidget)
        self.cancelButton.setObjectName("cancelButton")
        sizePolicy1.setHeightForWidth(self.cancelButton.sizePolicy().hasHeightForWidth())
        self.cancelButton.setSizePolicy(sizePolicy1)

        self.verticalLayout.addWidget(self.cancelButton, 0, Qt.AlignmentFlag.AlignRight)

        self.retranslateUi(ProgressWidget)

        QMetaObject.connectSlotsByName(ProgressWidget)

    # setupUi

    def retranslateUi(self, ProgressWidget):
        ProgressWidget.setWindowTitle(QCoreApplication.translate("ProgressWidget", "Form", None))
        self.statusLabel.setText(
            QCoreApplication.translate("ProgressWidget", "\u5f85\u6a5f\u4e2d...", None)
        )
        self.progressBar.setFormat(QCoreApplication.translate("ProgressWidget", "%v / %m", None))
        self.cancelButton.setText(
            QCoreApplication.translate("ProgressWidget", "\u30ad\u30e3\u30f3\u30bb\u30eb", None)
        )

    # retranslateUi
