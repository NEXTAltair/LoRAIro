# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'AnnotateTab.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QGroupBox, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QVBoxLayout, QWidget)

class Ui_AnnotateTab(object):
    def setupUi(self, AnnotateTab: QWidget) -> None:
        if not AnnotateTab.objectName():
            AnnotateTab.setObjectName(u"AnnotateTab")
        AnnotateTab.resize(800, 600)
        self.verticalLayout_batchTag = QVBoxLayout(AnnotateTab)
        self.verticalLayout_batchTag.setSpacing(8)
        self.verticalLayout_batchTag.setObjectName(u"verticalLayout_batchTag")
        self.verticalLayout_batchTag.setContentsMargins(8, 8, 8, 8)
        self.splitterBatchTagMain = QSplitter(AnnotateTab)
        self.splitterBatchTagMain.setObjectName(u"splitterBatchTagMain")
        self.splitterBatchTagMain.setOrientation(Qt.Orientation.Vertical)
        self.splitterBatchTagMain.setChildrenCollapsible(False)
        self.batchTagWidgetPlaceholder = QWidget(self.splitterBatchTagMain)
        self.batchTagWidgetPlaceholder.setObjectName(u"batchTagWidgetPlaceholder")
        self.splitterBatchTagMain.addWidget(self.batchTagWidgetPlaceholder)
        self.groupBoxBatchOperations = QGroupBox(self.splitterBatchTagMain)
        self.groupBoxBatchOperations.setObjectName(u"groupBoxBatchOperations")
        self.verticalLayout_operations = QVBoxLayout(self.groupBoxBatchOperations)
        self.verticalLayout_operations.setObjectName(u"verticalLayout_operations")
        self.scrollAreaBatchTagColumn = QScrollArea(self.groupBoxBatchOperations)
        self.scrollAreaBatchTagColumn.setObjectName(u"scrollAreaBatchTagColumn")
        self.scrollAreaBatchTagColumn.setWidgetResizable(True)
        self.scrollAreaBatchTagColumn.setFrameShape(QFrame.Shape.NoFrame)
        self.batchTagColumnContents = QWidget()
        self.batchTagColumnContents.setObjectName(u"batchTagColumnContents")
        self.verticalLayout_batchTagColumn = QVBoxLayout(self.batchTagColumnContents)
        self.verticalLayout_batchTagColumn.setObjectName(u"verticalLayout_batchTagColumn")
        self.verticalLayout_batchTagColumn.setContentsMargins(0, 0, 0, 0)
        self.batchTagInputPlaceholder = QWidget(self.batchTagColumnContents)
        self.batchTagInputPlaceholder.setObjectName(u"batchTagInputPlaceholder")

        self.verticalLayout_batchTagColumn.addWidget(self.batchTagInputPlaceholder)

        self.groupBoxAnnotation = QGroupBox(self.batchTagColumnContents)
        self.groupBoxAnnotation.setObjectName(u"groupBoxAnnotation")
        self.verticalLayout_annotation = QVBoxLayout(self.groupBoxAnnotation)
        self.verticalLayout_annotation.setObjectName(u"verticalLayout_annotation")
        self.labelAnnotationTarget = QLabel(self.groupBoxAnnotation)
        self.labelAnnotationTarget.setObjectName(u"labelAnnotationTarget")

        self.verticalLayout_annotation.addWidget(self.labelAnnotationTarget)

        self.annotationFilterPlaceholder = QWidget(self.groupBoxAnnotation)
        self.annotationFilterPlaceholder.setObjectName(u"annotationFilterPlaceholder")

        self.verticalLayout_annotation.addWidget(self.annotationFilterPlaceholder)

        self.modelSelectionPlaceholder = QWidget(self.groupBoxAnnotation)
        self.modelSelectionPlaceholder.setObjectName(u"modelSelectionPlaceholder")

        self.verticalLayout_annotation.addWidget(self.modelSelectionPlaceholder)

        self.btnAnnotationExecute = QPushButton(self.groupBoxAnnotation)
        self.btnAnnotationExecute.setObjectName(u"btnAnnotationExecute")

        self.verticalLayout_annotation.addWidget(self.btnAnnotationExecute)


        self.verticalLayout_batchTagColumn.addWidget(self.groupBoxAnnotation)

        self.scrollAreaBatchTagColumn.setWidget(self.batchTagColumnContents)

        self.verticalLayout_operations.addWidget(self.scrollAreaBatchTagColumn)

        self.splitterBatchTagMain.addWidget(self.groupBoxBatchOperations)

        self.verticalLayout_batchTag.addWidget(self.splitterBatchTagMain)


        self.retranslateUi(AnnotateTab)

        QMetaObject.connectSlotsByName(AnnotateTab)
    # setupUi

    def retranslateUi(self, AnnotateTab: QWidget) -> None:
        self.groupBoxBatchOperations.setTitle(QCoreApplication.translate("AnnotateTab", u"\u64cd\u4f5c", None))
        self.groupBoxAnnotation.setTitle(QCoreApplication.translate("AnnotateTab", u"\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3", None))
        self.labelAnnotationTarget.setText(QCoreApplication.translate("AnnotateTab", u"\u5bfe\u8c61: \u30b9\u30c6\u30fc\u30b8\u30f3\u30b0\u6e08\u307f\u753b\u50cf", None))
        self.btnAnnotationExecute.setText(QCoreApplication.translate("AnnotateTab", u"\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u5b9f\u884c", None))
        pass
    # retranslateUi

