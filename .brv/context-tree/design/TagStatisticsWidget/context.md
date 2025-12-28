
DB全体統計のUI向けに使用回数はフォーマット別の積み上げヒストグラムへ変更（usage tab）。top tags表示を削除し、summaryにformat別タグ数を追加。

---

The usage statistics in the database's overall statistics UI have been changed to a stacked histogram for each format, available in the 'usage' tab. The 'top tags' display has been removed, and the number of tags for each format has been added to the summary.

---

The `TagStatisticsWidget` class in `genai_tag_db_tools/gui/widgets/tag_statistics.py` is responsible for displaying the tag statistics. The usage chart is implemented as a `QStackedBarSeries` to show usage counts grouped by format.

---

The `_build_usage_chart` function in `genai_tag_db_tools/gui/presenters/tag_statistics_presenter.py` creates the `BarChartData` for the stacked histogram. It buckets tags by usage count and then groups them by format.
