# tests/unit/storage/test_file_system_manager.py
"""FileSystemManager のユニットテスト

保存先パスがプロジェクトディレクトリ内になることを検証する。
リグレッション防止: initialize_from_dataset_selection が lorairo_output ではなく
プロジェクトルートを使用すること。
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

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


class TestContextManager:
    """__enter__ / __exit__ のテスト"""

    def test_enter_raises_when_not_initialized(self) -> None:
        fsm = FileSystemManager()
        with pytest.raises(RuntimeError, match="初期化されていません"):
            with fsm:
                pass

    def test_enter_returns_self_when_initialized(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        with fsm as f:
            assert f is fsm

    def test_exit_propagates_exception(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        with pytest.raises(ValueError):
            with fsm:
                raise ValueError("test error")


class TestGetResolutionDir:
    """get_resolution_dir のテスト"""

    def test_raises_when_not_initialized(self) -> None:
        fsm = FileSystemManager()
        with pytest.raises(RuntimeError, match="初期化されていません"):
            fsm.get_resolution_dir(512)

    def test_returns_path_under_image_dataset_dir(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        result = fsm.get_resolution_dir(512)
        assert result.is_relative_to(fsm.image_dataset_dir / "512")  # type: ignore[arg-type]

    def test_creates_resolution_directory(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        result = fsm.get_resolution_dir(768)
        assert result.exists()

    def test_different_resolutions_create_different_dirs(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        dir_512 = fsm.get_resolution_dir(512)
        dir_768 = fsm.get_resolution_dir(768)
        assert dir_512 != dir_768


class TestCreateDirectory:
    """_create_directory のテスト"""

    def test_creates_nested_directory(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        new_dir = tmp_path / "a" / "b" / "c"
        fsm._create_directory(new_dir)
        assert new_dir.exists()

    def test_raises_on_permission_error(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        file_as_dir = tmp_path / "file.txt"
        file_as_dir.write_text("content")
        with pytest.raises(Exception):
            fsm._create_directory(file_as_dir / "subdir")


class TestGetImageFiles:
    """get_image_files のテスト"""

    def test_returns_image_files_only(self, tmp_path: Path) -> None:
        (tmp_path / "image1.jpg").write_bytes(b"fake")
        (tmp_path / "image2.png").write_bytes(b"fake")
        (tmp_path / "document.txt").write_bytes(b"fake")

        result = FileSystemManager.get_image_files(tmp_path)
        assert len(result) == 2

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = FileSystemManager.get_image_files(tmp_path)
        assert result == []

    def test_searches_recursively(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "deep.jpg").write_bytes(b"fake")

        result = FileSystemManager.get_image_files(tmp_path)
        assert len(result) == 1

    def test_case_insensitive_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "upper.JPG").write_bytes(b"fake")
        (tmp_path / "lower.png").write_bytes(b"fake")

        result = FileSystemManager.get_image_files(tmp_path)
        assert len(result) == 2

    def test_all_supported_extensions(self, tmp_path: Path) -> None:
        for ext in [".jpg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".jpeg", ".webp"]:
            (tmp_path / f"img{ext}").write_bytes(b"fake")

        result = FileSystemManager.get_image_files(tmp_path)
        assert len(result) == 8


class TestGetImageInfo:
    """get_image_info のテスト"""

    @pytest.fixture
    def rgb_image_path(self, tmp_path: Path) -> Path:
        img = Image.new("RGB", (100, 200), color=(255, 0, 0))
        path = tmp_path / "test.png"
        img.save(path, "PNG")
        return path

    @pytest.fixture
    def rgba_image_path(self, tmp_path: Path) -> Path:
        img = Image.new("RGBA", (50, 50))
        path = tmp_path / "alpha.png"
        img.save(path, "PNG")
        return path

    def test_returns_correct_dimensions(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["width"] == 100
        assert info["height"] == 200

    def test_returns_correct_format(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["format"] == "png"

    def test_returns_mode(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["mode"] == "RGB"

    def test_rgb_image_has_no_alpha(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["has_alpha"] is False

    def test_rgba_image_has_alpha(self, rgba_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgba_image_path)
        assert info["has_alpha"] is True

    def test_returns_filename(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["filename"] == "test.png"

    def test_returns_extension(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["extension"] == ".png"

    def test_no_icc_profile(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert info["icc_profile"] == "Not present"

    def test_raises_on_invalid_file(self, tmp_path: Path) -> None:
        invalid_path = tmp_path / "invalid.png"
        invalid_path.write_bytes(b"not an image data")
        with pytest.raises(Exception):
            FileSystemManager.get_image_info(invalid_path)

    def test_returns_color_space(self, rgb_image_path: Path) -> None:
        info = FileSystemManager.get_image_info(rgb_image_path)
        assert "color_space" in info


class TestScanNextSequenceNumber:
    """_scan_next_sequence_number のテスト"""

    def test_empty_dir_returns_zero(self, tmp_path: Path) -> None:
        result = FileSystemManager._scan_next_sequence_number(tmp_path)
        assert result == 0

    def test_returns_max_plus_one(self, tmp_path: Path) -> None:
        (tmp_path / f"{tmp_path.name}_00000.webp").write_bytes(b"")
        (tmp_path / f"{tmp_path.name}_00003.webp").write_bytes(b"")

        result = FileSystemManager._scan_next_sequence_number(tmp_path)
        assert result == 4

    def test_ignores_non_digit_suffix(self, tmp_path: Path) -> None:
        (tmp_path / f"{tmp_path.name}_abc.webp").write_bytes(b"")
        result = FileSystemManager._scan_next_sequence_number(tmp_path)
        assert result == 0

    def test_ignores_wrong_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "other_prefix_00010.webp").write_bytes(b"")
        result = FileSystemManager._scan_next_sequence_number(tmp_path)
        assert result == 0


class TestGetNextSequenceNumber:
    """_get_next_sequence_number のテスト"""

    def test_returns_zero_for_empty_dir(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        result = fsm._get_next_sequence_number(tmp_path)
        assert result == 0

    def test_increments_on_subsequent_calls(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        first = fsm._get_next_sequence_number(tmp_path)
        second = fsm._get_next_sequence_number(tmp_path)
        assert second == first + 1

    def test_skips_existing_file(self, tmp_path: Path) -> None:
        (tmp_path / f"{tmp_path.name}_00000.webp").write_bytes(b"")
        fsm = FileSystemManager()
        result = fsm._get_next_sequence_number(tmp_path)
        assert result == 1


class TestSaveProcessedImage:
    """save_processed_image のテスト"""

    @pytest.fixture
    def initialized_fsm(self, tmp_path: Path) -> FileSystemManager:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        return fsm

    @pytest.fixture
    def pil_image(self) -> Image.Image:
        return Image.new("RGB", (100, 100), color=(0, 128, 255))

    def test_saves_as_webp(
        self, initialized_fsm: FileSystemManager, pil_image: Image.Image, tmp_path: Path
    ) -> None:
        original_path = tmp_path / "src_dir" / "test.jpg"
        original_path.parent.mkdir()

        result = initialized_fsm.save_processed_image(pil_image, original_path, 512)

        assert result.exists()
        assert result.suffix == ".webp"

    def test_saves_under_resolution_dir(
        self, initialized_fsm: FileSystemManager, pil_image: Image.Image, tmp_path: Path
    ) -> None:
        original_path = tmp_path / "src_dir" / "test.jpg"
        original_path.parent.mkdir()

        result = initialized_fsm.save_processed_image(pil_image, original_path, 512)

        assert "512" in str(result)

    def test_sequential_filenames(
        self, initialized_fsm: FileSystemManager, pil_image: Image.Image, tmp_path: Path
    ) -> None:
        original_path = tmp_path / "src_dir" / "test.jpg"
        original_path.parent.mkdir()

        result1 = initialized_fsm.save_processed_image(pil_image, original_path, 512)
        result2 = initialized_fsm.save_processed_image(pil_image, original_path, 512)

        assert result1 != result2


class TestCopyFile:
    """copy_file のテスト"""

    def test_copies_file_content(self, tmp_path: Path) -> None:
        src = tmp_path / "source.bin"
        dst = tmp_path / "dest.bin"
        src.write_bytes(b"test content 123")

        FileSystemManager.copy_file(src, dst)

        assert dst.exists()
        assert dst.read_bytes() == b"test content 123"

    def test_raises_on_missing_source(self, tmp_path: Path) -> None:
        src = tmp_path / "nonexistent.txt"
        dst = tmp_path / "dest.txt"

        with pytest.raises(FileNotFoundError):
            FileSystemManager.copy_file(src, dst)

    def test_preserves_modification_time(self, tmp_path: Path) -> None:
        src = tmp_path / "source.txt"
        dst = tmp_path / "dest.txt"
        src.write_bytes(b"content")

        FileSystemManager.copy_file(src, dst)

        assert abs(src.stat().st_mtime - dst.stat().st_mtime) < 1.0


class TestSaveOriginalImage:
    """save_original_image のテスト"""

    @pytest.fixture
    def initialized_fsm(self, tmp_path: Path) -> FileSystemManager:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        return fsm

    def test_saves_image_preserving_filename(
        self, initialized_fsm: FileSystemManager, tmp_path: Path
    ) -> None:
        image_file = tmp_path / "source_dir" / "test.jpg"
        image_file.parent.mkdir()
        image_file.write_bytes(b"fake image content")

        result = initialized_fsm.save_original_image(image_file)

        assert result.exists()
        assert result.name == "test.jpg"

    def test_handles_duplicate_filename(self, initialized_fsm: FileSystemManager, tmp_path: Path) -> None:
        image_file = tmp_path / "source_dir" / "test.jpg"
        image_file.parent.mkdir()
        image_file.write_bytes(b"fake image content")

        result1 = initialized_fsm.save_original_image(image_file)
        result2 = initialized_fsm.save_original_image(image_file)

        assert result1.exists()
        assert result2.exists()
        assert result1 != result2

    def test_raises_when_original_images_dir_not_set(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"fake")

        with pytest.raises(RuntimeError, match="original_images_dir is not set"):
            fsm.save_original_image(image_file)

    def test_raises_on_missing_source_file(
        self, initialized_fsm: FileSystemManager, tmp_path: Path
    ) -> None:
        image_file = tmp_path / "source_dir" / "nonexistent.jpg"
        image_file.parent.mkdir()

        with pytest.raises(Exception):
            initialized_fsm.save_original_image(image_file)


class TestCreateBatchRequestFile:
    """create_batch_request_file のテスト"""

    def test_returns_jsonl_path(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        result = fsm.create_batch_request_file()
        assert result.name == "batch_request.jsonl"

    def test_path_is_under_batch_request_dir(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        fsm.initialize(tmp_path)
        result = fsm.create_batch_request_file()
        assert result.parent == fsm.batch_request_dir

    def test_raises_when_not_initialized(self) -> None:
        fsm = FileSystemManager()
        with pytest.raises(RuntimeError, match="batch_request_dir is not set"):
            fsm.create_batch_request_file()


class TestSaveBatchRequest:
    """save_batch_request のテスト"""

    def test_appends_jsonl_line(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        file_path = tmp_path / "batch.jsonl"
        data = {"key": "value", "num": 42}

        fsm.save_batch_request(file_path, data)

        lines = file_path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0]) == data

    def test_appends_multiple_records(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        file_path = tmp_path / "batch.jsonl"

        fsm.save_batch_request(file_path, {"id": 1})
        fsm.save_batch_request(file_path, {"id": 2})

        lines = file_path.read_text().strip().split("\n")
        assert len(lines) == 2


class TestSplitJsonl:
    """split_jsonl のテスト"""

    def test_raises_on_zero_maxsize(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        path = tmp_path / "test.jsonl"
        with pytest.raises(ValueError, match="json_maxsize must be > 0"):
            fsm.split_jsonl(path, 100, 0)

    def test_raises_on_zero_size(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        path = tmp_path / "test.jsonl"
        with pytest.raises(ValueError, match="jsonl_size must be > 0"):
            fsm.split_jsonl(path, 0, 100)

    def test_no_split_when_within_limit(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        path = tmp_path / "test.jsonl"
        path.write_text('{"a":1}\n')

        fsm.split_jsonl(path, 50, 100)

        assert not (tmp_path / "test_split").exists()

    def test_splits_large_file(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        path = tmp_path / "test.jsonl"
        lines = [json.dumps({"id": i}) + "\n" for i in range(10)]
        path.write_text("".join(lines))

        fsm.split_jsonl(path, 200, 50)

        split_dir = tmp_path / "test_split"
        assert split_dir.exists()
        parts = list(split_dir.glob("*.jsonl"))
        assert len(parts) >= 2

    def test_split_files_contain_all_lines(self, tmp_path: Path) -> None:
        fsm = FileSystemManager()
        path = tmp_path / "test.jsonl"
        total_lines = 12
        lines = [json.dumps({"id": i}) + "\n" for i in range(total_lines)]
        path.write_text("".join(lines))

        fsm.split_jsonl(path, 300, 100)

        split_dir = tmp_path / "test_split"
        collected = []
        for f in sorted(split_dir.glob("*.jsonl")):
            collected.extend(f.read_text().strip().split("\n"))
        assert len(collected) == total_lines


class TestExportDatasetToTxt:
    """export_dataset_to_txt のテスト"""

    @pytest.fixture
    def image_data(self, tmp_path: Path) -> dict:
        image_path = tmp_path / "source.jpg"
        image_path.write_bytes(b"fake image")
        return {
            "path": image_path,
            "tags": [{"tag": "tag1"}, {"tag": "tag2"}],
            "captions": [{"caption": "a beautiful scene"}],
        }

    def test_creates_txt_file_with_tags(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_txt(image_data, save_dir)

        txt_file = save_dir / "source.txt"
        assert txt_file.exists()
        assert txt_file.read_text() == "tag1, tag2"

    def test_creates_caption_file(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_txt(image_data, save_dir)

        caption_file = save_dir / "source.caption"
        assert caption_file.exists()
        assert caption_file.read_text() == "a beautiful scene"

    def test_merge_caption_includes_caption_in_txt(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_txt(image_data, save_dir, merge_caption=True)

        content = (save_dir / "source.txt").read_text()
        assert "tag1" in content
        assert "a beautiful scene" in content

    def test_copies_image_to_save_dir(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_txt(image_data, save_dir)

        assert (save_dir / "source.jpg").exists()


class TestExportDatasetToJson:
    """export_dataset_to_json のテスト"""

    @pytest.fixture
    def image_data(self, tmp_path: Path) -> dict:
        image_path = tmp_path / "source.jpg"
        image_path.write_bytes(b"fake image")
        return {
            "path": image_path,
            "tags": [{"tag": "tag1"}, {"tag": "tag2"}],
            "captions": [{"caption": "test caption"}],
        }

    def test_creates_metadata_json(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_json(image_data, save_dir)

        assert (save_dir / "meta_data.json").exists()

    def test_metadata_contains_tags_and_caption(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        FileSystemManager.export_dataset_to_json(image_data, save_dir)

        with open(save_dir / "meta_data.json", encoding="utf-8") as f:
            data = json.load(f)
        values = list(data.values())[0]
        assert "tag1" in values["tags"]
        assert "test caption" in values["caption"]

    def test_appends_to_existing_metadata(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        existing = {"other_image.jpg": {"tags": "old", "caption": "old"}}
        with open(save_dir / "meta_data.json", "w", encoding="utf-8") as f:
            json.dump(existing, f)

        FileSystemManager.export_dataset_to_json(image_data, save_dir)

        with open(save_dir / "meta_data.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "other_image.jpg" in data
        assert len(data) == 2

    def test_handles_corrupted_existing_json(self, tmp_path: Path, image_data: dict) -> None:
        save_dir = tmp_path / "output"
        save_dir.mkdir()

        (save_dir / "meta_data.json").write_text("{ invalid json }")

        FileSystemManager.export_dataset_to_json(image_data, save_dir)

        with open(save_dir / "meta_data.json", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1


class TestSaveTomlConfig:
    """save_toml_config のテスト"""

    def test_saves_config_to_file(self, tmp_path: Path) -> None:
        import toml

        config: dict = {"section": {"key": "value", "number": 42}}
        filename = str(tmp_path / "config.toml")

        FileSystemManager.save_toml_config(config, filename)

        loaded = toml.load(filename)
        assert loaded == config

    def test_raises_os_error_on_invalid_path(self) -> None:
        config: dict = {"key": "value"}
        with pytest.raises(OSError):
            FileSystemManager.save_toml_config(config, "/nonexistent_dir/config.toml")
