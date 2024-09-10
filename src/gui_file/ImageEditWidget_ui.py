# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ImageEditWidget.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSizePolicy, QSpacerItem, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ImagePreviewWidget import ImagePreviewWidget

class Ui_ImageEditWidget(object):
    def setupUi(self, ImageEditWidget):
        if not ImageEditWidget.objectName():
            ImageEditWidget.setObjectName(u"ImageEditWidget")
        ImageEditWidget.resize(758, 781)
        self.verticalLayout = QVBoxLayout(ImageEditWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.splitterMainContent = QSplitter(ImageEditWidget)
        self.splitterMainContent.setObjectName(u"splitterMainContent")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(2)
        sizePolicy.setHeightForWidth(self.splitterMainContent.sizePolicy().hasHeightForWidth())
        self.splitterMainContent.setSizePolicy(sizePolicy)
        self.splitterMainContent.setOrientation(Qt.Orientation.Horizontal)
        self.tableWidgetImageList = QTableWidget(self.splitterMainContent)
        if (self.tableWidgetImageList.columnCount() < 6):
            self.tableWidgetImageList.setColumnCount(6)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidgetImageList.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        self.tableWidgetImageList.setObjectName(u"tableWidgetImageList")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(1)
        sizePolicy1.setVerticalStretch(2)
        sizePolicy1.setHeightForWidth(self.tableWidgetImageList.sizePolicy().hasHeightForWidth())
        self.tableWidgetImageList.setSizePolicy(sizePolicy1)
        self.tableWidgetImageList.setFrameShape(QFrame.Shape.StyledPanel)
        self.tableWidgetImageList.setFrameShadow(QFrame.Shadow.Sunken)
        self.tableWidgetImageList.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.splitterMainContent.addWidget(self.tableWidgetImageList)
        self.tableWidgetImageList.horizontalHeader().setCascadingSectionResizes(False)
        self.tableWidgetImageList.horizontalHeader().setMinimumSectionSize(0)
        self.tableWidgetImageList.horizontalHeader().setDefaultSectionSize(0)
        self.tableWidgetImageList.horizontalHeader().setHighlightSections(True)
        self.tableWidgetImageList.horizontalHeader().setStretchLastSection(False)
        self.tableWidgetImageList.verticalHeader().setVisible(False)
        self.tableWidgetImageList.verticalHeader().setMinimumSectionSize(50)
        self.tableWidgetImageList.verticalHeader().setDefaultSectionSize(126)
        self.tableWidgetImageList.verticalHeader().setHighlightSections(False)
        self.widget_PreviewArea_2 = QWidget(self.splitterMainContent)
        self.widget_PreviewArea_2.setObjectName(u"widget_PreviewArea_2")
        self.verticalImagePreview = QVBoxLayout(self.widget_PreviewArea_2)
        self.verticalImagePreview.setSpacing(0)
        self.verticalImagePreview.setObjectName(u"verticalImagePreview")
        self.verticalImagePreview.setContentsMargins(0, 0, 0, 0)
        self.ImagePreview = ImagePreviewWidget(self.widget_PreviewArea_2)
        self.ImagePreview.setObjectName(u"ImagePreview")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.ImagePreview.sizePolicy().hasHeightForWidth())
        self.ImagePreview.setSizePolicy(sizePolicy2)
        self.ImagePreview.setMinimumSize(QSize(126, 0))
        self.labelPreviewTitle = QLabel(self.ImagePreview)
        self.labelPreviewTitle.setObjectName(u"labelPreviewTitle")
        self.labelPreviewTitle.setGeometry(QRect(0, 0, 177, 21))
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.labelPreviewTitle.sizePolicy().hasHeightForWidth())
        self.labelPreviewTitle.setSizePolicy(sizePolicy3)

        self.verticalImagePreview.addWidget(self.ImagePreview)

        self.splitterMainContent.addWidget(self.widget_PreviewArea_2)

        self.verticalLayout.addWidget(self.splitterMainContent)

        self.horizontalLayoutControlArea = QHBoxLayout()
        self.horizontalLayoutControlArea.setObjectName(u"horizontalLayoutControlArea")
        self.groupBoxEditOptions = QGroupBox(ImageEditWidget)
        self.groupBoxEditOptions.setObjectName(u"groupBoxEditOptions")
        self.horizontalLayout_EditOptions_2 = QHBoxLayout(self.groupBoxEditOptions)
        self.horizontalLayout_EditOptions_2.setObjectName(u"horizontalLayout_EditOptions_2")
        self.labelResizeOption = QLabel(self.groupBoxEditOptions)
        self.labelResizeOption.setObjectName(u"labelResizeOption")

        self.horizontalLayout_EditOptions_2.addWidget(self.labelResizeOption)

        self.comboBoxResizeOption = QComboBox(self.groupBoxEditOptions)
        self.comboBoxResizeOption.addItem("")
        self.comboBoxResizeOption.addItem("")
        self.comboBoxResizeOption.addItem("")
        self.comboBoxResizeOption.setObjectName(u"comboBoxResizeOption")

        self.horizontalLayout_EditOptions_2.addWidget(self.comboBoxResizeOption)

        self.labelUpscaler = QLabel(self.groupBoxEditOptions)
        self.labelUpscaler.setObjectName(u"labelUpscaler")

        self.horizontalLayout_EditOptions_2.addWidget(self.labelUpscaler)

        self.comboBoxUpscaler = QComboBox(self.groupBoxEditOptions)
        self.comboBoxUpscaler.addItem("")
        self.comboBoxUpscaler.addItem("")
        self.comboBoxUpscaler.setObjectName(u"comboBoxUpscaler")
        self.comboBoxUpscaler.setCurrentText(u"None")

        self.horizontalLayout_EditOptions_2.addWidget(self.comboBoxUpscaler)


        self.horizontalLayoutControlArea.addWidget(self.groupBoxEditOptions)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutControlArea.addItem(self.horizontalSpacer)

        self.pushButtonStartProcess = QPushButton(ImageEditWidget)
        self.pushButtonStartProcess.setObjectName(u"pushButtonStartProcess")

        self.horizontalLayoutControlArea.addWidget(self.pushButtonStartProcess)


        self.verticalLayout.addLayout(self.horizontalLayoutControlArea)


        self.retranslateUi(ImageEditWidget)

        QMetaObject.connectSlotsByName(ImageEditWidget)
    # setupUi

    def retranslateUi(self, ImageEditWidget):
        ImageEditWidget.setWindowTitle(QCoreApplication.translate("ImageEditWidget", u"Form", None))
        ___qtablewidgetitem = self.tableWidgetImageList.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("ImageEditWidget", u"\u30b5\u30e0\u30cd\u30a4\u30eb", None));
        ___qtablewidgetitem1 = self.tableWidgetImageList.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d", None));
        ___qtablewidgetitem2 = self.tableWidgetImageList.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d1\u30b9", None));
        ___qtablewidgetitem3 = self.tableWidgetImageList.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("ImageEditWidget", u"\u30b5\u30a4\u30ba", None));
        ___qtablewidgetitem4 = self.tableWidgetImageList.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("ImageEditWidget", u"\u65e2\u5b58\u30bf\u30b0", None));
        ___qtablewidgetitem5 = self.tableWidgetImageList.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("ImageEditWidget", u"\u65e2\u5b58\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None));
        self.labelPreviewTitle.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d7\u30ec\u30d3\u30e5\u30fc", None))
        self.groupBoxEditOptions.setTitle(QCoreApplication.translate("ImageEditWidget", u"\u7de8\u96c6\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.labelResizeOption.setText(QCoreApplication.translate("ImageEditWidget", u"\u30ea\u30b5\u30a4\u30ba:", None))
        self.comboBoxResizeOption.setItemText(0, QCoreApplication.translate("ImageEditWidget", u"512x512", None))
        self.comboBoxResizeOption.setItemText(1, QCoreApplication.translate("ImageEditWidget", u"768x768", None))
        self.comboBoxResizeOption.setItemText(2, QCoreApplication.translate("ImageEditWidget", u"1024x1024", None))

        self.labelUpscaler.setText(QCoreApplication.translate("ImageEditWidget", u"\u30a2\u30c3\u30d7\u30b9\u30b1\u30fc\u30e9\u30fc", None))
        self.comboBoxUpscaler.setItemText(0, QCoreApplication.translate("ImageEditWidget", u"None", None))
        self.comboBoxUpscaler.setItemText(1, QCoreApplication.translate("ImageEditWidget", u"RealESRGAN_x4plus", None))

        self.pushButtonStartProcess.setText(QCoreApplication.translate("ImageEditWidget", u"\u51e6\u7406\u958b\u59cb", None))
    # retranslateUi

