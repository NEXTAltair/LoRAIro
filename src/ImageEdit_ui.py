# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ImageEdit.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QGraphicsView,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QSpacerItem,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget)

class Ui_ImageEditWidget(object):
    def setupUi(self, ImageEditWidget):
        if not ImageEditWidget.objectName():
            ImageEditWidget.setObjectName(u"ImageEditWidget")
        ImageEditWidget.resize(1200, 800)
        self.verticalLayout_Main = QVBoxLayout(ImageEditWidget)
        self.verticalLayout_Main.setObjectName(u"verticalLayout_Main")
        self.label_Title = QLabel(ImageEditWidget)
        self.label_Title.setObjectName(u"label_Title")

        self.verticalLayout_Main.addWidget(self.label_Title)

        self.widget_DatasetSelector = QWidget(ImageEditWidget)
        self.widget_DatasetSelector.setObjectName(u"widget_DatasetSelector")
        self.horizontalLayout_DatasetSelector = QHBoxLayout(self.widget_DatasetSelector)
        self.horizontalLayout_DatasetSelector.setObjectName(u"horizontalLayout_DatasetSelector")
        self.label_DatasetDir = QLabel(self.widget_DatasetSelector)
        self.label_DatasetDir.setObjectName(u"label_DatasetDir")

        self.horizontalLayout_DatasetSelector.addWidget(self.label_DatasetDir)

        self.lineEdit_DatasetPath = QLineEdit(self.widget_DatasetSelector)
        self.lineEdit_DatasetPath.setObjectName(u"lineEdit_DatasetPath")

        self.horizontalLayout_DatasetSelector.addWidget(self.lineEdit_DatasetPath)

        self.pushButton_SelectDataset = QPushButton(self.widget_DatasetSelector)
        self.pushButton_SelectDataset.setObjectName(u"pushButton_SelectDataset")

        self.horizontalLayout_DatasetSelector.addWidget(self.pushButton_SelectDataset)


        self.verticalLayout_Main.addWidget(self.widget_DatasetSelector)

        self.splitter_MainContent = QSplitter(ImageEditWidget)
        self.splitter_MainContent.setObjectName(u"splitter_MainContent")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.splitter_MainContent.sizePolicy().hasHeightForWidth())
        self.splitter_MainContent.setSizePolicy(sizePolicy)
        self.splitter_MainContent.setOrientation(Qt.Orientation.Horizontal)
        self.tableWidget_ImageList = QTableWidget(self.splitter_MainContent)
        if (self.tableWidget_ImageList.columnCount() < 6):
            self.tableWidget_ImageList.setColumnCount(6)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        __qtablewidgetitem4 = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(4, __qtablewidgetitem4)
        __qtablewidgetitem5 = QTableWidgetItem()
        self.tableWidget_ImageList.setHorizontalHeaderItem(5, __qtablewidgetitem5)
        self.tableWidget_ImageList.setObjectName(u"tableWidget_ImageList")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy1.setHorizontalStretch(2)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.tableWidget_ImageList.sizePolicy().hasHeightForWidth())
        self.tableWidget_ImageList.setSizePolicy(sizePolicy1)
        self.tableWidget_ImageList.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.splitter_MainContent.addWidget(self.tableWidget_ImageList)
        self.tableWidget_ImageList.horizontalHeader().setMinimumSectionSize(50)
        self.tableWidget_ImageList.horizontalHeader().setDefaultSectionSize(126)
        self.tableWidget_ImageList.horizontalHeader().setStretchLastSection(True)
        self.tableWidget_ImageList.verticalHeader().setMinimumSectionSize(50)
        self.tableWidget_ImageList.verticalHeader().setDefaultSectionSize(126)
        self.widget_PreviewArea = QWidget(self.splitter_MainContent)
        self.widget_PreviewArea.setObjectName(u"widget_PreviewArea")
        self.verticalLayout_PreviewArea = QVBoxLayout(self.widget_PreviewArea)
        self.verticalLayout_PreviewArea.setObjectName(u"verticalLayout_PreviewArea")
        self.verticalLayout_PreviewArea.setContentsMargins(0, 0, 0, 0)
        self.label_PreviewTitle = QLabel(self.widget_PreviewArea)
        self.label_PreviewTitle.setObjectName(u"label_PreviewTitle")

        self.verticalLayout_PreviewArea.addWidget(self.label_PreviewTitle)

        self.graphicsView_Preview = QGraphicsView(self.widget_PreviewArea)
        self.graphicsView_Preview.setObjectName(u"graphicsView_Preview")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.graphicsView_Preview.sizePolicy().hasHeightForWidth())
        self.graphicsView_Preview.setSizePolicy(sizePolicy2)

        self.verticalLayout_PreviewArea.addWidget(self.graphicsView_Preview)

        self.splitter_MainContent.addWidget(self.widget_PreviewArea)

        self.verticalLayout_Main.addWidget(self.splitter_MainContent)

        self.horizontalLayout_ControlArea = QHBoxLayout()
        self.horizontalLayout_ControlArea.setObjectName(u"horizontalLayout_ControlArea")
        self.groupBox_EditOptions = QGroupBox(ImageEditWidget)
        self.groupBox_EditOptions.setObjectName(u"groupBox_EditOptions")
        self.horizontalLayout_EditOptions = QHBoxLayout(self.groupBox_EditOptions)
        self.horizontalLayout_EditOptions.setObjectName(u"horizontalLayout_EditOptions")
        self.label_ResizeOption = QLabel(self.groupBox_EditOptions)
        self.label_ResizeOption.setObjectName(u"label_ResizeOption")

        self.horizontalLayout_EditOptions.addWidget(self.label_ResizeOption)

        self.comboBox_ResizeOption = QComboBox(self.groupBox_EditOptions)
        self.comboBox_ResizeOption.addItem("")
        self.comboBox_ResizeOption.addItem("")
        self.comboBox_ResizeOption.addItem("")
        self.comboBox_ResizeOption.setObjectName(u"comboBox_ResizeOption")

        self.horizontalLayout_EditOptions.addWidget(self.comboBox_ResizeOption)

        self.label_Upscaler = QLabel(self.groupBox_EditOptions)
        self.label_Upscaler.setObjectName(u"label_Upscaler")

        self.horizontalLayout_EditOptions.addWidget(self.label_Upscaler)

        self.comboBox_Upscaler = QComboBox(self.groupBox_EditOptions)
        self.comboBox_Upscaler.setObjectName(u"comboBox_Upscaler")

        self.horizontalLayout_EditOptions.addWidget(self.comboBox_Upscaler)


        self.horizontalLayout_ControlArea.addWidget(self.groupBox_EditOptions)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayout_ControlArea.addItem(self.horizontalSpacer)

        self.pushButton_StartProcess = QPushButton(ImageEditWidget)
        self.pushButton_StartProcess.setObjectName(u"pushButton_StartProcess")

        self.horizontalLayout_ControlArea.addWidget(self.pushButton_StartProcess)


        self.verticalLayout_Main.addLayout(self.horizontalLayout_ControlArea)


        self.retranslateUi(ImageEditWidget)

        QMetaObject.connectSlotsByName(ImageEditWidget)
    # setupUi

    def retranslateUi(self, ImageEditWidget):
        ImageEditWidget.setWindowTitle(QCoreApplication.translate("ImageEditWidget", u"\u753b\u50cf\u7de8\u96c6", None))
        self.label_Title.setText(QCoreApplication.translate("ImageEditWidget", u"\u753b\u50cf\u7de8\u96c6", None))
        self.label_DatasetDir.setText(QCoreApplication.translate("ImageEditWidget", u"\u30c7\u30fc\u30bf\u30bb\u30c3\u30c8\u30c7\u30a3\u30ec\u30af\u30c8\u30ea", None))
        self.pushButton_SelectDataset.setText(QCoreApplication.translate("ImageEditWidget", u"\u9078\u629e", None))
        ___qtablewidgetitem = self.tableWidget_ImageList.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("ImageEditWidget", u"\u30b5\u30e0\u30cd\u30a4\u30eb", None));
        ___qtablewidgetitem1 = self.tableWidget_ImageList.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d5\u30a1\u30a4\u30eb\u540d", None));
        ___qtablewidgetitem2 = self.tableWidget_ImageList.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d1\u30b9", None));
        ___qtablewidgetitem3 = self.tableWidget_ImageList.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("ImageEditWidget", u"\u30b5\u30a4\u30ba", None));
        ___qtablewidgetitem4 = self.tableWidget_ImageList.horizontalHeaderItem(4)
        ___qtablewidgetitem4.setText(QCoreApplication.translate("ImageEditWidget", u"\u65e2\u5b58\u30bf\u30b0", None));
        ___qtablewidgetitem5 = self.tableWidget_ImageList.horizontalHeaderItem(5)
        ___qtablewidgetitem5.setText(QCoreApplication.translate("ImageEditWidget", u"\u65e2\u5b58\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3", None));
        self.label_PreviewTitle.setText(QCoreApplication.translate("ImageEditWidget", u"\u30d7\u30ec\u30d3\u30e5\u30fc", None))
        self.groupBox_EditOptions.setTitle(QCoreApplication.translate("ImageEditWidget", u"\u7de8\u96c6\u30aa\u30d7\u30b7\u30e7\u30f3", None))
        self.label_ResizeOption.setText(QCoreApplication.translate("ImageEditWidget", u"\u30ea\u30b5\u30a4\u30ba:", None))
        self.comboBox_ResizeOption.setItemText(0, QCoreApplication.translate("ImageEditWidget", u"512x512", None))
        self.comboBox_ResizeOption.setItemText(1, QCoreApplication.translate("ImageEditWidget", u"768x768", None))
        self.comboBox_ResizeOption.setItemText(2, QCoreApplication.translate("ImageEditWidget", u"1024x1024", None))

        self.label_Upscaler.setText(QCoreApplication.translate("ImageEditWidget", u"\u30a2\u30c3\u30d7\u30b9\u30b1\u30fc\u30e9\u30fc", None))
        self.pushButton_StartProcess.setText(QCoreApplication.translate("ImageEditWidget", u"\u51e6\u7406\u958b\u59cb", None))
    # retranslateUi

