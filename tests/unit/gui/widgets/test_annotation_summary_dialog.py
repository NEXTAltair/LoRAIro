"""AnnotationSummaryDialog単体テスト

アノテーション完了サマリーダイアログの表示内容とレイアウトを検証する。
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTextBrowser,
    QTextEdit,
    QWidget,
)

from lorairo.gui.widgets.annotation_summary_dialog import AnnotationSummaryDialog
from lorairo.gui.workers.annotation_worker import (
    AnnotationExecutionResult,
    ImageResultSummary,
    ModelErrorDetail,
)


@pytest.fixture
def success_result() -> AnnotationExecutionResult:
    """全成功のアノテーション結果"""
    return AnnotationExecutionResult(
        results={"phash1": {"gpt-4o-mini": {"tags": ["cat"]}}},
        total_images=5,
        models_used=["gpt-4o-mini"],
        db_save_success=5,
        db_save_skip=0,
        model_errors=[],
        image_summaries=[
            ImageResultSummary(
                file_name="image_001.png",
                tag_count=15,
                has_caption=True,
                score=0.85,
                rating="safe (danbooru4, 0.98)",
            ),
            ImageResultSummary(file_name="image_002.png", tag_count=12, has_caption=True, score=None),
            ImageResultSummary(file_name="image_003.png", tag_count=8, has_caption=False, score=0.72),
        ],
    )


@pytest.fixture
def rating_result() -> AnnotationExecutionResult:
    """レーティングを含むアノテーション結果"""
    return AnnotationExecutionResult(
        results={
            "phash1": {
                "wd-tagger": {
                    "ratings": [
                        {
                            "raw_label": "safe",
                            "source_scheme": "danbooru4",
                            "confidence_score": 0.9876,
                        }
                    ]
                },
                "legacy": {"ratings": ["PG"]},
            }
        },
        total_images=1,
        models_used=["wd-tagger", "legacy"],
        db_save_success=1,
        db_save_skip=0,
        model_errors=[],
        image_summaries=[
            ImageResultSummary(
                file_name="image_001.png",
                tag_count=10,
                has_caption=False,
                score=None,
                rating="safe (danbooru4, 0.99)",
            )
        ],
        phash_to_filename={"phash1": "image_001.png"},
    )


@pytest.fixture
def partial_error_result() -> AnnotationExecutionResult:
    """一部エラーのアノテーション結果"""
    return AnnotationExecutionResult(
        results={"phash1": {"gpt-4o-mini": {"tags": ["cat"]}}},
        total_images=10,
        models_used=["gpt-4o-mini", "claude-3-haiku"],
        db_save_success=8,
        db_save_skip=1,
        model_errors=[
            ModelErrorDetail(
                model_name="claude-3-haiku",
                image_path="image_001.png",
                error_message="Rate limit exceeded",
            ),
        ],
    )


@pytest.fixture
def integrity_violation_result() -> AnnotationExecutionResult:
    """内部整合性違反を含むアノテーション結果"""
    return AnnotationExecutionResult(
        results={"phash1": {"gpt-4o-mini": {"tags": ["cat"]}}},
        total_images=2,
        models_used=["gpt-4o-mini"],
        db_save_success=1,
        db_save_skip=0,
        model_errors=[
            ModelErrorDetail(
                model_name="unknown-model",
                image_path="image_001.png",
                error_message="Annotation result contains unexpected model_id: unknown-model",
                error_type="integrity_violation",
            ),
            ModelErrorDetail(
                model_name="gpt-4o-mini",
                image_path="image_002.png",
                error_message="Rate limit exceeded",
                error_type="result_error",
            ),
        ],
    )


@pytest.fixture
def all_error_result() -> AnnotationExecutionResult:
    """全失敗のアノテーション結果"""
    return AnnotationExecutionResult(
        results={},
        total_images=3,
        models_used=["gpt-4o-mini"],
        db_save_success=0,
        db_save_skip=0,
        model_errors=[
            ModelErrorDetail(
                model_name="gpt-4o-mini",
                image_path=f"image_{i:03d}.png",
                error_message="API Error",
            )
            for i in range(3)
        ],
    )


class TestAnnotationSummaryDialogTitle:
    """ウィンドウタイトルのテスト"""

    def test_success_title(self, qtbot, success_result):
        """全成功時のタイトル"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "アノテーション完了"

    def test_partial_error_title(self, qtbot, partial_error_result):
        """部分エラー時のタイトル"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "アノテーション完了 (一部エラーあり)"

    def test_all_error_title(self, qtbot, all_error_result):
        """全失敗時のタイトル"""
        dialog = AnnotationSummaryDialog(all_error_result)
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "アノテーション完了 (エラー)"


class TestAnnotationSummaryDialogLayout:
    """レイアウト構成のテスト"""

    def test_success_has_no_error_section(self, qtbot, success_result):
        """全成功時にエラー詳細セクションが非表示"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        error_groups = dialog.findChildren(QGroupBox)
        group_titles = [g.title() for g in error_groups]
        assert not any("エラー詳細" in t for t in group_titles)

    def test_error_has_error_section(self, qtbot, partial_error_result):
        """エラー時にエラー詳細セクションが表示される"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        error_groups = dialog.findChildren(QGroupBox)
        group_titles = [g.title() for g in error_groups]
        assert any("エラー詳細" in t for t in group_titles)

    def test_error_table_content(self, qtbot, partial_error_result, find_child_widget):
        """エラーテーブルの内容が正しい"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        table = find_child_widget(dialog, QTableWidget, "errorTable")
        assert table.rowCount() == 1
        assert table.item(0, 0).text() == "image_001.png"
        assert table.item(0, 1).text() == "claude-3-haiku"
        assert table.item(0, 2).text() == "Rate limit exceeded"

    def test_integrity_violation_uses_dedicated_table(
        self, qtbot, integrity_violation_result, find_child_widget
    ):
        """integrity_violation は通常エラーとは別テーブルに表示される"""
        dialog = AnnotationSummaryDialog(integrity_violation_result)
        qtbot.addWidget(dialog)

        integrity_table = find_child_widget(dialog, QTableWidget, "integrityViolationTable")
        assert integrity_table.rowCount() == 1
        assert integrity_table.item(0, 0).text() == "image_001.png"
        assert integrity_table.item(0, 1).text() == "unknown-model"
        assert "unexpected model_id" in integrity_table.item(0, 2).text()

        regular_table = find_child_widget(dialog, QTableWidget, "errorTable")
        assert regular_table.rowCount() == 1
        assert regular_table.item(0, 0).text() == "image_002.png"
        assert regular_table.item(0, 1).text() == "gpt-4o-mini"

    def test_only_integrity_violation_hides_regular_error_table(self, qtbot):
        """通常エラーが無い場合は errorTable を作らず専用セクションだけ表示する"""
        result = AnnotationExecutionResult(
            results={},
            total_images=1,
            models_used=["gpt-4o-mini"],
            model_errors=[
                ModelErrorDetail(
                    model_name="unknown-model",
                    image_path="image_001.png",
                    error_message="unexpected model",
                    error_type="integrity_violation",
                )
            ],
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)

        assert dialog.findChild(QTableWidget, "integrityViolationTable") is not None
        assert dialog.findChild(QTableWidget, "errorTable") is None

    def test_summary_shows_image_count(self, qtbot, success_result):
        """概要セクションに画像件数が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert any("5件" in text for text in label_texts)

    def test_summary_shows_model_names(self, qtbot, partial_error_result):
        """概要セクションにモデル名が表示される"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        model_view = dialog.findChild(QTextBrowser, "modelsUsedView")
        assert model_view is not None
        assert "gpt-4o-mini" in model_view.toPlainText()
        assert "claude-3-haiku" in model_view.toPlainText()

    def test_summary_model_names_use_scrollable_view(self, qtbot):
        """多数の長いモデル名でも概要欄を単一行QLabelにしない"""
        long_models = [
            f"openrouter/provider/very-long-model-name-{i:02d}-with-extra-suffix" for i in range(12)
        ]
        result = AnnotationExecutionResult(
            results={},
            total_images=1,
            models_used=long_models,
            db_save_success=0,
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)

        model_view = dialog.findChild(QTextBrowser, "modelsUsedView")
        assert model_view is not None
        assert model_view.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
        assert model_view.maximumHeight() <= 96
        assert long_models[0] in model_view.toPlainText()

    def test_skip_count_shown_when_nonzero(self, qtbot, partial_error_result):
        """スキップ件数が0でない場合に表示される"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert any("1件" in text for text in label_texts)


class TestAnnotationSummaryDialogStatusLabel:
    """ステータスラベルのテスト"""

    def test_success_status(self, qtbot, success_result):
        """成功時のステータステキスト"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert "処理完了" in label_texts

    def test_partial_error_status(self, qtbot, partial_error_result):
        """部分エラー時のステータステキスト"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert "一部エラーあり" in label_texts

    def test_all_error_status(self, qtbot, all_error_result):
        """全失敗時のステータステキスト"""
        dialog = AnnotationSummaryDialog(all_error_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert "処理失敗" in label_texts


class TestAnnotationSummaryDialogResultsTable:
    """保存結果一覧セクションのテスト"""

    def test_results_group_shown_when_has_summaries(self, qtbot, success_result):
        """image_summariesがある場合に保存結果一覧セクションが表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        groups = dialog.findChildren(QGroupBox)
        group_titles = [g.title() for g in groups]
        assert any("保存結果一覧" in t for t in group_titles)

    def test_results_group_hidden_when_no_summaries(self, qtbot, all_error_result):
        """image_summariesが空の場合に保存結果一覧セクションが非表示"""
        dialog = AnnotationSummaryDialog(all_error_result)
        qtbot.addWidget(dialog)

        groups = dialog.findChildren(QGroupBox)
        group_titles = [g.title() for g in groups]
        assert not any("保存結果一覧" in t for t in group_titles)

    def test_results_table_row_count(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルの行数が正しい"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.rowCount() == 3

    def test_results_table_file_names(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルにファイル名が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.item(0, 0).text() == "image_001.png"
        assert results_table.item(1, 0).text() == "image_002.png"
        assert results_table.item(2, 0).text() == "image_003.png"

    def test_results_table_tag_counts(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルにタグ数が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.item(0, 1).text() == "15"
        assert results_table.item(1, 1).text() == "12"
        assert results_table.item(2, 1).text() == "8"

    def test_results_table_caption_status(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルにキャプション有無が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.item(0, 2).text() == "あり"
        assert results_table.item(2, 2).text() == "-"

    def test_results_table_scores(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルにスコアが表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.item(0, 3).text() == "0.85"
        assert results_table.item(1, 3).text() == "-"  # score=None
        assert results_table.item(2, 3).text() == "0.72"

    def test_results_table_has_rating_column(self, qtbot, success_result, find_child_widget):
        """保存結果テーブルにレーティング列が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        results_table = find_child_widget(dialog, QTableWidget, "resultsTable")
        assert results_table.columnCount() == 5
        assert results_table.horizontalHeaderItem(4).text() == "レーティング"
        assert results_table.item(0, 4).text() == "safe (danbooru4, 0.98)"
        assert results_table.item(1, 4).text() == "-"


class TestAnnotationSummaryDialogRatingsTab:
    """レーティングタブのテスト"""

    def test_ratings_table_content(self, qtbot, rating_result, find_child_widget):
        """レーティングタブに詳細が表示される"""
        dialog = AnnotationSummaryDialog(rating_result)
        qtbot.addWidget(dialog)

        table = find_child_widget(dialog, QTableWidget, "ratingsTable")
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "image_001.png"
        assert table.item(0, 1).text() == "wd-tagger"
        assert table.item(0, 2).text() == "safe"
        assert table.item(0, 3).text() == "danbooru4"
        assert table.item(0, 4).text() == "0.9876"
        assert table.item(1, 1).text() == "legacy"
        assert table.item(1, 2).text() == "PG"

    def test_ratings_table_excludes_errored_results(self, qtbot, rating_result, find_child_widget):
        """error result の ratings はレーティングタブに表示しない"""
        rating_result.results["phash1"]["failed-model"] = {
            "ratings": [
                {
                    "raw_label": "questionable",
                    "source_scheme": "danbooru4",
                    "confidence_score": 0.9,
                }
            ],
            "error": "model failed",
        }
        dialog = AnnotationSummaryDialog(rating_result)
        qtbot.addWidget(dialog)

        table = find_child_widget(dialog, QTableWidget, "ratingsTable")
        model_names = [table.item(row, 1).text() for row in range(table.rowCount())]
        assert model_names == ["wd-tagger", "legacy"]

    def test_ratings_placeholder_when_empty(self, qtbot, success_result):
        """レーティングがない場合はプレースホルダーを表示する"""
        success_result.results = {"phash1": {"gpt-4o-mini": {"tags": ["cat"]}}}
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert "レーティングデータがありません。" in label_texts


class TestAnnotationSummaryDialogFooterActions:
    """フッターアクションボタンと通知シグナルのテスト (#1557)。"""

    def test_footer_buttons_and_signals_on_failure(self, qtbot, find_child_widget):
        result = AnnotationExecutionResult(
            results={"phash1": {}},
            total_images=2,
            models_used=["m1"],
            db_save_success=1,
            db_save_skip=0,
            model_errors=[
                ModelErrorDetail(
                    model_name="m1",
                    error_message="failed",
                    image_path="/path/to/fail.jpg",
                )
            ],
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)

        btn_results = find_child_widget(dialog, QPushButton, "buttonOpenResults")
        btn_errors = find_child_widget(dialog, QPushButton, "buttonOpenErrors")
        btn_restage = find_child_widget(dialog, QPushButton, "buttonRestageFailed")

        assert btn_results is not None
        assert btn_errors is not None
        assert btn_restage is not None

        with qtbot.waitSignal(dialog.open_results_requested, timeout=1000):
            btn_results.click()

        dialog2 = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog2)
        btn_errors2 = find_child_widget(dialog2, QPushButton, "buttonOpenErrors")
        with qtbot.waitSignal(dialog2.open_errors_requested, timeout=1000):
            btn_errors2.click()

        dialog3 = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog3)
        btn_restage3 = find_child_widget(dialog3, QPushButton, "buttonRestageFailed")
        captured_paths: list[list[str]] = []
        dialog3.restage_failed_requested.connect(captured_paths.append)
        btn_restage3.click()
        assert captured_paths == [["/path/to/fail.jpg"]]

    def test_action_buttons_navigate_parent_tabs_and_restage(self, qtbot, find_child_widget):
        result = AnnotationExecutionResult(
            results={},
            total_images=2,
            models_used=["m1"],
            db_save_success=0,
            db_save_skip=0,
            model_errors=[
                ModelErrorDetail(model_name="m1", image_path="/path/fail.jpg", error_message="err")
            ],
        )

        parent = QWidget()
        qtbot.addWidget(parent)
        parent.tabWidgetMainMode = MagicMock()
        parent.tabResults = QWidget()
        parent.tabErrors = QWidget()
        parent._restage_failed_annotation_paths = MagicMock()

        dialog = AnnotationSummaryDialog(result, parent=parent)
        qtbot.addWidget(dialog)
        btn_results = find_child_widget(dialog, QPushButton, "buttonOpenResults")
        btn_results.click()
        parent.tabWidgetMainMode.setCurrentWidget.assert_called_with(parent.tabResults)

        dialog2 = AnnotationSummaryDialog(result, parent=parent)
        qtbot.addWidget(dialog2)
        btn_errors = find_child_widget(dialog2, QPushButton, "buttonOpenErrors")
        btn_errors.click()
        parent.tabWidgetMainMode.setCurrentWidget.assert_called_with(parent.tabErrors)

        dialog3 = AnnotationSummaryDialog(result, parent=parent)
        qtbot.addWidget(dialog3)
        btn_restage = find_child_widget(dialog3, QPushButton, "buttonRestageFailed")
        btn_restage.click()
        parent._restage_failed_annotation_paths.assert_called_once_with(["/path/fail.jpg"])

    def test_dry_run_and_excluded_count_display(self, qtbot, find_child_widget):
        result = AnnotationExecutionResult(
            results={},
            total_images=10,
            models_used=["m1"],
            db_save_success=0,
            db_save_skip=0,
            is_dry_run=True,
            excluded_count=3,
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)

        notice = find_child_widget(dialog, QLabel, "dryRunNoticeLabel")
        assert notice is not None
        assert not notice.isHidden()
        assert "ドライラン" in notice.text()

        excluded_label = find_child_widget(dialog, QLabel, "excludedCountLabel")
        assert excluded_label is not None
        assert excluded_label.text() == "3件"

    def test_restage_prefers_raw_image_path_over_basename(self, qtbot, find_child_widget):
        """サマリーダイアログの再ステージングは basename ではなく完全パス/ID を優先する (#1551, Codex P2 #4532613341)。"""
        result = AnnotationExecutionResult(
            results={},
            total_images=1,
            models_used=["m1"],
            model_errors=[
                ModelErrorDetail(
                    model_name="m1",
                    image_path="fail.jpg",
                    error_message="err",
                    raw_image_path="/custom/dir/fail.jpg",
                )
            ],
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)
        btn_restage = find_child_widget(dialog, QPushButton, "buttonRestageFailed")
        captured: list[list[str]] = []
        dialog.restage_failed_requested.connect(captured.append)
        btn_restage.click()
        assert captured == [["/custom/dir/fail.jpg"]]

    def test_restage_includes_db_save_failures_without_model_errors(self, qtbot, find_child_widget):
        """推論成功後のDB保存失敗のみでも failed_save_paths を再ステージング対象に含める (#1557, Codex P2 #4533111309)。"""
        result = AnnotationExecutionResult(
            results={"phash1": {"m1": {"tags": ["tag1"]}}},
            total_images=1,
            models_used=["m1"],
            db_save_success=0,
            db_save_skip=0,
            model_errors=[],
            failed_save_paths=["/custom/dir/db_fail.jpg"],
        )
        dialog = AnnotationSummaryDialog(result)
        qtbot.addWidget(dialog)
        btn_restage = find_child_widget(dialog, QPushButton, "buttonRestageFailed")
        assert btn_restage is not None
        captured: list[list[str]] = []
        dialog.restage_failed_requested.connect(captured.append)
        btn_restage.click()
        assert captured == [["/custom/dir/db_fail.jpg"]]


class TestAnnotationSummaryDialogExecutionControl:
    """ADR 0109: メモリ不足・CPU 実行など実行状況の表示。"""

    @staticmethod
    def _memory_result() -> AnnotationExecutionResult:
        return AnnotationExecutionResult(
            results={"phash1": {"wd-tagger": {"tags": ["cat"]}}},
            total_images=2,
            models_used=["wd-tagger", "deepdanbooru"],
            db_save_success=1,
            model_errors=[
                ModelErrorDetail(
                    model_name="deepdanbooru",
                    image_path="a.png",
                    error_message="空きメモリが回復しなかったため実行を見送りました",
                    error_type="INSUFFICIENT_MEMORY",
                    raw_image_path="/data/a.png",
                    error_code="INSUFFICIENT_MEMORY",
                ),
                ModelErrorDetail(
                    model_name="wd-tagger",
                    image_path="b.png",
                    error_message="推論中にメモリ不足になりました",
                    error_type="result_error",
                    raw_image_path="/data/b.png",
                    error_code="OUT_OF_MEMORY",
                ),
                ModelErrorDetail(
                    model_name="gpt-4o-mini",
                    image_path="b.png",
                    error_message="rate_limited",
                    error_type="result_error",
                ),
            ],
            execution_notes=[
                "wd-tagger: CPU で実行しました",
                "deepdanbooru: 空きメモリが回復しなかったため実行を見送りました",
            ],
        )

    def test_memory_errors_are_counted_and_labeled(self, qtbot, find_child_widget):
        dialog = AnnotationSummaryDialog(self._memory_result())
        qtbot.addWidget(dialog)

        memory_label = find_child_widget(dialog, QLabel, "memoryErrorCountLabel")
        assert memory_label is not None
        assert memory_label.text() == "2モデル"
        table = find_child_widget(dialog, QTableWidget, "errorTable")
        messages = [table.item(row, 2).text() for row in range(table.rowCount())]
        assert messages == [
            "メモリ不足: 空きメモリが回復しなかったため実行を見送りました",
            "メモリ不足: 推論中にメモリ不足になりました",
            "rate_limited",
        ]

    def test_execution_notes_are_shown(self, qtbot, find_child_widget):
        dialog = AnnotationSummaryDialog(self._memory_result())
        qtbot.addWidget(dialog)

        group = find_child_widget(dialog, QGroupBox, "executionNotesGroup")
        assert group is not None
        texts = [label.text() for label in group.findChildren(QLabel)]
        assert texts == [
            "wd-tagger: CPU で実行しました",
            "deepdanbooru: 空きメモリが回復しなかったため実行を見送りました",
        ]

    def test_no_notes_hides_execution_group(self, qtbot, success_result):
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        assert dialog.findChild(QGroupBox, "executionNotesGroup") is None
        assert dialog.findChild(QLabel, "memoryErrorCountLabel") is None

    def test_memory_skip_images_are_restage_candidates(self, qtbot, find_child_widget):
        dialog = AnnotationSummaryDialog(self._memory_result())
        qtbot.addWidget(dialog)
        captured: list[list[str]] = []
        dialog.restage_failed_requested.connect(captured.append)

        find_child_widget(dialog, QPushButton, "buttonRestageFailed").click()

        assert captured[0][:2] == ["/data/a.png", "/data/b.png"]
