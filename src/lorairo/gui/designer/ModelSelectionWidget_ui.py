# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ModelSelectionWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget)

class Ui_ModelSelectionWidget(object):
    def setupUi(self, ModelSelectionWidget):
        if not ModelSelectionWidget.objectName():
            ModelSelectionWidget.setObjectName(u"ModelSelectionWidget")
        ModelSelectionWidget.resize(320, 300)
        ModelSelectionWidget.setStyleSheet(u"/* Provider Group Label Style */\n"
".provider-group-label {\n"
"    font-size: 9px;\n"
"    font-weight: bold;\n"
"    color: #666;\n"
"    padding: 2px 0px;\n"
"    margin: 4px 0px 2px 0px;\n"
"}")
        self.mainLayout = QVBoxLayout(ModelSelectionWidget)
        self.mainLayout.setSpacing(6)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.controlFrame = QFrame(ModelSelectionWidget)
        self.controlFrame.setObjectName(u"controlFrame")
        self.controlFrame.setFrameShape(QFrame.Shape.NoFrame)
        self.controlLayout = QHBoxLayout(self.controlFrame)
        self.controlLayout.setSpacing(6)
        self.controlLayout.setObjectName(u"controlLayout")
        self.controlLayout.setContentsMargins(0, 0, 0, 0)
        self.btnSelectAll = QPushButton(self.controlFrame)
        self.btnSelectAll.setObjectName(u"btnSelectAll")
        self.btnSelectAll.setMaximumSize(QSize(55, 24))
        self.btnSelectAll.setStyleSheet(u"QPushButton {\n"
"    font-size: 10px;\n"
"    padding: 3px 6px;\n"
"    border: 1px solid #4CAF50;\n"
"    border-radius: 3px;\n"
"    background-color: #f0f8f0;\n"
"    color: #2E7D32;\n"
"}\n"
"QPushButton:hover { background-color: #e8f5e8; }\n"
"QPushButton:pressed { background-color: #4CAF50; color: white; }")

        self.controlLayout.addWidget(self.btnSelectAll)

        self.btnDeselectAll = QPushButton(self.controlFrame)
        self.btnDeselectAll.setObjectName(u"btnDeselectAll")
        self.btnDeselectAll.setMaximumSize(QSize(55, 24))
        self.btnDeselectAll.setStyleSheet(u"QPushButton {\n"
"    font-size: 10px;\n"
"    padding: 3px 6px;\n"
"    border: 1px solid #f44336;\n"
"    border-radius: 3px;\n"
"    background-color: #fff8f8;\n"
"    color: #c62828;\n"
"}\n"
"QPushButton:hover { background-color: #ffebee; }\n"
"QPushButton:pressed { background-color: #f44336; color: white; }")

        self.controlLayout.addWidget(self.btnDeselectAll)

        self.btnSelectRecommended = QPushButton(self.controlFrame)
        self.btnSelectRecommended.setObjectName(u"btnSelectRecommended")
        self.btnSelectRecommended.setMaximumSize(QSize(65, 24))
        self.btnSelectRecommended.setStyleSheet(u"QPushButton {\n"
"    font-size: 10px;\n"
"    padding: 3px 6px;\n"
"    border: 1px solid #2196F3;\n"
"    border-radius: 3px;\n"
"    background-color: #f0f8ff;\n"
"    color: #1976D2;\n"
"}\n"
"QPushButton:hover { background-color: #e3f2fd; }\n"
"QPushButton:pressed { background-color: #2196F3; color: white; }")

        self.controlLayout.addWidget(self.btnSelectRecommended)

        self.controlSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.controlLayout.addItem(self.controlSpacer)


        self.mainLayout.addWidget(self.controlFrame)

        self.scrollArea = QScrollArea(ModelSelectionWidget)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setMinimumSize(QSize(0, 80))
        self.scrollArea.setMaximumSize(QSize(16777215, 200))
        self.scrollArea.setFrameShape(QFrame.Shape.StyledPanel)
        self.scrollArea.setFrameShadow(QFrame.Shadow.Sunken)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 318, 198))
        self.dynamicContentLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.dynamicContentLayout.setSpacing(2)
        self.dynamicContentLayout.setObjectName(u"dynamicContentLayout")
        self.dynamicContentLayout.setContentsMargins(6, 6, 6, 6)
        self.placeholderLabel = QLabel(self.scrollAreaWidgetContents)
        self.placeholderLabel.setObjectName(u"placeholderLabel")
        self.placeholderLabel.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.placeholderLabel.setWordWrap(True)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.placeholderLabel.sizePolicy().hasHeightForWidth())
        self.placeholderLabel.setSizePolicy(sizePolicy)
        self.placeholderLabel.setStyleSheet(u"QLabel {\n"
"    color: #666;\n"
"    font-style: italic;\n"
"    padding: 12px;\n"
"    font-size: 10px;\n"
"    line-height: 1.3;\n"
"    background-color: #f0f8ff;\n"
"    border: 1px dashed #2196F3;\n"
"    border-radius: 4px;\n"
"}")

        self.dynamicContentLayout.addWidget(self.placeholderLabel)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.dynamicContentLayout.addItem(self.verticalSpacer)

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.mainLayout.addWidget(self.scrollArea)

        self.statusLabel = QLabel(ModelSelectionWidget)
        self.statusLabel.setObjectName(u"statusLabel")
        self.statusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sizePolicy.setHeightForWidth(self.statusLabel.sizePolicy().hasHeightForWidth())
        self.statusLabel.setSizePolicy(sizePolicy)

        self.mainLayout.addWidget(self.statusLabel)


        self.retranslateUi(ModelSelectionWidget)
        self.btnSelectAll.clicked.connect(ModelSelectionWidget.select_all_models)
        self.btnDeselectAll.clicked.connect(ModelSelectionWidget.deselect_all_models)
        self.btnSelectRecommended.clicked.connect(ModelSelectionWidget.select_recommended_models)

        QMetaObject.connectSlotsByName(ModelSelectionWidget)
    # setupUi

    def retranslateUi(self, ModelSelectionWidget):
        ModelSelectionWidget.setWindowTitle(QCoreApplication.translate("ModelSelectionWidget", u"Model Selection", None))
        self.btnSelectAll.setText(QCoreApplication.translate("ModelSelectionWidget", u"\u5168\u9078\u629e", None))
        self.btnDeselectAll.setText(QCoreApplication.translate("ModelSelectionWidget", u"\u5168\u89e3\u9664", None))
