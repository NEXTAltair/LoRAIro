"""アノテーション完了サマリーダイアログ

アノテーション処理完了後に、処理結果のサマリーをモーダルダイアログで表示する。
成功/失敗件数、保存結果一覧、エラー詳細を確認できる。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui.workers.annotation_worker import AnnotationExecutionResult

# テーブルの最大表示行数
_MAX_TABLE_ROWS = 50


class AnnotationSummaryDialog(QDialog):
    """アノテーション完了サマリーダイアログ

    処理結果の概要、保存データ一覧、エラー詳細を表示するモーダルダイアログ。
    """

    def __init__(self, result: AnnotationExecutionResult, parent: QWidget | None = None) -> None:
        """AnnotationSummaryDialog初期化

        Args:
            result: アノテーション実行結果。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._result = result
        self._setup_ui()

    def _setup_ui(self) -> None:
        """UI構築"""
        self._configure_window()
        layout = QVBoxLayout(self)

        layout.addWidget(self._create_status_label())
        layout.addWidget(self._create_summary_group())

        if self._result.image_summaries:
            layout.addWidget(self._create_results_group())

        if self._result.model_errors:
            layout.addWidget(self._create_error_group())

        layout.addWidget(self._create_button_box())

    def _configure_window(self) -> None:
        """ウィンドウ設定"""
        title = self._determine_title()
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setModal(True)

    def _determine_title(self) -> str:
        """ウィンドウタイトルを決定する。

        Returns:
            エラー有無に応じたタイトル文字列。
        """
        if not self._result.model_errors:
            return "アノテーション完了"
        if self._result.db_save_success > 0:
            return "アノテーション完了 (一部エラーあり)"
        return "アノテーション完了 (エラー)"

    def _create_status_label(self) -> QLabel:
        """ステータスラベルを作成する。

        Returns:
            処理完了ステータスを示すラベル。
        """
        if not self._result.model_errors:
            text = "処理完了"
            color = "#4CAF50"
        elif self._result.db_save_success > 0:
            text = "一部エラーあり"
            color = "#FF9800"
        else:
            text = "処理失敗"
            color = "#F44336"

        label = QLabel(text)
        label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; padding: 8px 0;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _create_summary_group(self) -> QGroupBox:
        """概要セクションを作成する。

        Returns:
            処理統計を表示するグループボックス。
        """
        group = QGroupBox("概要")
        form = QFormLayout(group)

        form.addRow("対象画像:", QLabel(f"{self._result.total_images}件"))
        form.addRow("使用モデル:", QLabel(", ".join(self._result.models_used)))
        form.addRow("DB保存成功:", QLabel(f"{self._result.db_save_success}件"))

        if self._result.db_save_skip > 0:
            form.addRow("スキップ:", QLabel(f"{self._result.db_save_skip}件"))

        db_save_fail = len(self._result.results) - self._result.db_save_success - self._result.db_save_skip
        if db_save_fail > 0:
            fail_label = QLabel(f"{db_save_fail}件")
            fail_label.setStyleSheet("color: #F44336; font-weight: bold;")
            form.addRow("DB保存失敗:", fail_label)

        if self._result.model_errors:
            unique_model_errors = len({e.model_name for e in self._result.model_errors})
            error_label = QLabel(f"{unique_model_errors}モデルでエラー発生")
            error_label.setStyleSheet("color: #FF9800;")
            form.addRow("モデルエラー:", error_label)

        return group

    def _create_results_group(self) -> QGroupBox:
        """保存結果一覧セクションを作成する。

        Returns:
            画像ごとの保存結果テーブルを含むグループボックス。
        """
        summaries = self._result.image_summaries
        total = len(summaries)
        display_count = min(total, _MAX_TABLE_ROWS)

        group = QGroupBox(f"保存結果一覧 ({total}件)")
        layout = QVBoxLayout(group)

        table = QTableWidget(display_count, 4)
        table.setHorizontalHeaderLabels(["画像名", "タグ数", "キャプション", "スコア"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setMaximumHeight(200)

        for row, summary in enumerate(summaries[:_MAX_TABLE_ROWS]):
            table.setItem(row, 0, QTableWidgetItem(summary.file_name))

            tag_item = QTableWidgetItem(str(summary.tag_count))
            tag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 1, tag_item)

            caption_item = QTableWidgetItem("あり" if summary.has_caption else "-")
            caption_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, caption_item)

            score_text = f"{summary.score:.2f}" if summary.score is not None else "-"
            score_item = QTableWidgetItem(score_text)
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 3, score_item)

        layout.addWidget(table)

        if total > _MAX_TABLE_ROWS:
            overflow_label = QLabel(f"他 {total - _MAX_TABLE_ROWS}件")
            overflow_label.setStyleSheet("color: #999; font-style: italic;")
            layout.addWidget(overflow_label)

        return group

    def _create_error_group(self) -> QGroupBox:
        """エラー詳細セクションを作成する。

        Returns:
            エラー一覧テーブルを含むグループボックス。
        """
        errors = self._result.model_errors
        total_errors = len(errors)
        display_count = min(total_errors, _MAX_TABLE_ROWS)

        title = f"エラー詳細 ({total_errors}件)"
        group = QGroupBox(title)
        layout = QVBoxLayout(group)

        table = QTableWidget(display_count, 3)
        table.setHorizontalHeaderLabels(["画像", "モデル", "エラー内容"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setMaximumHeight(200)

        for row, error in enumerate(errors[:_MAX_TABLE_ROWS]):
            table.setItem(row, 0, QTableWidgetItem(error.image_path))
            table.setItem(row, 1, QTableWidgetItem(error.model_name))
            table.setItem(row, 2, QTableWidgetItem(error.error_message))

        layout.addWidget(table)

        if total_errors > _MAX_TABLE_ROWS:
            overflow_label = QLabel(f"他 {total_errors - _MAX_TABLE_ROWS}件のエラー")
            overflow_label.setStyleSheet("color: #999; font-style: italic;")
            layout.addWidget(overflow_label)

        return group

    def _create_button_box(self) -> QDialogButtonBox:
        """OKボタンを作成する。

        Returns:
            ダイアログ閉じるボタン。
        """
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        return button_box
