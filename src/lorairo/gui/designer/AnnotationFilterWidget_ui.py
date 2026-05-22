# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'AnnotationFilterWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QGroupBox, QHBoxLayout,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_AnnotationFilterWidget(object):
    def setupUi(self, AnnotationFilterWidget: QWidget) -> None:
        if not AnnotationFilterWidget.objectName():
            AnnotationFilterWidget.setObjectName(u"AnnotationFilterWidget")
        AnnotationFilterWidget.resize(300, 150)
        self.mainLayout = QVBoxLayout(AnnotationFilterWidget)
        self.mainLayout.setSpacing(6)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.groupBoxEnvironment = QGroupBox(AnnotationFilterWidget)
        self.groupBoxEnvironment.setObjectName(u"groupBoxEnvironment")
        self.horizontalLayoutEnvironment = QHBoxLayout(self.groupBoxEnvironment)
        self.horizontalLayoutEnvironment.setSpacing(6)
        self.horizontalLayoutEnvironment.setObjectName(u"horizontalLayoutEnvironment")
        self.checkBoxWebAPI = QCheckBox(self.groupBoxEnvironment)
        self.checkBoxWebAPI.setObjectName(u"checkBoxWebAPI")

        self.horizontalLayoutEnvironment.addWidget(self.checkBoxWebAPI)

        self.checkBoxLocal = QCheckBox(self.groupBoxEnvironment)
        self.checkBoxLocal.setObjectName(u"checkBoxLocal")

        self.horizontalLayoutEnvironment.addWidget(self.checkBoxLocal)

        self.horizontalSpacerEnvironment = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutEnvironment.addItem(self.horizontalSpacerEnvironment)


        self.mainLayout.addWidget(self.groupBoxEnvironment)

        self.groupBoxFunctionType = QGroupBox(AnnotationFilterWidget)
        self.groupBoxFunctionType.setObjectName(u"groupBoxFunctionType")
        self.horizontalLayoutFunctionType = QHBoxLayout(self.groupBoxFunctionType)
        self.horizontalLayoutFunctionType.setSpacing(6)
        self.horizontalLayoutFunctionType.setObjectName(u"horizontalLayoutFunctionType")
        self.checkBoxTags = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxTags.setObjectName(u"checkBoxTags")

        self.horizontalLayoutFunctionType.addWidget(self.checkBoxTags)

        self.checkBoxCaption = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxCaption.setObjectName(u"checkBoxCaption")

        self.horizontalLayoutFunctionType.addWidget(self.checkBoxCaption)

        self.checkBoxScore = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxScore.setObjectName(u"checkBoxScore")

        self.horizontalLayoutFunctionType.addWidget(self.checkBoxScore)

        self.checkBoxRating = QCheckBox(self.groupBoxFunctionType)
        self.checkBoxRating.setObjectName(u"checkBoxRating")

        self.horizontalLayoutFunctionType.addWidget(self.checkBoxRating)

        self.horizontalSpacerFunctionType = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutFunctionType.addItem(self.horizontalSpacerFunctionType)


        self.mainLayout.addWidget(self.groupBoxFunctionType)

        self.retranslateUi(AnnotationFilterWidget)

        QMetaObject.connectSlotsByName(AnnotationFilterWidget)
    # setupUi

    def retranslateUi(self, AnnotationFilterWidget: QWidget) -> None:
        AnnotationFilterWidget.setWindowTitle(QCoreApplication.translate("AnnotationFilterWidget", u"Annotation Filter", None))
        self.groupBoxEnvironment.setTitle(QCoreApplication.translate("AnnotationFilterWidget", u"\u5b9f\u884c\u74b0\u5883\u9078\u629e", None))
        self.checkBoxWebAPI.setText(QCoreApplication.translate("AnnotationFilterWidget", u"Web API", None))
        self.checkBoxLocal.setText(QCoreApplication.translate("AnnotationFilterWidget", u"\u30ed\u30fc\u30ab\u30eb\u30e2\u30c7\u30eb", None))
        self.groupBoxFunctionType.setTitle(QCoreApplication.translate("AnnotationFilterWidget", u"\u30ed\u30fc\u30ab\u30eb\u30e2\u30c7\u30eb\u5bfe\u5fdc\u6a5f\u80fd", None))
        self.checkBoxTags.setText(QCoreApplication.translate("AnnotationFilterWidget", u"\u30bf\u30b0\u5bfe\u5fdc", None))
        self.checkBoxCaption.setText(QCoreApplication.translate("AnnotationFilterWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u5bfe\u5fdc", None))
        self.checkBoxScore.setText(QCoreApplication.translate("AnnotationFilterWidget", u"\u30b9\u30b3\u30a2\u5bfe\u5fdc", None))
        self.checkBoxRating.setText(QCoreApplication.translate("AnnotationFilterWidget", u"\u30ec\u30fc\u30c6\u30a3\u30f3\u30b0\u5bfe\u5fdc", None))
    # retranslateUi
