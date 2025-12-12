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
from PySide6.QtWidgets import (QApplication, QComboBox, QGridLayout, QGroupBox,
    QLabel, QPushButton, QSizePolicy, QSlider,
    QTextEdit, QVBoxLayout, QWidget)

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
        self.groupBoxImageInfo = QGroupBox(SelectedImageDetailsWidget)
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


        self.verticalLayoutMain.addWidget(self.groupBoxImageInfo)

        self.groupBoxAnnotationSummary = QGroupBox(SelectedImageDetailsWidget)
        self.groupBoxAnnotationSummary.setObjectName(u"groupBoxAnnotationSummary")
        self.verticalLayoutAnnotationSummary = QVBoxLayout(self.groupBoxAnnotationSummary)
        self.verticalLayoutAnnotationSummary.setObjectName(u"verticalLayoutAnnotationSummary")
        self.groupBoxTags = QGroupBox(self.groupBoxAnnotationSummary)
        self.groupBoxTags.setObjectName(u"groupBoxTags")
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName(u"verticalLayoutTags")
        self.labelTagsContent = QLabel(self.groupBoxTags)
        self.labelTagsContent.setObjectName(u"labelTagsContent")
        self.labelTagsContent.setWordWrap(True)
        sizePolicy.setHeightForWidth(self.labelTagsContent.sizePolicy().hasHeightForWidth())
        self.labelTagsContent.setSizePolicy(sizePolicy)

        self.verticalLayoutTags.addWidget(self.labelTagsContent)


        self.verticalLayoutAnnotationSummary.addWidget(self.groupBoxTags)

        self.groupBoxCaptions = QGroupBox(self.groupBoxAnnotationSummary)
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


        self.verticalLayoutAnnotationSummary.addWidget(self.groupBoxCaptions)

        self.gridLayoutRatingScore = QGridLayout()
        self.gridLayoutRatingScore.setObjectName(u"gridLayoutRatingScore")
        self.labelRating = QLabel(self.groupBoxAnnotationSummary)
        self.labelRating.setObjectName(u"labelRating")
        sizePolicy.setHeightForWidth(self.labelRating.sizePolicy().hasHeightForWidth())
        self.labelRating.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelRating, 0, 0, 1, 1)

        self.labelRatingValue = QLabel(self.groupBoxAnnotationSummary)
        self.labelRatingValue.setObjectName(u"labelRatingValue")
        self.labelRatingValue.setVisible(False)
        sizePolicy.setHeightForWidth(self.labelRatingValue.sizePolicy().hasHeightForWidth())
        self.labelRatingValue.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelRatingValue, 0, 1, 1, 1)

        self.comboBoxRating = QComboBox(self.groupBoxAnnotationSummary)
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.addItem("")
        self.comboBoxRating.setObjectName(u"comboBoxRating")
        self.comboBoxRating.setVisible(True)
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.comboBoxRating.sizePolicy().hasHeightForWidth())
        self.comboBoxRating.setSizePolicy(sizePolicy2)

        self.gridLayoutRatingScore.addWidget(self.comboBoxRating, 0, 1, 1, 1)

        self.pushButtonSaveRating = QPushButton(self.groupBoxAnnotationSummary)
        self.pushButtonSaveRating.setObjectName(u"pushButtonSaveRating")
        self.pushButtonSaveRating.setVisible(True)
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.pushButtonSaveRating.sizePolicy().hasHeightForWidth())
        self.pushButtonSaveRating.setSizePolicy(sizePolicy3)

        self.gridLayoutRatingScore.addWidget(self.pushButtonSaveRating, 0, 2, 1, 1)

        self.labelScore = QLabel(self.groupBoxAnnotationSummary)
        self.labelScore.setObjectName(u"labelScore")
        sizePolicy.setHeightForWidth(self.labelScore.sizePolicy().hasHeightForWidth())
        self.labelScore.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelScore, 1, 0, 1, 1)

        self.labelScoreValue = QLabel(self.groupBoxAnnotationSummary)
        self.labelScoreValue.setObjectName(u"labelScoreValue")
        self.labelScoreValue.setVisible(False)
        sizePolicy.setHeightForWidth(self.labelScoreValue.sizePolicy().hasHeightForWidth())
        self.labelScoreValue.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelScoreValue, 1, 1, 1, 1)

        self.sliderScore = QSlider(self.groupBoxAnnotationSummary)
        self.sliderScore.setObjectName(u"sliderScore")
        self.sliderScore.setMinimum(0)
        self.sliderScore.setMaximum(1000)
        self.sliderScore.setValue(500)
        self.sliderScore.setOrientation(Qt.Orientation.Horizontal)
        self.sliderScore.setVisible(True)

        self.gridLayoutRatingScore.addWidget(self.sliderScore, 1, 1, 1, 1)

        self.pushButtonSaveScore = QPushButton(self.groupBoxAnnotationSummary)
        self.pushButtonSaveScore.setObjectName(u"pushButtonSaveScore")
        self.pushButtonSaveScore.setVisible(True)
        sizePolicy3.setHeightForWidth(self.pushButtonSaveScore.sizePolicy().hasHeightForWidth())
        self.pushButtonSaveScore.setSizePolicy(sizePolicy3)

        self.gridLayoutRatingScore.addWidget(self.pushButtonSaveScore, 1, 2, 1, 1)


        self.verticalLayoutAnnotationSummary.addLayout(self.gridLayoutRatingScore)


        self.verticalLayoutMain.addWidget(self.groupBoxAnnotationSummary)

        self.annotationDataDisplay = AnnotationDataDisplayWidget(SelectedImageDetailsWidget)
        self.annotationDataDisplay.setObjectName(u"annotationDataDisplay")
        sizePolicy1.setHeightForWidth(self.annotationDataDisplay.sizePolicy().hasHeightForWidth())
        self.annotationDataDisplay.setSizePolicy(sizePolicy1)

        self.verticalLayoutMain.addWidget(self.annotationDataDisplay)


        self.retranslateUi(SelectedImageDetailsWidget)
        self.comboBoxRating.currentTextChanged.connect(SelectedImageDetailsWidget._on_rating_changed)
        self.sliderScore.valueChanged.connect(SelectedImageDetailsWidget._on_score_changed)
        self.pushButtonSaveRating.clicked.connect(SelectedImageDetailsWidget._on_save_clicked)
        self.pushButtonSaveScore.clicked.connect(SelectedImageDetailsWidget._on_save_clicked)
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
        self.groupBoxAnnotationSummary.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30a2\u30ce\u30c6\u30fc\u30b7\u30e7\u30f3\u6982\u8981", None))
        self.groupBoxTags.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30bf\u30b0", None))
        self.labelTagsContent.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"cat, sitting, outdoor, wooden", None))
        self.groupBoxCaptions.setTitle(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None))
        self.textEditCaptionsContent.setPlaceholderText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u8868\u793a\u3055\u308c\u307e\u3059", None))
        self.labelRating.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"Rating:", None))
        self.labelRatingValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"PG-13", None))
        self.comboBoxRating.setItemText(0, QCoreApplication.translate("SelectedImageDetailsWidget", u"PG", None))
        self.comboBoxRating.setItemText(1, QCoreApplication.translate("SelectedImageDetailsWidget", u"PG-13", None))
        self.comboBoxRating.setItemText(2, QCoreApplication.translate("SelectedImageDetailsWidget", u"R", None))
        self.comboBoxRating.setItemText(3, QCoreApplication.translate("SelectedImageDetailsWidget", u"X", None))
        self.comboBoxRating.setItemText(4, QCoreApplication.translate("SelectedImageDetailsWidget", u"XXX", None))

        self.pushButtonSaveRating.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u4fdd\u5b58", None))
        self.labelScore.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u30b9\u30b3\u30a2:", None))
        self.labelScoreValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"75.4", None))
        self.pushButtonSaveScore.setText(QCoreApplication.translate("SelectedImageDetailsWidget", u"\u4fdd\u5b58", None))
    # retranslateUi

