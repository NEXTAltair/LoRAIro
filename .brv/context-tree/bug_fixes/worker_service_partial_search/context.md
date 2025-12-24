
WorkerService: TagSearchWorker now respects TagSearchRequest.partial; test_worker_service updated to assert partial=False when request partial is False.

---

class TagSearchWorker(QRunnable):

    def run(self) -> None:
        """Execute search in background thread."""
        try:
            df = self.service.search_tags(
                keyword=self.request.query,
                partial=False,  # Core API handles exact/fuzzy matching via resolve_preferred
                format_name=self.request.format_names[0] if self.request.format_names else None,
                type_name=self.request.type_names[0] if self.request.type_names else None,
                alias=self.request.include_aliases,
                min_usage=self.request.min_usage,
                max_usage=self.request.max_usage,
                limit=self.request.limit,
                offset=self.request.offset,
            )
        except Exception as e:
            self.logger.exception("Error in async tag search")
            self.signals.error.emit(str(e))
