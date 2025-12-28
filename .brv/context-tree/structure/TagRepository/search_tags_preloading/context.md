
def search_tags(
        self,
        keyword: str,
        *,
        # ... other params ...
        resolve_preferred: bool = False,
    ) -> list[TagSearchRow]:
        """検索結果を辞書配列で返す。"""
        # ...
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

The `TagRepository.search_tags` method in `db/repository.py` has been updated to utilize the `TagSearchPreloader`. After filtering tag IDs based on the search criteria, it now calls the preloader to fetch all associated data at once. This preloaded data is then passed to the `TagSearchResultBuilder` to assemble the final search results, significantly improving performance by avoiding numerous small queries.
