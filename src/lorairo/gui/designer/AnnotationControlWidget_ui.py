
################################################################################
## Form generated from reading UI file 'AnnotationControlWidget.ui'
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
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui.widgets.model_selection_table_widget import ModelSelectionTableWidget


class Ui_AnnotationControlWidget:
    def setupUi(self, AnnotationControlWidget):
        if not AnnotationControlWidget.objectName():
            AnnotationControlWidget.setObjectName("AnnotationControlWidget")
        AnnotationControlWidget.resize(341, 1102)
        self.verticalLayoutMain = QVBoxLayout(AnnotationControlWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(9, 9, 9, 9)
        self.groupBoxFunctionType = QGroupBox(AnnotationControlWidget)
        self.groupBoxFunctionType.setObjectName("groupBoxFunctionType")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBoxFunctionType.sizePolicy().hasHeightForWidth())
        self.groupBoxFunctionType.setSizePolicy(sizePolicy)
        self.gridLayoutFunctionTypes = QGridLayout(self.groupBoxFunctionType)
        self.gridLayoutFunctionTypes.setSpacing(3)
        self.gridLayoutFunctionTypes.setObjectName("gridLayoutFunctionTypes")
        self.checkBoxCaption = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxCaption.setObjectName("checkBoxCaption")
        self.checkBoxCaption.setChecked(True)
        self.checkBoxCaption.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.gridLayoutFunctionTypes.addWidget(self.checkBoxCaption, 0, 0, 1, 1)

        self.checkBoxTagger = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxTagger.setObjectName("checkBoxTagger")
        self.checkBoxTagger.setChecked(True)
        self.checkBoxTagger.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.gridLayoutFunctionTypes.addWidget(self.checkBoxTagger, 1, 0, 1, 1)

        self.checkBoxScorer = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxScorer.setObjectName("checkBoxScorer")
        self.checkBoxScorer.setChecked(True)
        self.checkBoxScorer.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.gridLayoutFunctionTypes.addWidget(self.checkBoxScorer, 2, 0, 1, 1)


        self.verticalLayoutMain.addWidget(self.groupBoxFunctionType)

        self.groupBoxProviderSelection = QGroupBox(AnnotationControlWidget)
        self.groupBoxProviderSelection.setObjectName("groupBoxProviderSelection")
        sizePolicy.setHeightForWidth(self.groupBoxProviderSelection.sizePolicy().hasHeightForWidth())
        self.groupBoxProviderSelection.setSizePolicy(sizePolicy)
        self.horizontalLayoutProviders = QHBoxLayout(self.groupBoxProviderSelection)
        self.horizontalLayoutProviders.setSpacing(6)
        self.horizontalLayoutProviders.setObjectName("horizontalLayoutProviders")
        self.checkBoxWebAPI = QCheckBox(self.groupBoxProviderSelection)
        self.checkBoxWebAPI.setObjectName("checkBoxWebAPI")
        self.checkBoxWebAPI.setChecked(True)
        self.checkBoxWebAPI.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.horizontalLayoutProviders.addWidget(self.checkBoxWebAPI)

        self.checkBoxLocal = QCheckBox(self.groupBoxProviderSelection)
        self.checkBoxLocal.setObjectName("checkBoxLocal")
        self.checkBoxLocal.setChecked(True)
        self.checkBoxLocal.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.horizontalLayoutProviders.addWidget(self.checkBoxLocal)

        self.horizontalSpacerProviders = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutProviders.addItem(self.horizontalSpacerProviders)


        self.verticalLayoutMain.addWidget(self.groupBoxProviderSelection)

        self.groupBoxModelSelection = QGroupBox(AnnotationControlWidget)
        self.groupBoxModelSelection.setObjectName("groupBoxModelSelection")
        self.verticalLayoutModels = QVBoxLayout(self.groupBoxModelSelection)
        self.verticalLayoutModels.setObjectName("verticalLayoutModels")
        self.modelSelectionTable = ModelSelectionTableWidget(self.groupBoxModelSelection)
        self.modelSelectionTable.setObjectName("modelSelectionTable")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.modelSelectionTable.sizePolicy().hasHeightForWidth())
        self.modelSelectionTable.setSizePolicy(sizePolicy1)

        self.verticalLayoutModels.addWidget(self.modelSelectionTable)


        self.verticalLayoutMain.addWidget(self.groupBoxModelSelection)

        self.groupBoxOptions = QGroupBox(AnnotationControlWidget)
        self.groupBoxOptions.setObjectName("groupBoxOptions")
        sizePolicy.setHeightForWidth(self.groupBoxOptions.sizePolicy().hasHeightForWidth())
        self.groupBoxOptions.setSizePolicy(sizePolicy)
        self.verticalLayoutOptions = QVBoxLayout(self.groupBoxOptions)
        self.verticalLayoutOptions.setObjectName("verticalLayoutOptions")
        self.checkBoxLowResolution = QCheckBox(self.groupBoxOptions)
        self.checkBoxLowResolution.setObjectName("checkBoxLowResolution")
        self.checkBoxLowResolution.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.verticalLayoutOptions.addWidget(self.checkBoxLowResolution)

        self.checkBoxBatchMode = QCheckBox(self.groupBoxOptions)
        self.checkBoxBatchMode.setObjectName("checkBoxBatchMode")
        self.checkBoxBatchMode.setStyleSheet("QCheckBox {\n"
"    font-size: 10px;\n"
"    font-weight: normal;\n"
"    spacing: 5px;\n"
"}\n"
"QCheckBox::indicator {\n"
"    width: 14px;\n"
"    height: 14px;\n"
"}\n"
"QCheckBox::indicator:unchecked {\n"
"    border: 1px solid #ccc;\n"
"    background-color: white;\n"
"    border-radius: 2px;\n"
"}\n"
"QCheckBox::indicator:checked {\n"
"    border: 1px solid #4CAF50;\n"
"    background-color: #4CAF50;\n"
"    border-radius: 2px;\n"
"}")

        self.verticalLayoutOptions.addWidget(self.checkBoxBatchMode)


        self.verticalLayoutMain.addWidget(self.groupBoxOptions)

        self.horizontalLayoutControls = QHBoxLayout()
        self.horizontalLayoutControls.setObjectName("horizontalLayoutControls")
        self.pushButtonStart = QPushButton(AnnotationControlWidget)
        self.pushButtonStart.setObjectName("pushButtonStart")
        self.pushButtonStart.setStyleSheet("QPushButton {\n"
"    font-size: 12px;\n"
"    font-weight: bold;\n"
"    padding: 8px 16px;\n"
"    border: 2px solid #4CAF50;\n"
"    border-radius: 6px;\n"
"    background-color: palette(button);\n"
"    color: palette(buttonText);\n"
"    min-height: 30px;\n"
"}\n"
"QPushButton:hover {\n"
"    background-color: palette(highlight);\n"
"    color: palette(highlightedText);\n"
"}\n"
"QPushButton:pressed {\n"
"    background-color: #4CAF50;\n"
"    color: white;\n"
"}\n"
"QPushButton:disabled {\n"
"    background-color: palette(window);\n"
"    color: palette(mid);\n"
"    border-color: palette(mid);\n"
"}")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.pushButtonStart.sizePolicy().hasHeightForWidth())
        self.pushButtonStart.setSizePolicy(sizePolicy2)

        self.horizontalLayoutControls.addWidget(self.pushButtonStart)


        self.verticalLayoutMain.addLayout(self.horizontalLayoutControls)


        self.retranslateUi(AnnotationControlWidget)

        QMetaObject.connectSlotsByName(AnnotationControlWidget)
    # setupUi

    def retranslateUi(self, AnnotationControlWidget):
        AnnotationControlWidget.setWindowTitle(QCoreApplication.translate("AnnotationControlWidget", "Annotation Control", None))
        self.groupBoxFunctionType.setTitle(QCoreApplication.translate("AnnotationControlWidget", "\u6a5f\u80fd\u30bf\u30a4\u30d7", None))
        self.checkBoxCaption.setText(QCoreApplication.translate("AnnotationControlWidget", "Caption\u751f\u6210", None))
        self.checkBoxTagger.setText(QCoreApplication.translate("AnnotationControlWidget", "Tag\u751f\u6210", None))
        self.checkBoxScorer.setText(QCoreApplication.translate("AnnotationControlWidget", "\u54c1\u8cea\u30b9\u30b3\u30a2", None))
        self.groupBoxProviderSelection.setTitle(QCoreApplication.translate("AnnotationControlWidget", "\u5b9f\u884c\u74b0\u5883\u9078\u629e", None))
        self.checkBoxWebAPI.setText(QCoreApplication.translate("AnnotationControlWidget", "Web API", None))
        self.checkBoxLocal.setText(QCoreApplication.translate("AnnotationControlWidget", "\u30ed\u30fc\u30ab\u30eb\u30e2\u30c7\u30eb", None))
        self.groupBoxModelSelection.setTitle(QCoreApplication.translate("AnnotationControlWidget", "\u30e2\u30c7\u30eb\u9078\u629e", None))
        self.groupBoxOptions.setTitle(QCoreApplication.translate("AnnotationControlWidget", "\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.checkBoxLowResolution.setText(QCoreApplication.translate("AnnotationControlWidget", "API\u8ca0\u8377\u8efd\u6e1b\u7528512x512\u30d9\u30fc\u30b9\u306e\u753b\u50cf\u3092\u4f7f\u7528", None))
        self.checkBoxBatchMode.setText(QCoreApplication.translate("AnnotationControlWidget", "\u30d0\u30c3\u30c1\u51e6\u7406\u30e2\u30fc\u30c9", None))
#if QT_CONFIG(tooltip)
        self.pushButtonStart.setToolTip(QCoreApplication.translate("AnnotationControlWidget", "\u9078\u629e\u3057\u305f\u30e2\u30c7\u30eb\u3067\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u5b9f\u884c", None))
#endif // QT_CONFIG(tooltip)
        self.pushButtonStart.setText(QCoreApplication.translate("AnnotationControlWidget", "\u5b9f\u884c", None))
    # retranslateUi

