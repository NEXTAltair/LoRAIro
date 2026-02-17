"""アノテーション完了サマリーダイアログ

アノテーション処理完了後に、処理結果のサマリーをモーダルダイアログで表示する。
成功/失敗件数、保存結果一覧、エラー詳細を5タブ形式で確認できる。
"""

from typing import Any

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
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui.workers.annotation_worker import AnnotationExecutionResult

# テーブルの最大表示行数
_MAX_TABLE_ROWS = 50


class AnnotationSummaryDialog(QDialog):
    """アノテーション完了サマリーダイアログ

    処理結果の概要、保存データ一覧、エラー詳細を5タブ形式で表示するモーダルダイアログ。

    タブ構成:
        1. サマリー: 処理統計と全体概要
        2. タグ: モデル別タグ一覧
        3. キャプション: モデル別キャプション
        4. スコア: モデル別スコア詳細
        5. モデル詳細: モデル統計情報
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

        # QTabWidgetをメインレイアウトに配置
        tabs = QTabWidget()
        tabs.addTab(self._create_summary_tab(), "サマリー")
        tabs.addTab(self._create_tags_tab(), "タグ")
        tabs.addTab(self._create_captions_tab(), "キャプション")
        tabs.addTab(self._create_scores_tab(), "スコア")
        tabs.addTab(self._create_model_details_tab(), "モデル詳細")

        layout.addWidget(tabs)
        layout.addWidget(self._create_button_box())

    def _configure_window(self) -> None:
        """ウィンドウ設定"""
        title = self._determine_title()
        self.setWindowTitle(title)
        self.resize(800, 600)
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

    def _create_summary_tab(self) -> QWidget:
        """サマリータブを作成する。

        Returns:
            サマリータブウィジェット。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(self._create_status_label())
        layout.addWidget(self._create_summary_group())

        if self._result.image_summaries:
            layout.addWidget(self._create_results_group())

        if self._result.model_errors:
            layout.addWidget(self._create_error_group())

        layout.addStretch()
        return widget

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


    @staticmethod
    def _get_result_attr(result: object, key: str, default: object = None) -> Any:  # Any使用: dict/objectの動的アクセス
        """アノテーション結果からキーに対応する値を取得する。

        object型（getattr）とdict型（get）の両方に対応。

        Args:
            result: アノテーション結果（objectまたはdict）。
            key: 取得するキー名。
            default: デフォルト値。

        Returns:
            対応する値。見つからない場合はdefault。
        """
        if isinstance(result, dict):
            return result.get(key, default)
        return getattr(result, key, default)

    def _create_tags_tab(self) -> QWidget:
        """タグタブを作成する。

        Returns:
            タグタブウィジェット。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # タグデータを収集
        tag_rows: list[tuple[str, str, str]] = []
        for phash, model_results in self._result.results.items():
            filename = self._result.phash_to_filename.get(phash, phash[:12] + "...")
            for model_name, result in model_results.items():
                tags = self._get_result_attr(result, "tags", None) or []
                if tags:
                    tags_text = ", ".join(tags)
                    tag_rows.append((filename, model_name, tags_text))

        # テーブル作成
        table = QTableWidget(len(tag_rows), 3)
        table.setHorizontalHeaderLabels(["pHash/ファイル", "モデル名", "タグ"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for row, (filename, model_name, tags_text) in enumerate(tag_rows):
            table.setItem(row, 0, QTableWidgetItem(filename))
            table.setItem(row, 1, QTableWidgetItem(model_name))
            table.setItem(row, 2, QTableWidgetItem(tags_text))

        layout.addWidget(table)

        if not tag_rows:
            layout.addWidget(QLabel("タグデータがありません。"))

        return widget

    def _create_captions_tab(self) -> QWidget:
        """キャプションタブを作成する。

        Returns:
            キャプションタブウィジェット。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)

        caption_html = "<html><body>"
        has_captions = False

        for phash, model_results in self._result.results.items():
            filename = self._result.phash_to_filename.get(phash, phash[:12] + "...")
            for model_name, result in model_results.items():
                captions = self._get_result_attr(result, "captions", None)

                if captions:
                    has_captions = True
                    caption_html += f"<h3>{filename} - {model_name}</h3>"
                    if isinstance(captions, list):
                        for caption in captions:
                            caption_html += f"<p>{caption}</p>"
                    else:
                        caption_html += f"<p>{captions}</p>"

        caption_html += "</body></html>"

        if has_captions:
            browser.setHtml(caption_html)
        else:
            browser.setPlainText("キャプションデータがありません。")

        layout.addWidget(browser)
        return widget

    def _create_scores_tab(self) -> QWidget:
        """スコアタブを作成する。

        Returns:
            スコアタブウィジェット。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # スコアデータを収集
        score_rows: list[tuple[str, str, str, float]] = []
        for phash, model_results in self._result.results.items():
            filename = self._result.phash_to_filename.get(phash, phash[:12] + "...")
            for model_name, result in model_results.items():
                scores = self._get_result_attr(result, "scores", None)

                if scores and isinstance(scores, dict):
                    for score_name, score_value in scores.items():
                        if isinstance(score_value, (int, float)):
                            score_rows.append((filename, model_name, score_name, float(score_value)))

        # テーブル作成
        table = QTableWidget(len(score_rows), 4)
        table.setHorizontalHeaderLabels(["pHash/ファイル", "モデル名", "スコア名", "値"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for row, (filename, model_name, score_name, score_value) in enumerate(score_rows):
            table.setItem(row, 0, QTableWidgetItem(filename))
            table.setItem(row, 1, QTableWidgetItem(model_name))
            table.setItem(row, 2, QTableWidgetItem(score_name))
            score_item = QTableWidgetItem(f"{score_value:.4f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, score_item)

        layout.addWidget(table)

        if not score_rows:
            layout.addWidget(QLabel("スコアデータがありません。"))

        return widget

    def _create_model_details_tab(self) -> QWidget:
        """モデル詳細タブを作成する。

        Returns:
            モデル詳細タブウィジェット。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        stats = self._result.model_statistics
        table = QTableWidget(len(stats), 7)
        table.setHorizontalHeaderLabels(
            ["モデル名", "プロバイダー", "成功", "エラー", "タグ数", "キャプション数", "処理時間(秒)"]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        for row, (model_name, stat) in enumerate(stats.items()):
            table.setItem(row, 0, QTableWidgetItem(model_name))
            table.setItem(row, 1, QTableWidgetItem(stat.provider_name or "-"))

            success_item = QTableWidgetItem(str(stat.success_count))
            success_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, success_item)

            error_item = QTableWidgetItem(str(stat.error_count))
            error_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 3, error_item)

            tags_item = QTableWidgetItem(str(stat.total_tags))
            tags_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 4, tags_item)

            captions_item = QTableWidgetItem(str(stat.total_captions))
            captions_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 5, captions_item)

            time_text = (
                f"{stat.processing_time_sec:.2f}" if stat.processing_time_sec is not None else "-"
            )
            time_item = QTableWidgetItem(time_text)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 6, time_item)

        layout.addWidget(table)

        if not stats:
            layout.addWidget(QLabel("モデル統計データがありません。"))

        return widget

    def _create_button_box(self) -> QDialogButtonBox:
        """OKボタンを作成する。

        Returns:
            ダイアログ閉じるボタン。
        """
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        return button_box
