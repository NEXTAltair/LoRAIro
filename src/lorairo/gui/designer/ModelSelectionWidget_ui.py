
################################################################################
## Form generated from reading UI file 'ModelSelectionWidget.ui'
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
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class Ui_ModelSelectionWidget:
    def setupUi(self, ModelSelectionWidget):
        if not ModelSelectionWidget.objectName():
            ModelSelectionWidget.setObjectName("ModelSelectionWidget")
        ModelSelectionWidget.resize(320, 300)
        self.mainLayout = QVBoxLayout(ModelSelectionWidget)
        self.mainLayout.setSpacing(6)
        self.mainLayout.setObjectName("mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollArea = QScrollArea(ModelSelectionWidget)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollArea.setMinimumSize(QSize(0, 80))
        self.scrollArea.setMaximumSize(QSize(16777215, 200))
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
        self.scrollContent = QWidget()
        self.scrollContent.setObjectName("scrollContent")
        self.scrollContent.setGeometry(QRect(0, 0, 318, 198))
        self.scrollLayout = QVBoxLayout(self.scrollContent)
        self.scrollLayout.setSpacing(2)
        self.scrollLayout.setObjectName("scrollLayout")
        self.scrollLayout.setContentsMargins(6, 6, 6, 6)
        self.placeholderLabel = QLabel(self.scrollContent)
        self.placeholderLabel.setObjectName("placeholderLabel")
        self.placeholderLabel.setStyleSheet("")
        self.placeholderLabel.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.placeholderLabel.setWordWrap(True)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.placeholderLabel.sizePolicy().hasHeightForWidth())
        self.placeholderLabel.setSizePolicy(sizePolicy)

        self.scrollLayout.addWidget(self.placeholderLabel)

        self.scrollArea.setWidget(self.scrollContent)

        self.mainLayout.addWidget(self.scrollArea)

        self.statusLabel = QLabel(ModelSelectionWidget)
        self.statusLabel.setObjectName("statusLabel")
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sizePolicy.setHeightForWidth(self.statusLabel.sizePolicy().hasHeightForWidth())
        self.statusLabel.setSizePolicy(sizePolicy)

        self.mainLayout.addWidget(self.statusLabel)


        self.retranslateUi(ModelSelectionWidget)

        QMetaObject.connectSlotsByName(ModelSelectionWidget)
    # setupUi

    def retranslateUi(self, ModelSelectionWidget):
        ModelSelectionWidget.setWindowTitle(QCoreApplication.translate("ModelSelectionWidget", "Model Selection", None))
        self.placeholderLabel.setText(QCoreApplication.translate("ModelSelectionWidget", "\ud83d\udccb \u63a8\u5968AI\u30e2\u30c7\u30eb \n"
"\n"
"\u4e0b\u8a18\u306e\u63a8\u5968\u69cb\u6210\u304b\u3089\u8907\u6570\u9078\u629e\u3067\u304d\u307e\u3059:\n"
"\ud83c\udfaf \u9ad8\u54c1\u8ceaCaption\u751f\u6210\n"
"\ud83c\udff7\ufe0f \u9ad8\u7cbe\u5ea6\u30bf\u30b0\u751f\u6210\n"
"\u2b50 \u54c1\u8cea\u8a55\u4fa1\n"
"\n"
"", None))
#if QT_CONFIG(tooltip)
        self.statusLabel.setToolTip(QCoreApplication.translate("ModelSelectionWidget", "\u63a8\u5968\u30e2\u30c7\u30eb\u304b\u3089\u9078\u629e\u3055\u308c\u3066\u3044\u308b\u6570", None))
#endif // QT_CONFIG(tooltip)
        self.statusLabel.setStyleSheet(QCoreApplication.translate("ModelSelectionWidget", "color: #333; font-size: 11px; font-weight: bold;", None))
        self.statusLabel.setText(QCoreApplication.translate("ModelSelectionWidget", "\u9078\u629e\u6570: 0 (\u63a8\u5968)", None))
    # retranslateUi

