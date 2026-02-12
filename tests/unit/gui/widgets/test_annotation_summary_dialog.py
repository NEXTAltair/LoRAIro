"""AnnotationSummaryDialog単体テスト

アノテーション完了サマリーダイアログの表示内容とレイアウトを検証する。
"""

import pytest
from PySide6.QtWidgets import QGroupBox, QLabel, QTableWidget

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
            ImageResultSummary(file_name="image_001.png", tag_count=15, has_caption=True, score=0.85),
            ImageResultSummary(file_name="image_002.png", tag_count=12, has_caption=True, score=None),
            ImageResultSummary(file_name="image_003.png", tag_count=8, has_caption=False, score=0.72),
        ],
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

    def test_error_table_content(self, qtbot, partial_error_result):
        """エラーテーブルの内容が正しい"""
        dialog = AnnotationSummaryDialog(partial_error_result)
        qtbot.addWidget(dialog)

        table = dialog.findChild(QTableWidget)
        assert table is not None
        assert table.rowCount() == 1
        assert table.item(0, 0).text() == "image_001.png"
        assert table.item(0, 1).text() == "claude-3-haiku"
        assert table.item(0, 2).text() == "Rate limit exceeded"

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

        labels = dialog.findChildren(QLabel)
        label_texts = [label.text() for label in labels]
        assert any("gpt-4o-mini" in text and "claude-3-haiku" in text for text in label_texts)

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

    def test_results_table_row_count(self, qtbot, success_result):
        """保存結果テーブルの行数が正しい"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        tables = dialog.findChildren(QTableWidget)
        # 保存結果テーブルは4列（画像名、タグ数、キャプション、スコア）
        results_table = next(t for t in tables if t.columnCount() == 4)
        assert results_table.rowCount() == 3

    def test_results_table_file_names(self, qtbot, success_result):
        """保存結果テーブルにファイル名が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        tables = dialog.findChildren(QTableWidget)
        results_table = next(t for t in tables if t.columnCount() == 4)
        assert results_table.item(0, 0).text() == "image_001.png"
        assert results_table.item(1, 0).text() == "image_002.png"
        assert results_table.item(2, 0).text() == "image_003.png"

    def test_results_table_tag_counts(self, qtbot, success_result):
        """保存結果テーブルにタグ数が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        tables = dialog.findChildren(QTableWidget)
        results_table = next(t for t in tables if t.columnCount() == 4)
        assert results_table.item(0, 1).text() == "15"
        assert results_table.item(1, 1).text() == "12"
        assert results_table.item(2, 1).text() == "8"

    def test_results_table_caption_status(self, qtbot, success_result):
        """保存結果テーブルにキャプション有無が表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        tables = dialog.findChildren(QTableWidget)
        results_table = next(t for t in tables if t.columnCount() == 4)
        assert results_table.item(0, 2).text() == "あり"
        assert results_table.item(2, 2).text() == "-"

    def test_results_table_scores(self, qtbot, success_result):
        """保存結果テーブルにスコアが表示される"""
        dialog = AnnotationSummaryDialog(success_result)
        qtbot.addWidget(dialog)

        tables = dialog.findChildren(QTableWidget)
        results_table = next(t for t in tables if t.columnCount() == 4)
        assert results_table.item(0, 3).text() == "0.85"
        assert results_table.item(1, 3).text() == "-"  # score=None
        assert results_table.item(2, 3).text() == "0.72"