#if QT_CONFIG(tooltip)
        self.btnSelectRecommended.setToolTip(QCoreApplication.translate("ModelSelectionWidget", u"\u63a8\u5968\u30e2\u30c7\u30eb\u3092\u81ea\u52d5\u9078\u629e", None))
#endif // QT_CONFIG(tooltip)
        self.btnSelectRecommended.setText(QCoreApplication.translate("ModelSelectionWidget", u"\u63a8\u5968\u9078\u629e", None))
        self.placeholderLabel.setText(QCoreApplication.translate("ModelSelectionWidget", u"\u25a0 \u63a8\u5968AI\u30e2\u30c7\u30eb (DB\u81ea\u52d5\u9078\u629e)\n"
"\n"
"\u4e0b\u8a18\u306e\u63a8\u5968\u69cb\u6210\u304b\u3089\u8907\u6570\u9078\u629e\u3067\u304d\u307e\u3059:\n"
"\u30fb\u9ad8\u54c1\u8ceaCaption\u751f\u6210\n"
"\u30fb\u9ad8\u7cbe\u5ea6\u30bf\u30b0\u751f\u6210\n"
"\u30fb\u54c1\u8cea\u8a55\u4fa1\n"
"\n"
"\u30e2\u30c7\u30eb\u4e00\u89a7\u306f\u8a2d\u5b9a\u3055\u308c\u305fAPI\u30ad\u30fc\u3068\n"
"\u5229\u7528\u53ef\u80fd\u306a\u30ed\u30fc\u30ab\u30eb\u30e2\u30c7\u30eb\u306b\u57fa\u3065\u3044\u3066\n"
"\u81ea\u52d5\u8868\u793a\u3055\u308c\u307e\u3059", None))
#if QT_CONFIG(tooltip)
        self.statusLabel.setToolTip(QCoreApplication.translate("ModelSelectionWidget", u"\u63a8\u5968\u30e2\u30c7\u30eb\u304b\u3089\u9078\u629e\u3055\u308c\u3066\u3044\u308b\u6570", None))
#endif // QT_CONFIG(tooltip)
        self.statusLabel.setStyleSheet(QCoreApplication.translate("ModelSelectionWidget", u"color: #333; font-size: 11px; font-weight: bold;", None))
        self.statusLabel.setText(QCoreApplication.translate("ModelSelectionWidget", u"\u9078\u629e\u6570: 0 (\u63a8\u5968)", None))
    # retranslateUi

