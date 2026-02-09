"""QuickTagDialog Unit Tests

クイックタグ追加ダイアログのテストスイート。
空入力、正規化失敗、正常系のシグナル発行を検証。
"""

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from lorairo.gui.widgets.quick_tag_dialog import QuickTagDialog


class TestQuickTagDialogInitialization:
    """初期化テスト"""

    def test_initialization(self, qtbot):
        """ダイアログが正しく初期化される"""
        dialog = QuickTagDialog(image_ids=[1, 2, 3])
        qtbot.addWidget(dialog)

        assert dialog._image_ids == [1, 2, 3]
        assert dialog.windowTitle() == "クイックタグ追加 (3枚)"

    def test_ui_components_present(self, qtbot):
        """UI要素が存在する"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        assert hasattr(dialog, "_tag_input")
        assert hasattr(dialog, "_add_button")
        assert hasattr(dialog, "_cancel_button")


class TestQuickTagDialogAddClicked:
    """追加ボタンクリック時のテスト"""

    def test_empty_input_sets_placeholder(self, qtbot):
        """空入力時にプレースホルダーが設定される"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        dialog._tag_input.setText("")
        dialog._on_add_clicked()

        assert dialog._tag_input.placeholderText() == "タグを入力してください"

    def test_whitespace_only_input_sets_placeholder(self, qtbot):
        """空白のみの入力時にプレースホルダーが設定される"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        dialog._tag_input.setText("   ")
        dialog._on_add_clicked()

        assert dialog._tag_input.placeholderText() == "タグを入力してください"

    def test_normalization_failure_shows_warning(self, qtbot, monkeypatch):
        """タグ正規化失敗時にQMessageBox.warningが表示される"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        # _normalize_tagが空文字を返す（正規化失敗）
        monkeypatch.setattr(QuickTagDialog, "_normalize_tag", staticmethod(lambda tag: ""))

        warning_called = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warning_called.append(args))

        dialog._tag_input.setText("invalid_tag")
        dialog._on_add_clicked()

        assert len(warning_called) == 1
        assert "正規化に失敗" in warning_called[0][2]

    def test_valid_tag_emits_signal(self, qtbot):
        """正常なタグ入力でシグナルが発行される"""
        dialog = QuickTagDialog(image_ids=[1, 2])
        qtbot.addWidget(dialog)

        dialog._tag_input.setText("  LANDSCAPE  ")

        with qtbot.waitSignal(dialog.tag_add_requested, timeout=1000) as blocker:
            dialog._on_add_clicked()

        image_ids, tag = blocker.args
        assert image_ids == [1, 2]
        assert tag == "landscape"


class TestQuickTagDialogNormalization:
    """タグ正規化テスト"""

    def test_normalize_tag_basic(self, qtbot):
        """基本的なタグ正規化"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        result = dialog._normalize_tag("  LANDSCAPE  ")
        assert result == "landscape"

    def test_normalize_tag_empty(self, qtbot):
        """空文字の正規化"""
        dialog = QuickTagDialog(image_ids=[1])
        qtbot.addWidget(dialog)

        result = dialog._normalize_tag("")
        assert result == ""
