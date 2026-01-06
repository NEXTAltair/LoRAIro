################################################################################
## Form generated from reading UI file 'SelectedImageDetailsWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
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
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets.annotation_data_display_widget import AnnotationDataDisplayWidget


class Ui_SelectedImageDetailsWidget:
    def setupUi(self, SelectedImageDetailsWidget):
        if not SelectedImageDetailsWidget.objectName():
            SelectedImageDetailsWidget.setObjectName("SelectedImageDetailsWidget")
        SelectedImageDetailsWidget.resize(250, 400)
        self.verticalLayoutMain = QVBoxLayout(SelectedImageDetailsWidget)
        self.verticalLayoutMain.setSpacing(6)
        self.verticalLayoutMain.setObjectName("verticalLayoutMain")
        self.verticalLayoutMain.setContentsMargins(6, 6, 6, 6)
        self.tabWidgetDetails = QTabWidget(SelectedImageDetailsWidget)
        self.tabWidgetDetails.setObjectName("tabWidgetDetails")
        self.tabOverview = QWidget()
        self.tabOverview.setObjectName("tabOverview")
        self.verticalLayoutOverview = QVBoxLayout(self.tabOverview)
        self.verticalLayoutOverview.setObjectName("verticalLayoutOverview")
        self.groupBoxImageInfo = QGroupBox(self.tabOverview)
        self.groupBoxImageInfo.setObjectName("groupBoxImageInfo")
        self.gridLayoutImageInfo = QGridLayout(self.groupBoxImageInfo)
        self.gridLayoutImageInfo.setSpacing(3)
        self.gridLayoutImageInfo.setObjectName("gridLayoutImageInfo")
        self.labelFileName = QLabel(self.groupBoxImageInfo)
        self.labelFileName.setObjectName("labelFileName")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.labelFileName.sizePolicy().hasHeightForWidth())
        self.labelFileName.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileName, 0, 0, 1, 1)

        self.labelFileSize = QLabel(self.groupBoxImageInfo)
        self.labelFileSize.setObjectName("labelFileSize")
        sizePolicy.setHeightForWidth(self.labelFileSize.sizePolicy().hasHeightForWidth())
        self.labelFileSize.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileSize, 2, 0, 1, 1)

        self.labelFileNameValue = QLabel(self.groupBoxImageInfo)
        self.labelFileNameValue.setObjectName("labelFileNameValue")
        self.labelFileNameValue.setWordWrap(True)
        sizePolicy.setHeightForWidth(self.labelFileNameValue.sizePolicy().hasHeightForWidth())
        self.labelFileNameValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileNameValue, 0, 1, 1, 1)

        self.labelFileSizeValue = QLabel(self.groupBoxImageInfo)
        self.labelFileSizeValue.setObjectName("labelFileSizeValue")
        sizePolicy.setHeightForWidth(self.labelFileSizeValue.sizePolicy().hasHeightForWidth())
        self.labelFileSizeValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelFileSizeValue, 2, 1, 1, 1)

        self.labelCreatedDate = QLabel(self.groupBoxImageInfo)
        self.labelCreatedDate.setObjectName("labelCreatedDate")
        sizePolicy.setHeightForWidth(self.labelCreatedDate.sizePolicy().hasHeightForWidth())
        self.labelCreatedDate.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelCreatedDate, 3, 0, 1, 1)

        self.labelCreatedDateValue = QLabel(self.groupBoxImageInfo)
        self.labelCreatedDateValue.setObjectName("labelCreatedDateValue")
        sizePolicy.setHeightForWidth(self.labelCreatedDateValue.sizePolicy().hasHeightForWidth())
        self.labelCreatedDateValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelCreatedDateValue, 3, 1, 1, 1)

        self.labelImageSizeValue = QLabel(self.groupBoxImageInfo)
        self.labelImageSizeValue.setObjectName("labelImageSizeValue")
        sizePolicy.setHeightForWidth(self.labelImageSizeValue.sizePolicy().hasHeightForWidth())
        self.labelImageSizeValue.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelImageSizeValue, 1, 1, 1, 1)

        self.labelImageSize = QLabel(self.groupBoxImageInfo)
        self.labelImageSize.setObjectName("labelImageSize")
        sizePolicy.setHeightForWidth(self.labelImageSize.sizePolicy().hasHeightForWidth())
        self.labelImageSize.setSizePolicy(sizePolicy)

        self.gridLayoutImageInfo.addWidget(self.labelImageSize, 1, 0, 1, 1)

        self.verticalLayoutOverview.addWidget(self.groupBoxImageInfo)

        self.groupBoxRatingScore = QGroupBox(self.tabOverview)
        self.groupBoxRatingScore.setObjectName("groupBoxRatingScore")
        self.gridLayoutRatingScore = QGridLayout(self.groupBoxRatingScore)
        self.gridLayoutRatingScore.setObjectName("gridLayoutRatingScore")
        self.labelRating = QLabel(self.groupBoxRatingScore)
        self.labelRating.setObjectName("labelRating")
        sizePolicy.setHeightForWidth(self.labelRating.sizePolicy().hasHeightForWidth())
        self.labelRating.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelRating, 0, 0, 1, 1)

        self.labelRatingValue = QLabel(self.groupBoxRatingScore)
        self.labelRatingValue.setObjectName("labelRatingValue")
        sizePolicy.setHeightForWidth(self.labelRatingValue.sizePolicy().hasHeightForWidth())
        self.labelRatingValue.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelRatingValue, 0, 1, 1, 1)

        self.labelScore = QLabel(self.groupBoxRatingScore)
        self.labelScore.setObjectName("labelScore")
        sizePolicy.setHeightForWidth(self.labelScore.sizePolicy().hasHeightForWidth())
        self.labelScore.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelScore, 1, 0, 1, 1)

        self.labelScoreValue = QLabel(self.groupBoxRatingScore)
        self.labelScoreValue.setObjectName("labelScoreValue")
        sizePolicy.setHeightForWidth(self.labelScoreValue.sizePolicy().hasHeightForWidth())
        self.labelScoreValue.setSizePolicy(sizePolicy)

        self.gridLayoutRatingScore.addWidget(self.labelScoreValue, 1, 1, 1, 1)

        self.verticalLayoutOverview.addWidget(self.groupBoxRatingScore)

        self.tabWidgetDetails.addTab(self.tabOverview, "")
        self.tabTags = QWidget()
        self.tabTags.setObjectName("tabTags")
        self.verticalLayoutTagsTab = QVBoxLayout(self.tabTags)
        self.verticalLayoutTagsTab.setObjectName("verticalLayoutTagsTab")
        self.groupBoxTags = QGroupBox(self.tabTags)
        self.groupBoxTags.setObjectName("groupBoxTags")
        self.verticalLayoutTags = QVBoxLayout(self.groupBoxTags)
        self.verticalLayoutTags.setObjectName("verticalLayoutTags")
        self.labelTagsContent = QLabel(self.groupBoxTags)
        self.labelTagsContent.setObjectName("labelTagsContent")
        self.labelTagsContent.setWordWrap(True)
        sizePolicy.setHeightForWidth(self.labelTagsContent.sizePolicy().hasHeightForWidth())
        self.labelTagsContent.setSizePolicy(sizePolicy)

        self.verticalLayoutTags.addWidget(self.labelTagsContent)

        self.verticalLayoutTagsTab.addWidget(self.groupBoxTags)

        self.tabWidgetDetails.addTab(self.tabTags, "")
        self.tabCaptions = QWidget()
        self.tabCaptions.setObjectName("tabCaptions")
        self.verticalLayoutCaptionsTab = QVBoxLayout(self.tabCaptions)
        self.verticalLayoutCaptionsTab.setObjectName("verticalLayoutCaptionsTab")
        self.groupBoxCaptions = QGroupBox(self.tabCaptions)
        self.groupBoxCaptions.setObjectName("groupBoxCaptions")
        self.verticalLayoutCaptions = QVBoxLayout(self.groupBoxCaptions)
        self.verticalLayoutCaptions.setObjectName("verticalLayoutCaptions")
        self.textEditCaptionsContent = QTextEdit(self.groupBoxCaptions)
        self.textEditCaptionsContent.setObjectName("textEditCaptionsContent")
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
        self.tabMetadata.setObjectName("tabMetadata")
        self.verticalLayoutMetadata = QVBoxLayout(self.tabMetadata)
        self.verticalLayoutMetadata.setObjectName("verticalLayoutMetadata")
        self.annotationDataDisplay = AnnotationDataDisplayWidget(self.tabMetadata)
        self.annotationDataDisplay.setObjectName("annotationDataDisplay")
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
        SelectedImageDetailsWidget.setWindowTitle(
            QCoreApplication.translate("SelectedImageDetailsWidget", "Selected Image Details", None)
        )
        self.groupBoxImageInfo.setTitle(
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u753b\u50cf\u60c5\u5831", None)
        )
        self.labelFileName.setText(
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u30d5\u30a1\u30a4\u30eb\u540d:", None
            )
        )
        self.labelFileSize.setText(
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u30d5\u30a1\u30a4\u30eb\u30b5\u30a4\u30ba:", None
            )
        )
        self.labelFileNameValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", "-", None))
        self.labelFileSizeValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", "-", None))
        self.labelCreatedDate.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u767b\u9332\u65e5:", None)
        )
        self.labelCreatedDateValue.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "-", None)
        )
        self.labelImageSizeValue.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "-", None)
        )
        self.labelImageSize.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u89e3\u50cf\u5ea6:", None)
        )
        self.groupBoxRatingScore.setTitle(
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u8a55\u4fa1\u30fb\u30b9\u30b3\u30a2", None
            )
        )
        self.labelRating.setText(QCoreApplication.translate("SelectedImageDetailsWidget", "Rating:", None))
        self.labelRatingValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", "-", None))
        self.labelScore.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u30b9\u30b3\u30a2:", None)
        )
        self.labelScoreValue.setText(QCoreApplication.translate("SelectedImageDetailsWidget", "-", None))
        self.tabWidgetDetails.setTabText(
            self.tabWidgetDetails.indexOf(self.tabOverview),
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u6982\u8981", None),
        )
        self.groupBoxTags.setTitle(
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u30bf\u30b0", None)
        )
        self.labelTagsContent.setText(
            QCoreApplication.translate("SelectedImageDetailsWidget", "cat, sitting, outdoor, wooden", None)
        )
        self.tabWidgetDetails.setTabText(
            self.tabWidgetDetails.indexOf(self.tabTags),
            QCoreApplication.translate("SelectedImageDetailsWidget", "\u30bf\u30b0", None),
        )
        self.groupBoxCaptions.setTitle(
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None
            )
        )
        self.textEditCaptionsContent.setPlaceholderText(
            QCoreApplication.translate(
                "SelectedImageDetailsWidget",
                "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3\u304c\u8868\u793a\u3055\u308c\u307e\u3059",
                None,
            )
        )
        self.tabWidgetDetails.setTabText(
            self.tabWidgetDetails.indexOf(self.tabCaptions),
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None
            ),
        )
        self.tabWidgetDetails.setTabText(
            self.tabWidgetDetails.indexOf(self.tabMetadata),
            QCoreApplication.translate(
                "SelectedImageDetailsWidget", "\u30e1\u30bf\u30c7\u30fc\u30bf", None
            ),
        )

    # retranslateUi
