
################################################################################
## Form generated from reading UI file 'ThumbnailSelectorWidget.ui'
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
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


class Ui_ThumbnailSelectorWidget:
    def setupUi(self, ThumbnailSelectorWidget):
        if not ThumbnailSelectorWidget.objectName():
            ThumbnailSelectorWidget.setObjectName("ThumbnailSelectorWidget")
        self.verticalLayout = QVBoxLayout(ThumbnailSelectorWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.frameThumbnailHeader = QFrame(ThumbnailSelectorWidget)
        self.frameThumbnailHeader.setObjectName("frameThumbnailHeader")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frameThumbnailHeader.sizePolicy().hasHeightForWidth())
        self.frameThumbnailHeader.setSizePolicy(sizePolicy)
        self.frameThumbnailHeader.setFrameShape(QFrame.Shape.NoFrame)
        self.horizontalLayoutThumbnailHeader = QHBoxLayout(self.frameThumbnailHeader)
        self.horizontalLayoutThumbnailHeader.setObjectName("horizontalLayoutThumbnailHeader")
        self.horizontalLayoutThumbnailHeader.setContentsMargins(0, 0, 0, 0)
        self.labelThumbnailCount = QLabel(self.frameThumbnailHeader)
        self.labelThumbnailCount.setObjectName("labelThumbnailCount")

        self.horizontalLayoutThumbnailHeader.addWidget(self.labelThumbnailCount)

        self.horizontalSpacerThumbnailHeader = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutThumbnailHeader.addItem(self.horizontalSpacerThumbnailHeader)

        self.labelThumbnailSize = QLabel(self.frameThumbnailHeader)
        self.labelThumbnailSize.setObjectName("labelThumbnailSize")

        self.horizontalLayoutThumbnailHeader.addWidget(self.labelThumbnailSize)

        self.sliderThumbnailSize = QSlider(self.frameThumbnailHeader)
        self.sliderThumbnailSize.setObjectName("sliderThumbnailSize")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.sliderThumbnailSize.sizePolicy().hasHeightForWidth())
        self.sliderThumbnailSize.setSizePolicy(sizePolicy1)
        self.sliderThumbnailSize.setMinimum(64)
        self.sliderThumbnailSize.setMaximum(256)
        self.sliderThumbnailSize.setValue(128)
        self.sliderThumbnailSize.setOrientation(Qt.Orientation.Horizontal)

        self.horizontalLayoutThumbnailHeader.addWidget(self.sliderThumbnailSize)


        self.verticalLayout.addWidget(self.frameThumbnailHeader)

        self.scrollAreaThumbnails = QScrollArea(ThumbnailSelectorWidget)
        self.scrollAreaThumbnails.setObjectName("scrollAreaThumbnails")
        self.scrollAreaThumbnails.setWidgetResizable(True)
        self.widgetThumbnailsContent = QWidget()
        self.widgetThumbnailsContent.setObjectName("widgetThumbnailsContent")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.widgetThumbnailsContent.sizePolicy().hasHeightForWidth())
        self.widgetThumbnailsContent.setSizePolicy(sizePolicy2)
        self.scrollAreaThumbnails.setWidget(self.widgetThumbnailsContent)

        self.verticalLayout.addWidget(self.scrollAreaThumbnails)


        self.retranslateUi(ThumbnailSelectorWidget)
        self.sliderThumbnailSize.valueChanged.connect(ThumbnailSelectorWidget._on_thumbnail_size_slider_changed)

        QMetaObject.connectSlotsByName(ThumbnailSelectorWidget)
    # setupUi

    def retranslateUi(self, ThumbnailSelectorWidget):
        self.labelThumbnailCount.setText(QCoreApplication.translate("ThumbnailSelectorWidget", "\u753b\u50cf: 0\u4ef6", None))
        self.labelThumbnailSize.setText(QCoreApplication.translate("ThumbnailSelectorWidget", "\u30b5\u30a4\u30ba:", None))
        pass
    # retranslateUi

