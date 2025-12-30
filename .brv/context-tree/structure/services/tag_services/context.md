
## Relations
@@bug_fixes/mypy-fixes-gui-services

The application uses several services to manage tags. In `TagRegisterService`, `preferred_tag_id` is now treated as `Optional[int]` and includes a `None` check before being used in `update_tag_status` to prevent errors when an alias is being registered without a preferred tag being immediately available. `TagStatisticsService` now correctly filters out `None` language values from translation statistics and uses `model_dump()` in its `__main__` block to correctly serialize Pydantic models. The base class for GUI services, `GuiServiceBase`, now uses a `# type: ignore[call-overload]` on its `disconnect()` call to handle stub inconsistencies in PySide6.
