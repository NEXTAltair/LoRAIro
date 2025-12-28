
def search_tag_ids(self, keyword: str, partial: bool = False) -> list[int]:
        """tag/source_tag/translationからtag_idを検索する。"""
        keyword, use_like = normalize_search_keyword(keyword, partial)

        with self.session_factory() as session:
            builder = TagSearchQueryBuilder(session)
            tag_ids = builder.initial_tag_ids(keyword, use_like)
            return list(tag_ids)

---

def search_tags(
        self,
        keyword: str,
        *,
        partial: bool = False,
        format_name: str | None = None,
        type_name: str | None = None,
        language: str | None = None,
        min_usage: int | None = None,
        max_usage: int | None = None,
        alias: bool | None = None,
        resolve_preferred: bool = False,
    ) -> list[TagSearchRow]:
        """検索結果を辞書配列で返す。"""
        keyword, use_like = normalize_search_keyword(keyword, partial)

        with self.session_factory() as session:
            builder = TagSearchQueryBuilder(session)
            tag_ids = builder.initial_tag_ids(keyword, use_like)
            if not tag_ids:
                return []

            tag_ids, format_id = builder.apply_format_filter(tag_ids, format_name)
            if not tag_ids:
                return []

            tag_ids = builder.apply_usage_filter(tag_ids, format_id, min_usage, max_usage)
            if not tag_ids:
                return []

            tag_ids = builder.apply_type_filter(tag_ids, format_id, type_name)
            if not tag_ids:
                return []

            tag_ids = builder.apply_alias_filter(tag_ids, format_id, alias)
            if not tag_ids:
                return []

            tag_ids = builder.apply_language_filter(tag_ids, language)
            if not tag_ids:
                return []

            preloader = TagSearchPreloader(session)
            preloaded = preloader.load(tag_ids)

            rows: list[TagSearchRow] = []
            result_builder = TagSearchResultBuilder(
                format_id=format_id,
                resolve_preferred=resolve_preferred,
                logger=self.logger,
            )
            for t_id in sorted(tag_ids):
                row = result_builder.build_row(t_id, preloaded)
                if row is not None:
                    rows.append(row)

            return rows
