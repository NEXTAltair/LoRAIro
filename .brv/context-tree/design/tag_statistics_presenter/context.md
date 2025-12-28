
## Relations
@structure/tag_statistics_service

The presenter builds charts for tag statistics, including Tag Types by Format (bar), Usage by Format (pie), Translations by Language (bar), and the top 10 tags by summed usage (currently by TagID).

---

'''python
def build_statistics_view(
    general_stats: dict,
    usage_df: pl.DataFrame,
    type_dist_df: pl.DataFrame,
    translation_df: pl.DataFrame,
) -> TagStatisticsView:
    return TagStatisticsView(
        summary_text=_build_summary_text(general_stats),
        distribution=_build_distribution_chart(type_dist_df),
        usage=_build_usage_chart(usage_df),
        language=_build_language_chart(translation_df),
    )
'''
