"""resolve_stored_path のパス解決テスト。

DB内の stored_image_path を実際のファイルパスに正しく解決できることを検証する。
特に、プロジェクトルートのプレフィックスが含まれる場合の二重結合防止を確認する。
"""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_project_root(tmp_path: Path):
    """テスト用のプロジェクトルートを作成する。"""
    project_root = tmp_path / "lorairo_data" / "main_dataset_20250707_001"
    project_root.mkdir(parents=True)
    return project_root


class TestResolveStoredPath:
    """resolve_stored_path のテスト。"""

    def test_absolute_path_returned_as_is(self, mock_project_root: Path) -> None:
        """絶対パスはそのまま返される。"""
        from lorairo.database.db_core import resolve_stored_path

        absolute = mock_project_root / "image_dataset" / "original_images" / "test.png"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            result = resolve_stored_path(str(absolute))

        assert result == absolute

    def test_relative_to_project_root(self, mock_project_root: Path) -> None:
        """プロジェクトルート相対パスが正しく解決される。

        修正スクリプトで正規化済みの旧データ形式。
        """
        from lorairo.database.db_core import resolve_stored_path

        stored = "image_dataset/original_images/2025/07/22/2_color/2745.png"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            result = resolve_stored_path(stored)

        expected = mock_project_root / "image_dataset" / "original_images" / "2025" / "07" / "22" / "2_color" / "2745.png"
        assert result == expected

    def test_cwd_relative_with_project_root_prefix(self, mock_project_root: Path) -> None:
        """プロジェクトルートのプレフィックスを含む相対パスが二重結合されない。

        2026-02-04以降のコードで保存されたデータ形式。
        lorairo_data/main_dataset_20250707_001/image_dataset/... のようなパスが
        project_root/lorairo_data/main_dataset_20250707_001/image_dataset/... にならないことを確認。
        """
        from lorairo.database.db_core import resolve_stored_path

        stored = "lorairo_data/main_dataset_20250707_001/image_dataset/original_images/2026/03/17/10_Alim/0262_1227.webp"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            result = resolve_stored_path(stored)

        expected = mock_project_root / "image_dataset" / "original_images" / "2026" / "03" / "17" / "10_Alim" / "0262_1227.webp"
        assert result == expected

    def test_windows_backslash_paths(self, mock_project_root: Path) -> None:
        """Windowsスタイルのバックスラッシュパスも正しく処理される。"""
        from lorairo.database.db_core import resolve_stored_path

        stored = "lorairo_data\\main_dataset_20250707_001\\image_dataset\\original_images\\test.png"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            result = resolve_stored_path(stored)

        expected = mock_project_root / "image_dataset" / "original_images" / "test.png"
        assert result == expected

    def test_project_dir_name_not_in_subdirectory(self, mock_project_root: Path) -> None:
        """プロジェクトディレクトリ名がサブディレクトリに存在しない通常ケース。"""
        from lorairo.database.db_core import resolve_stored_path

        stored = "image_dataset/512/test_512.png"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            result = resolve_stored_path(stored)

        expected = mock_project_root / "image_dataset" / "512" / "test_512.png"
        assert result == expected


class TestDbDirIsAbsolute:
    """DB_DIR が絶対パスとして解決されていることを確認する。"""

    def test_db_dir_is_absolute(self) -> None:
        """DB_DIR が常に絶対パスである。"""
        from lorairo.database.db_core import DB_DIR

        assert DB_DIR.is_absolute(), f"DB_DIR should be absolute, got: {DB_DIR}"

    def test_img_db_path_is_absolute(self) -> None:
        """IMG_DB_PATH が常に絶対パスである。"""
        from lorairo.database.db_core import IMG_DB_PATH

        assert IMG_DB_PATH.is_absolute(), f"IMG_DB_PATH should be absolute, got: {IMG_DB_PATH}"

    def test_get_current_project_root_is_absolute(self) -> None:
        """get_current_project_root() が常に絶対パスを返す。"""
        from lorairo.database.db_core import get_current_project_root

        result = get_current_project_root()
        assert result.is_absolute(), f"Project root should be absolute, got: {result}"
