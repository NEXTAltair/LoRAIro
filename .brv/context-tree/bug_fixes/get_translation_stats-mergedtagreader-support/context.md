
Fix for stats error: TagStatistics.get_translation_stats must use repo.get_all_tag_ids() + repo.get_translations(tag_id) to support MergedTagReader (no list_translations).

---

'''python
    def get_translation_stats(self) -> pl.DataFrame:
        """タグごとの翻訳状況を返す"""
        from collections import defaultdict

        from genai_tag_db_tools.db.schema import TagTranslation

        all_translations = self.repo.list_translations()

        by_tag: dict[int, list[TagTranslation]] = defaultdict(list)
        for tr in all_translations:
            by_tag[tr.tag_id].append(tr)

        rows = []
        for t_id, translations in by_tag.items():
            lang_set = {tr.language for tr in translations}
            rows.append(
                {
                    "tag_id": t_id,
                    "total_translations": len(translations),
                    "languages": sorted(lang_set),
                }
            )
        return pl.DataFrame(rows)
'''
