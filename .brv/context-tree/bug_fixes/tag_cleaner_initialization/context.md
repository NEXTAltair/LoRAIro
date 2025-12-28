
class TagCleanerWidget(QWidget, Ui_TagCleanerWidget):
    ...
    def set_service(self, cleaner_service: TagCleanerService) -> None:
        """Set service instance (initialization deferred to showEvent)."""
        self._cleaner_service = cleaner_service
        self._initialized = False
        if self.isVisible():
            self._initialize_ui()
            self._initialized = True

    def showEvent(self, event: QShowEvent) -> None:
        """Initialize UI when widget is first shown."""
        if self._cleaner_service and not self._initialized:
            self._initialize_ui()
            self._initialized = True
        super().showEvent(event)

    def _initialize_ui(self) -> None:
        """Initialize UI elements with service data."""
        formats = self._cleaner_service.get_tag_formats()
        self.comboBoxFormat.clear()
        self.comboBoxFormat.addItems(formats)
        default_index = self.comboBoxFormat.findText("danbooru", Qt.MatchFixedString)
        if default_index >= 0:
            self.comboBoxFormat.setCurrentIndex(default_index)
