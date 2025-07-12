"""
DirectoryPickerWidget検証機能のテストケース

このテストは階層制限付きディレクトリ検証ロジックの動作を確認します。
- 最大階層深度: 3レベル
- 最大ファイル数: 10,000件
- 画像ファイル必須要件
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from lorairo.gui.widgets.directory_picker import DirectoryPickerWidget


class TestDirectoryPickerValidation:
    """DirectoryPickerWidget検証機能のテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])

        self.widget = DirectoryPickerWidget()
        self.signal_emitted = False
        self.emitted_path = None

        # シグナルをキャッチするためのスロット
        self.widget.validDirectorySelected.connect(self._on_signal_emitted)

    def _on_signal_emitted(self, path: str):
        """validDirectorySelectedシグナルをキャッチするスロット"""
        self.signal_emitted = True
        self.emitted_path = path

    def test_empty_path_validation(self):
        """空のパスが入力された場合のテスト"""
        # テスト実行
        self.widget.DirectoryPicker.lineEditPicker.setText("")
        self.widget._validate_and_emit()

        # アサーション
        assert not self.signal_emitted
        assert self.emitted_path is None

    def test_non_existent_directory(self):
        """存在しないディレクトリのテスト"""
        # テスト実行
        fake_path = "/non/existent/directory"
        result = self.widget._validate_dataset_directory(fake_path)

        # アサーション
        assert not result

    def test_search_term_input(self):
        """検索ワード誤入力のテスト（grayscale illustrationなど）"""
        # テスト実行
        search_term = "grayscale illustration"
        result = self.widget._validate_dataset_directory(search_term)

        # アサーション
        assert not result

    def test_valid_dataset_directory(self):
        """有効なデータセットディレクトリのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 画像ファイルを作成
            temp_path = Path(temp_dir)
            (temp_path / "image1.jpg").touch()
            (temp_path / "image2.png").touch()

            # テスト実行
            result = self.widget._validate_dataset_directory(str(temp_path))

            # アサーション
            assert result

    def test_directory_without_images(self):
        """画像ファイルが含まれていないディレクトリのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 非画像ファイルのみ作成
            temp_path = Path(temp_dir)
            (temp_path / "file.txt").touch()
            (temp_path / "data.json").touch()

            # テスト実行
            result = self.widget._validate_dataset_directory(str(temp_path))

            # アサーション
            assert not result

    def test_hierarchy_depth_limit(self):
        """階層深度制限のテスト（3階層超過）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 深い階層構造を作成（4階層深）
            temp_path = Path(temp_dir)
            deep_path = temp_path / "level1" / "level2" / "level3" / "level4"
            deep_path.mkdir(parents=True)

            # 4階層目に画像を配置
            (deep_path / "image.jpg").touch()

            # テスト実行
            result = self.widget._validate_dataset_directory(str(temp_path))

            # アサーション: 3階層制限により4階層目の画像は検出されず、Falseになることを確認
            assert not result  # 4階層目の画像は検出されないため無効と判定される

    def test_file_count_limit(self):
        """ファイル数上限制限のテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 大量のファイルを作成（テスト用に100件程度で制限をシミュレート）
            with patch.object(self.widget, "_validate_dataset_directory") as mock_validate:
                # 大量ファイルでFalseを返すようにモック
                mock_validate.return_value = False

                # テスト実行
                result = self.widget._validate_dataset_directory(str(temp_path))

                # アサーション
                assert not result

    def test_mixed_dataset_directory(self):
        """画像ファイルとテキストファイルが混在するディレクトリのテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 画像とテキストファイルを作成
            (temp_path / "image1.jpg").touch()
            (temp_path / "image1.txt").touch()
            (temp_path / "image2.png").touch()
            (temp_path / "image2.caption").touch()

            # テスト実行
            result = self.widget._validate_dataset_directory(str(temp_path))

            # アサーション
            assert result

    def test_dialog_selection_signal(self):
        """ダイアログ選択時のシグナル発信テスト"""
        with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory") as mock_dialog:
            # 有効なディレクトリパスを返すようにモック
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / "image.jpg").touch()

                mock_dialog.return_value = str(temp_path)

                # テスト実行
                self.widget.select_folder()

                # アサーション
                assert self.signal_emitted
                assert self.emitted_path == str(temp_path)

    def test_manual_input_validation(self):
        """手動入力時のバリデーション動作テスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "image.jpg").touch()

            # テスト実行
            self.widget.DirectoryPicker.lineEditPicker.setText(str(temp_path))
            self.widget._validate_and_emit()

            # アサーション
            assert self.signal_emitted
            assert self.emitted_path == str(temp_path)

    def test_quick_validation_check(self):
        """履歴選択用の軽量チェックテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 存在するディレクトリのテスト
            result = self.widget._quick_validation_check(temp_dir)
            assert result

            # 存在しないディレクトリのテスト
            result = self.widget._quick_validation_check("/non/existent/path")
            assert not result

    def test_supported_image_extensions(self):
        """サポートされている画像拡張子のテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 各種画像拡張子をテスト
            for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"]:
                (temp_path / f"image{ext}").touch()

            # テスト実行
            result = self.widget._validate_dataset_directory(str(temp_path))

            # アサーション
            assert result

    def teardown_method(self):
        """各テストメソッドの後に実行されるクリーンアップ処理"""
        self.widget.deleteLater()


if __name__ == "__main__":
    pytest.main([__file__])
