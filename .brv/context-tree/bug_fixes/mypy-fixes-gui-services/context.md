
## Relations
@@structure/gui/widgets
@@structure/services/tag_services

CI mypy fixes in genai-tag-db-tools: add Optional annotations for GUI widget attributes in TagSearchWidget; use Qt.MatchFlag.MatchFixedString in TagCleanerWidget; tag service attributes typed Optional in MainWindow; TagRegisterService now treats preferred_tag_id as Optional with None guard before update_tag_status; TagStatistics filters None languages and uses model_dump in __main__ to avoid items() on Pydantic model; GuiServiceBase disconnect uses type: ignore for PySide6 stub.
