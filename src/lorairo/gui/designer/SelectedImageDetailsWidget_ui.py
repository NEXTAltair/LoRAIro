# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SelectedImageDetailsWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QGroupBox, QLabel,
    QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget)

from ..widgets.annotation_data_display_widget import AnnotationDataDisplayWidget

class Ui_SelectedImageDetailsWidget(object):
    def setupUi(self, SelectedImageDetailsWidget):
        if not SelectedImageDetailsWidget.objectName():
            SelectedImageDetailsWidget.setObjectName(u"SelectedImageDetailsWidget")
        SelectedImageDetailsWidget.resize(250, 400)
        self.verticalLayoutMain = QVBoxLayout(SelectedImageDetailsWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName(u"verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(6, 6, 6, 6)
        self.tabWidgetDetails = QTabWidget(SelectedImageDetailsWidget)
        self.tabWidgetDetails.setObjectName(u"tabWidgetDetails")
        self.tabOverview = QWidget()
        self.tabOverview.setObjectName(u"tabOverview")
        self.verticalLayoutOverview = QVBoxLayout(self.tabOverview)
        self.verticalLayoutOverview.setObjectName(u"verticalLayoutOverview")
        self.groupBoxImageInfo = QGroupBox(self.tabOverview)
        self.groupBoxImageInfo.setObjectName(u"groupBoxImageInfo")
        self.gridLayoutImageInfo = QGridLayout(self.groupBoxImageInfo)
        self.gridLayoutImageInfo.setSpacing(3)
        self.gridLayoutImageInfo.setObjectName(u"gridLayoutImageInfo")
        self.labelFileName = QLabel(self.groupBoxImageInfo)
        self.labelFileName.setObjectName(u"labelFileName")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelFileName.sizePolicy().hasHeightForWidth())
        self.labelFileName.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileName, 0, 0, 1, 1)

        self.labelFileSize = QLabel(self.groupBoxImageInfo)
        self.labelFileSize.setObjectName(u"labelFileSize")
        sizePolicy.setHeightForWidth(self.labelFileSize.sizePolicy().hasHeightForWidth())
        self.labelFileSize.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileSize, 2, 0, 1, 1)

        self.labelFileNameValue = QLabel(self.groupBoxImageInfo)
        self.labelFileNameValue.setObjectName(u"labelFileNameValue")
        self.labelFileNameValue.setWordWrap(True)
        sizePolicy.setHeightForWidth(self.labelFileNameValue.sizePolicy().hasHeightForWidth())
        self.labelFileNameValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileNameValue, 0, 1, 1, 1)

        self.labelFileSizeValue = QLabel(self.groupBoxImageInfo)
        self.labelFileSizeValue.setObjectName(u"labelFileSizeValue")
        sizePolicy.setHeightForWidth(self.labelFileSizeValue.sizePolicy().hasHeightForWidth())
        self.labelFileSizeValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileSizeValue, 2, 1, 1, 1)

        self.labelCreatedDate = QLabel(self.groupBoxImageInfo)
        self.labelCreatedDate.setObjectName(u"labelCreatedDate")
        sizePolicy.setHeightForWidth(self.labelCreatedDate.sizePolicy().hasHeightForWidth())
        self.labelCreatedDate.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelCreatedDate, 3, 0, 1, 1)

        self.labelCreatedDateValue = QLabel(self.groupBoxImageInfo)
        self.labelCreatedDateValue.setObjectName(u"labelCreatedDateValue")
        sizePolicy.setHeightForWidth(self.labelCreatedDateValue.sizePolicy().hasHeightForWidth())
        self.labelCreatedDateValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelCreatedDateValue, 3, 1, 1, 1)

        self.labelImageSizeValue = QLabel(self.groupBoxImageInfo)
        self.labelImageSizeValue.setObjectName(u"labelImageSizeValue")
        sizePolicy.setHeightForWidth(self.labelImageSizeValue.sizePolicy().hasHeightForWidth())
        self.labelImageSizeValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelImageSizeValue, 1, 1, 1, 1)

        self.labelImageSize = QLabel(self.groupBoxImageInfo)
        self.labelImageSize.setObjectName(u"labelImageSize")
        sizePolicy.setHeightForWidth(self.labelImageSize.sizePolicy().hasHeightForWidth())
        self.labelImageSize.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelImageSize, 1, 0, 1, 1)


        self.verticalLayoutOverview.addWidget(self.groupBoxImageInfo)

        self.tabWidgetDetails.addTab(self.tabOverview, "")
        self.tabTags = QWidget()
        self.tabTags.setObjectName(u"tabTags")
        self.verticalLayoutTagsTab = QVBoxLayout(self.tabTags)
        self.verticalLayoutTagsTab.setObjectName(u"verticalLayoutTagsTab")
        self.groupBoxTags = QGroupBox(self.tabTags)
        self.groupBoxTags.setObjectName(u"groupBoxTags")
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName(u"verticalLayoutTags")
        self.labelTagsContent = QLabel(self.groupBoxTags)
        self.labelTagsContent.setObjectName(u"labelTagsContent")
        self.labelTagsContent.setWordWrap(True)
        sizePolicy.setHeightForWidth(self.labelTagsContent.sizePolicy().hasHeightForWidth())
        self.labelTagsContent.setSizePolicy(sizePolicy)

        self.verticalLayoutTags.addWidget(self.labelTagsContent)


        self.verticalLayoutTagsTab.addWidget(self.groupBoxTags)

        self.tabWidgetDetails.addTab(self.tabTags, "")
        self.tabCaptions = QWidget()
        self.tabCaptions.setObjectName(u"tabCaptions")
        self.verticalLayoutCaptionsTab = QVBoxLayout(self.tabCaptions)
        self.verticalLayoutCaptionsTab.setObjectName(u"verticalLayoutCaptionsTab")
        self.groupBoxCaptions = QGroupBox(self.tabCaptions)
        self.groupBoxCaptions.setObjectName(u"groupBoxCaptions")
        self.verticalLayoutCaptions = QVBoxLayout(self.groupBoxCaptions)
        self.verticalLayoutCaptions.setObjectName(u"verticalLayoutCaptions")
        self.textEditCaptionsContent = QTextEdit(self.groupBoxCaptions)
        self.textEditCaptionsContent.setObjectName(u"textEditCaptionsContent")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.textEditCaptionsContent.sizePolicy().hasHeightForWidth())
        self.textEditCaptionsContent.setSizePolicy(sizePolicy1)
        self.textEditCaptionsContent.setReadOnly(True)

        self.verticalLayoutCaptions.addWidget(self.textEditCaptionsContent)


        self.verticalLayoutCaptionsTab.addWidget(self.groupBoxCaptions)

        self.tabWidgetDetails.addTab(self.tabCaptions, "")
        self.tabMetadata = QWidget()
        self.tabMetadata.setObjectName(u"tabMetadata")
        self.verticalLayoutMetadata = QVBoxLayout(self.tabMetadata)
        self.verticalLayoutMetadata.setObjectName(u"verticalLayoutMetadata")
        self.annotationDataDisplay = AnnotationDataDisplayWidget(self.tabMetadata)
        self.annotationDataDisplay.setObjectName(u"annotationDataDisplay")
        sizePolicy1.setHeightForWidth(self.annotationDataDisplay.sizePolicy().hasHeightForWidth())
        self.annotationDataDisplay.setSizePolicy(sizePolicy1)

        self.verticalLayoutMetadata.addWidget(self.annotationDataDisplay)

        self.tabWidgetDetails.addTab(self.tabMetadata, "")

        self.verticalLayoutMain.addWidget(self.tabWidgetDetails)


        self.retranslateUi(SelectedImageDetailsWidget)

        self.tabWidgetDetails.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(SelectedImageDetailsWidget)
    # setupUi

    def retranslateUi(self, SelectedImageDetailsWidget):
        SelectedImageDetailsWidget.setWindowTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"Selected Image Details", None))
        self.groupBoxImageInfo.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u753b\u50cf\u60c5\u5831", None))
        self.labelFileName.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d:", None))
        self.labelFileSize.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30d5\u30a1\u30a4\u30eb\u30b5\u30a4\u30ba:", None))
        self.labelFileNameValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"-", None))
        self.labelFileSizeValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"-", None))
        self.labelCreatedDate.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u767b\u9332\u65e5:", None))
        self.labelCreatedDateValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"-", None))
        self.labelImageSizeValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"-", None))
        self.labelImageSize.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u89e3\u50cf\u5ea6:", None))
        self.tabWidgetDetails.setTabText(self.tabWidgetDetails.indexOf(self.tabOverview), QCoreApplication.translate("SelectedImageDetailsWidget", u"\u6982\u8981", None))
        self.groupBoxTags.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30bf\u30b0", None))
        self.labelTagsContent.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"cat, sitting, outdoor, wooden", None))
        self.tabWidgetDetails.setTabText(self.tabWidgetDetails.indexOf(self.tabTags), QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30bf\u30b0", None))
        self.groupBoxCaptions.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.textEditCaptionsContent.setPlaceholderText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.tabWidgetDetails.setTabText(self.tabWidgetDetails.indexOf(self.tabCaptions), QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.tabWidgetDetails.setTabText(self.tabWidgetDetails.indexOf(self.tabMetadata), QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30e1\u30bf\u30c7\u30fc\u30bf", None))
    # retranslateUi

