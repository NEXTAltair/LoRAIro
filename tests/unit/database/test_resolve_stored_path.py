"""resolve_stored_path のパス解決テスト。

DB内の stored_image_path を実際のファイルパスに正しく解決できることを検証する。
特に、プロジェクトルートのプレフィックスが含まれる場合の二重結合防止を確認する。
"""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_resolve_cache():
    """各テスト前後で resolve_stored_path のモジュールキャッシュをリセットする（Issue #584 / D3）。"""
    import lorairo.database.db_core as db_core

    db_core._resolve_cache.clear()
    db_core._resolve_cache_root = None
    yield
    db_core._resolve_cache.clear()
    db_core._resolve_cache_root = None


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

        expected = (
            mock_project_root
            / "image_dataset"
            / "original_images"
            / "2025"
            / "07"
            / "22"
            / "2_color"
            / "2745.png"
        )
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

        expected = (
            mock_project_root
            / "image_dataset"
            / "original_images"
            / "2026"
            / "03"
            / "17"
            / "10_Alim"
            / "0262_1227.webp"
        )
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

    def test_cache_hit_returns_same_result(self, mock_project_root: Path) -> None:
        """同一 (project_root, stored_path) の2回目はキャッシュから返る（Issue #584 / D3）。"""
        import lorairo.database.db_core as db_core

        stored = "image_dataset/original_images/2025/07/22/2745.png"
        with patch("lorairo.database.db_core.get_current_project_root", return_value=mock_project_root):
            first = db_core.resolve_stored_path(stored)
            # 1回目でキャッシュに登録される
            assert stored in db_core._resolve_cache
            second = db_core.resolve_stored_path(stored)

        assert first == second
        assert (
            second
            == mock_project_root / "image_dataset" / "original_images" / "2025" / "07" / "22" / "2745.png"
        )

    def test_cache_invalidated_on_project_root_change(self, tmp_path: Path) -> None:
        """project root が変わったらキャッシュは破棄され stale パスを返さない（Issue #584 / D3）。"""
        import lorairo.database.db_core as db_core

        root_a = tmp_path / "lorairo_data" / "project_a"
        root_b = tmp_path / "lorairo_data" / "project_b"
        root_a.mkdir(parents=True)
        root_b.mkdir(parents=True)
        stored = "image_dataset/original_images/shared.png"

        with patch("lorairo.database.db_core.get_current_project_root", return_value=root_a):
            result_a = db_core.resolve_stored_path(stored)
        with patch("lorairo.database.db_core.get_current_project_root", return_value=root_b):
            result_b = db_core.resolve_stored_path(stored)

        assert result_a == root_a / "image_dataset" / "original_images" / "shared.png"
        # 同一 stored_path でも root が変われば新しい root 基準の結果になる（stale-free）
        assert result_b == root_b / "image_dataset" / "original_images" / "shared.png"
        assert result_a != result_b


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
