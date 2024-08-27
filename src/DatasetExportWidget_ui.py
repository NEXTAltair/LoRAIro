# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'DatasetExportWidget.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QRadioButton, QSizePolicy, QSplitter,
    QVBoxLayout, QWidget)

from DirectoryPickerWidget import DirectoryPickerWidget
from ImagePreviewWidget import ImagePreviewWidget
from ThumbnailSelectorWidget import ThumbnailSelectorWidget

class Ui_DatasetExportWidget(object):
    def setupUi(self, DatasetExportWidget):
        if not DatasetExportWidget.objectName():
            DatasetExportWidget.setObjectName(u"DatasetExportWidget")
        DatasetExportWidget.resize(1200, 800)
        DatasetExportWidget.setStyleSheet(u"\n"
"    QWidget {\n"
"      background-color: #f0f0f0;\n"
"      color: #333333;\n"
"      font-family: Arial, sans-serif;\n"
"    }\n"
"    QGroupBox {\n"
"      background-color: white;\n"
"      border: 1px solid #cccccc;\n"
"      border-radius: 5px;\n"
"      margin-top: 1ex;\n"
"      font-weight: bold;\n"
"    }\n"
"    QGroupBox::title {\n"
"      subcontrol-origin: margin;\n"
"      left: 10px;\n"
"      padding: 0 3px 0 3px;\n"
"    }\n"
"    QPushButton {\n"
"      background-color: #4CAF50;\n"
"      color: white;\n"
"      border: none;\n"
"      padding: 5px 15px;\n"
"      border-radius: 3px;\n"
"    }\n"
"    QPushButton:hover {\n"
"      background-color: #45a049;\n"
"    }\n"
"    QLineEdit, QComboBox {\n"
"      border: 1px solid #cccccc;\n"
"      padding: 5px;\n"
"      border-radius: 3px;\n"
"    }\n"
"    QProgressBar {\n"
"      border: 1px solid #cccccc;\n"
"      border-radius: 3px;\n"
"      text-align: center;\n"
"    }\n"
"    QProgressBar::chunk {\n"
"      background-color: #4CA"
                        "F50;\n"
"    }\n"
"   ")
        self.mainLayout = QHBoxLayout(DatasetExportWidget)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainSplitter = QSplitter(DatasetExportWidget)
        self.mainSplitter.setObjectName(u"mainSplitter")
        self.mainSplitter.setOrientation(Qt.Orientation.Horizontal)
        self.leftPanel = QWidget(self.mainSplitter)
        self.leftPanel.setObjectName(u"leftPanel")
        self.leftPanelLayout = QVBoxLayout(self.leftPanel)
        self.leftPanelLayout.setObjectName(u"leftPanelLayout")
        self.leftPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.filterGroupBox = QGroupBox(self.leftPanel)
        self.filterGroupBox.setObjectName(u"filterGroupBox")
        self.filterLayout = QVBoxLayout(self.filterGroupBox)
        self.filterLayout.setObjectName(u"filterLayout")
        self.filterTypeLayout = QHBoxLayout()
        self.filterTypeLayout.setObjectName(u"filterTypeLayout")
        self.filterTypeLabel = QLabel(self.filterGroupBox)
        self.filterTypeLabel.setObjectName(u"filterTypeLabel")

        self.filterTypeLayout.addWidget(self.filterTypeLabel)

        self.filterTypeComboBox = QComboBox(self.filterGroupBox)
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.addItem("")
        self.filterTypeComboBox.setObjectName(u"filterTypeComboBox")

        self.filterTypeLayout.addWidget(self.filterTypeComboBox)

        self.andRadioButton = QRadioButton(self.filterGroupBox)
        self.andRadioButton.setObjectName(u"andRadioButton")

        self.filterTypeLayout.addWidget(self.andRadioButton)


        self.filterLayout.addLayout(self.filterTypeLayout)

        self.filterLineEdit = QLineEdit(self.filterGroupBox)
        self.filterLineEdit.setObjectName(u"filterLineEdit")

        self.filterLayout.addWidget(self.filterLineEdit)

        self.resolutionLayout = QHBoxLayout()
        self.resolutionLayout.setObjectName(u"resolutionLayout")
        self.resolutionLabel = QLabel(self.filterGroupBox)
        self.resolutionLabel.setObjectName(u"resolutionLabel")

        self.resolutionLayout.addWidget(self.resolutionLabel)

        self.resolutionComboBox = QComboBox(self.filterGroupBox)
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.addItem("")
        self.resolutionComboBox.setObjectName(u"resolutionComboBox")

        self.resolutionLayout.addWidget(self.resolutionComboBox)


        self.filterLayout.addLayout(self.resolutionLayout)

        self.applyFilterButton = QPushButton(self.filterGroupBox)
        self.applyFilterButton.setObjectName(u"applyFilterButton")
        icon = QIcon()
        icon.addFile(u":/icons/filter.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.applyFilterButton.setIcon(icon)

        self.filterLayout.addWidget(self.applyFilterButton)


        self.leftPanelLayout.addWidget(self.filterGroupBox)

        self.thumbnailSelector = ThumbnailSelectorWidget(self.leftPanel)
        self.thumbnailSelector.setObjectName(u"thumbnailSelector")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.thumbnailSelector.sizePolicy().hasHeightForWidth())
        self.thumbnailSelector.setSizePolicy(sizePolicy)

        self.leftPanelLayout.addWidget(self.thumbnailSelector)

        self.imageCountLabel = QLabel(self.leftPanel)
        self.imageCountLabel.setObjectName(u"imageCountLabel")
        self.imageCountLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.leftPanelLayout.addWidget(self.imageCountLabel)

        self.mainSplitter.addWidget(self.leftPanel)
        self.rightPanel = QWidget(self.mainSplitter)
        self.rightPanel.setObjectName(u"rightPanel")
        self.rightPanelLayout = QVBoxLayout(self.rightPanel)
        self.rightPanelLayout.setObjectName(u"rightPanelLayout")
        self.rightPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.imagePreview = ImagePreviewWidget(self.rightPanel)
        self.imagePreview.setObjectName(u"imagePreview")
        sizePolicy.setHeightForWidth(self.imagePreview.sizePolicy().hasHeightForWidth())
        self.imagePreview.setSizePolicy(sizePolicy)

        self.rightPanelLayout.addWidget(self.imagePreview)

        self.exportGroupBox = QGroupBox(self.rightPanel)
        self.exportGroupBox.setObjectName(u"exportGroupBox")
        self.exportLayout = QVBoxLayout(self.exportGroupBox)
        self.exportLayout.setObjectName(u"exportLayout")
        self.exportDirectoryPicker = DirectoryPickerWidget(self.exportGroupBox)
        self.exportDirectoryPicker.setObjectName(u"exportDirectoryPicker")

        self.exportLayout.addWidget(self.exportDirectoryPicker)

        self.exportFormatLabel = QLabel(self.exportGroupBox)
        self.exportFormatLabel.setObjectName(u"exportFormatLabel")

        self.exportLayout.addWidget(self.exportFormatLabel)

        self.exportFormatLayout = QHBoxLayout()
        self.exportFormatLayout.setObjectName(u"exportFormatLayout")
        self.checkBoxTxtCap = QCheckBox(self.exportGroupBox)
        self.checkBoxTxtCap.setObjectName(u"checkBoxTxtCap")
        self.checkBoxTxtCap.setChecked(True)

        self.exportFormatLayout.addWidget(self.checkBoxTxtCap)

        self.checkBoxJson = QCheckBox(self.exportGroupBox)
        self.checkBoxJson.setObjectName(u"checkBoxJson")

        self.exportFormatLayout.addWidget(self.checkBoxJson)


        self.exportLayout.addLayout(self.exportFormatLayout)

        self.exportButton = QPushButton(self.exportGroupBox)
        self.exportButton.setObjectName(u"exportButton")
        icon1 = QIcon()
        icon1.addFile(u":/icons/export.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.exportButton.setIcon(icon1)

        self.exportLayout.addWidget(self.exportButton)

        self.exportProgressBar = QProgressBar(self.exportGroupBox)
        self.exportProgressBar.setObjectName(u"exportProgressBar")
        self.exportProgressBar.setValue(0)

        self.exportLayout.addWidget(self.exportProgressBar)

        self.statusLabel = QLabel(self.exportGroupBox)
        self.statusLabel.setObjectName(u"statusLabel")

        self.exportLayout.addWidget(self.statusLabel)


        self.rightPanelLayout.addWidget(self.exportGroupBox)

        self.mainSplitter.addWidget(self.rightPanel)

        self.mainLayout.addWidget(self.mainSplitter)


        self.retranslateUi(DatasetExportWidget)

        QMetaObject.connectSlotsByName(DatasetExportWidget)
    # setupUi

    def retranslateUi(self, DatasetExportWidget):
        DatasetExportWidget.setWindowTitle(QCoreApplication.translate("DatasetExportWidget", u"Dataset Export", None))
        self.filterGroupBox.setTitle(QCoreApplication.translate("DatasetExportWidget", u"Filter Criteria", None))
        self.filterTypeLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Filter Type:", None))
        self.filterTypeComboBox.setItemText(0, QCoreApplication.translate("DatasetExportWidget", u"Tags", None))
        self.filterTypeComboBox.setItemText(1, QCoreApplication.translate("DatasetExportWidget", u"Caption", None))

        self.andRadioButton.setText(QCoreApplication.translate("DatasetExportWidget", u"AND\u691c\u7d22", None))
        self.filterLineEdit.setPlaceholderText(QCoreApplication.translate("DatasetExportWidget", u"Enter filter criteria", None))
        self.resolutionLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"\u5b66\u7fd2\u89e3\u50cf\u5ea6:", None))
        self.resolutionComboBox.setItemText(0, QCoreApplication.translate("DatasetExportWidget", u"512x512", None))
        self.resolutionComboBox.setItemText(1, QCoreApplication.translate("DatasetExportWidget", u"768x768", None))
        self.resolutionComboBox.setItemText(2, QCoreApplication.translate("DatasetExportWidget", u"1024x1024", None))

        self.applyFilterButton.setText(QCoreApplication.translate("DatasetExportWidget", u"Apply Filters", None))
        self.imageCountLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Selected Images: 0 / Total Images: 0", None))
        self.exportGroupBox.setTitle(QCoreApplication.translate("DatasetExportWidget", u"Export Settings", None))
        self.exportFormatLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Format:", None))
        self.checkBoxTxtCap.setText(QCoreApplication.translate("DatasetExportWidget", u"txt/caption", None))
        self.checkBoxJson.setText(QCoreApplication.translate("DatasetExportWidget", u"metadata.json", None))
        self.exportButton.setText(QCoreApplication.translate("DatasetExportWidget", u"Export Dataset", None))
        self.statusLabel.setText(QCoreApplication.translate("DatasetExportWidget", u"Status: Ready", None))
    # retranslateUi

