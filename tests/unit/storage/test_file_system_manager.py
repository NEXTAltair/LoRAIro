# tests/unit/storage/test_file_system_manager.py
"""FileSystemManager のユニットテスト

保存先パスがプロジェクトディレクトリ内になることを検証する。
リグレッション防止: initialize_from_dataset_selection が lorairo_output ではなく
プロジェクトルートを使用すること。
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from lorairo.storage.file_system import FileSystemManager


class TestInitializeFromDatasetSelection:
    """initialize_from_dataset_selection のテスト"""

    @pytest.fixture
    def fsm(self) -> FileSystemManager:
        return FileSystemManager()

    def test_uses_project_root_not_selected_dir_parent(
        self, fsm: FileSystemManager, tmp_path: Path
    ) -> None:
        """保存先がプロジェクトルートであり、選択ディレクトリの親ではないことを検証

        リグレッション防止: 以前のバグでは selected_dir.parent / "lorairo_output" を
        使用していたため、プロジェクトディレクトリとは無関係な場所に画像が保存されていた。
        """
        project_root = tmp_path / "lorairo_data" / "main_dataset_20250707_001"
        project_root.mkdir(parents=True)

        # 選択ディレクトリはプロジェクトとは全く別の場所
        selected_dir = tmp_path / "user_images" / "my_photos"
        selected_dir.mkdir(parents=True)

        with patch("lorairo.database.db_core.get_current_project_root", return_value=project_root):
            output_dir = fsm.initialize_from_dataset_selection(selected_dir)

        # プロジェクトルートが返される
        assert output_dir == project_root
        # image_dataset がプロジェクトルート内に作成される
        assert fsm.image_dataset_dir == project_root / "image_dataset"
        assert fsm.initialized is True

    def test_output_dir_is_not_lorairo_output(self, fsm: FileSystemManager, tmp_path: Path) -> None:
        """lorairo_output ディレクトリが作成されないことを検証"""
        project_root = tmp_path / "lorairo_data" / "test_project_001"
        project_root.mkdir(parents=True)

        selected_dir = tmp_path / "some_images"
        selected_dir.mkdir(parents=True)

        with patch("lorairo.database.db_core.get_current_project_root", return_value=project_root):
            output_dir = fsm.initialize_from_dataset_selection(selected_dir)

        # lorairo_output が含まれない
        assert "lorairo_output" not in str(output_dir)
        # 選択ディレクトリの親にlorairo_outputが作成されていない
        assert not (selected_dir.parent / "lorairo_output").exists()

    def test_creates_image_dataset_directory_structure(
        self, fsm: FileSystemManager, tmp_path: Path
    ) -> None:
        """プロジェクトルート内に正しいディレクトリ構造が作成される"""
        project_root = tmp_path / "lorairo_data" / "project_001"
        project_root.mkdir(parents=True)

        selected_dir = tmp_path / "input_images"
        selected_dir.mkdir(parents=True)

        with patch("lorairo.database.db_core.get_current_project_root", return_value=project_root):
            fsm.initialize_from_dataset_selection(selected_dir)

        # ディレクトリ構造の検証
        assert (project_root / "image_dataset").exists()
        assert (project_root / "image_dataset" / "original_images").exists()
        assert fsm.original_images_dir is not None
        # original_images_dir はプロジェクトルート配下
        assert str(fsm.original_images_dir).startswith(str(project_root))


class TestInitialize:
    """initialize メソッドのテスト"""

    @pytest.fixture
    def fsm(self) -> FileSystemManager:
        return FileSystemManager()

    def test_creates_directory_structure(self, fsm: FileSystemManager, tmp_path: Path) -> None:
        """initialize が正しいディレクトリ構造を作成する"""
        output_dir = tmp_path / "test_output"

        fsm.initialize(output_dir)

        assert fsm.initialized is True
        assert (output_dir / "image_dataset").exists()
        assert (output_dir / "image_dataset" / "original_images").exists()
        assert (output_dir / "batch_request_jsonl").exists()

    def test_image_dataset_dir_under_output(self, fsm: FileSystemManager, tmp_path: Path) -> None:
        """image_dataset_dir が output_dir 直下に設定される"""
        output_dir = tmp_path / "project_root"

        fsm.initialize(output_dir)

        assert fsm.image_dataset_dir == output_dir / "image_dataset"
