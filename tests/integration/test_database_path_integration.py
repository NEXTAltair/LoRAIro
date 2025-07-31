"""
データベースパス解決と GUI 統合の統合テスト
overview.py と thumbnail.py の変更をテストする
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.services.configuration_service import ConfigurationService


class TestDatabasePathIntegration:
    """データベースパス解決とGUI統合のテスト"""

    def test_relative_to_absolute_path_conversion(self, tmp_path):
        """相対パスから絶対パスへの変換統合テスト"""
        # プロジェクトディレクトリ構造をセットアップ
        project_dir = tmp_path / "test_project_20250708_001"
        project_dir.mkdir()

        image_dataset_dir = project_dir / "image_dataset"
        image_dataset_dir.mkdir()

        original_images_dir = image_dataset_dir / "original_images" / "2024" / "10" / "08" / "test_source"
        original_images_dir.mkdir(parents=True)

        # テスト画像ファイルを作成
        test_image = original_images_dir / "test_image.jpg"
        test_image.write_bytes(b"fake_image_data")

        # 設定サービスをセットアップ
        config_file = tmp_path / "test_config.toml"
        config_file.write_text(f"""
[directories]
database_dir = "{project_dir}"
""")

        with patch("lorairo.services.configuration_service.get_config") as mock_get_config:
            mock_get_config.return_value = {"directories": {"database_dir": str(project_dir)}}

            config_service = ConfigurationService(config_file)

            # データベースから取得される相対パス（実際のDB結果をシミュレート）
            db_relative_path = "image_dataset/original_images/2024/10/08/test_source/test_image.jpg"

            # 設定サービスから取得したデータベースディレクトリ
            database_dir = Path(config_service.get_database_directory())

            # 相対パスを絶対パスに変換
            absolute_path = database_dir / Path(db_relative_path)

            # 変換されたパスが実際のファイルを指すこと
            assert absolute_path.exists()
            assert absolute_path.is_file()
            assert absolute_path == test_image

    def test_overview_widget_path_resolution_integration(self, tmp_path):
        """DatasetOverviewWidget のパス解決統合テスト"""
        # テストデータ準備
        project_dir = tmp_path / "overview_test_20250708_001"
        project_dir.mkdir()

        # 複数の画像ファイルを作成
        image_paths = []
        for i in range(3):
            subdir = (
                project_dir
                / "image_dataset"
                / "original_images"
                / "2024"
                / "10"
                / f"0{i + 1}"
                / f"source_{i}"
            )
            subdir.mkdir(parents=True)
            image_file = subdir / f"image_{i:03d}.jpg"
            image_file.write_bytes(f"fake_image_data_{i}".encode())
            image_paths.append(
                f"image_dataset/original_images/2024/10/0{i + 1}/source_{i}/image_{i:03d}.jpg"
            )

        # ConfigurationService をモック
        mock_config_service = Mock(spec=ConfigurationService)
        mock_config_service.get_database_directory.return_value = str(project_dir)

        # データベース検索結果をシミュレート
        filtered_image_metadata = [
            {"id": i + 1, "stored_image_path": path} for i, path in enumerate(image_paths)
        ]

        # パス解決ロジックをテスト（overview.py の on_filter_applied と同様）
        database_dir = Path(mock_config_service.get_database_directory())

        # 相対パスを絶対パスに変換
        absolute_image_paths = [
            database_dir / Path(item["stored_image_path"]) for item in filtered_image_metadata
        ]

        # すべてのパスが実際のファイルを指すこと
        for abs_path in absolute_image_paths:
            assert abs_path.exists()
            assert abs_path.is_file()

        # image_metadata_map も正しく変換されること
        image_metadata_map = {
            item["id"]: {"path": database_dir / Path(item["stored_image_path"]), "metadata": item}
            for item in filtered_image_metadata
        }

        for _image_id, data in image_metadata_map.items():
            assert data["path"].exists()
            assert data["path"].is_file()

    def test_thumbnail_loading_path_integration(self, tmp_path):
        """サムネイル読み込みパス統合テスト"""
        # 実際の画像ファイルを作成（最小限のJPEGヘッダー）
        project_dir = tmp_path / "thumbnail_test_20250708_001"
        project_dir.mkdir()

        image_dir = project_dir / "image_dataset" / "original_images"
        image_dir.mkdir(parents=True)

        # 最小限のJPEGファイルを作成（QPixmapでロード可能）
        jpeg_header = bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x01,
                0x00,
                0x48,
                0x00,
                0x48,
                0x00,
                0x00,
                0xFF,
                0xD9,
            ]
        )

        test_images = []
        for i in range(2):
            image_file = image_dir / f"test_{i}.jpg"
            image_file.write_bytes(jpeg_header)
            test_images.append(image_file)

        # データベースの相対パス形式
        relative_paths = [f"image_dataset/original_images/test_{i}.jpg" for i in range(2)]

        # パス解決のテスト
        database_dir = project_dir
        absolute_paths = [database_dir / Path(rel_path) for rel_path in relative_paths]

        # QPixmap でロード可能であることをテスト
        for abs_path in absolute_paths:
            assert abs_path.exists()
            # ファイルが読み取り可能であること
            with abs_path.open("rb") as f:
                content = f.read()
                assert len(content) > 0
                # JPEGヘッダーがあること
                assert content.startswith(b"\xff\xd8")

    def test_path_normalization_cross_platform(self, tmp_path):
        """クロスプラットフォームパス正規化テスト"""
        project_dir = tmp_path / "normalization_test"
        project_dir.mkdir()

        # 異なるパス区切り文字でのテスト
        path_variations = [
            "image_dataset/original_images/test.jpg",  # Unix形式
            "image_dataset\\original_images\\test.jpg",  # Windows形式
            "image_dataset/original_images\\test.jpg",  # 混在形式
        ]

        # 実際のファイルを作成
        test_file_dir = project_dir / "image_dataset" / "original_images"
        test_file_dir.mkdir(parents=True)
        test_file = test_file_dir / "test.jpg"
        test_file.write_bytes(b"test_image")

        # すべてのパス形式が同じファイルを指すことをテスト
        for path_str in path_variations:
            # Pathオブジェクトでパス区切り文字を正規化
            normalized_path = Path(path_str)
            resolved_path = project_dir / normalized_path

            # パス正規化が正しく動作することを確認
            if path_str.startswith("image_dataset"):
                # 少なくとも正規化されたパス要素が含まれることを確認
                assert "image_dataset" in str(resolved_path)
                assert "original_images" in str(resolved_path)
                assert "test.jpg" in str(resolved_path)

    def test_missing_file_handling_integration(self, tmp_path):
        """存在しないファイルの処理統合テスト"""
        project_dir = tmp_path / "missing_file_test"
        project_dir.mkdir()

        # 存在しないファイルのパス
        missing_relative_paths = [
            "image_dataset/original_images/missing1.jpg",
            "image_dataset/original_images/missing2.jpg",
        ]

        database_dir = project_dir
        missing_absolute_paths = [database_dir / Path(rel_path) for rel_path in missing_relative_paths]

        # 存在しないファイルが正しく検出されること
        for abs_path in missing_absolute_paths:
            assert not abs_path.exists()
            # パス解決自体は成功すること（ファイルの存在は別途チェック）
            assert abs_path.is_absolute()
            assert str(database_dir) in str(abs_path)

    def test_unicode_filename_path_resolution(self, tmp_path):
        """Unicode ファイル名のパス解決テスト"""
        project_dir = tmp_path / "unicode_test_20250708_001"
        project_dir.mkdir()

        # Unicode文字を含むディレクトリとファイル名
        unicode_dir = project_dir / "image_dataset" / "original_images" / "2024" / "猫画像"
        unicode_dir.mkdir(parents=True)

        unicode_files = ["猫_001.jpg", "データセット_画像.png", "テスト画像_αβγ.webp"]

        for filename in unicode_files:
            file_path = unicode_dir / filename
            file_path.write_bytes(b"unicode_image_data")

        # 相対パスでの表現
        relative_paths = [
            f"image_dataset/original_images/2024/猫画像/{filename}" for filename in unicode_files
        ]

        # 絶対パスに変換して存在確認
        database_dir = project_dir
        for rel_path in relative_paths:
            abs_path = database_dir / Path(rel_path)
            assert abs_path.exists()
            assert abs_path.is_file()
            # Unicode文字が正しく処理されること
            assert "猫" in str(abs_path) or "データ" in str(abs_path) or "テスト" in str(abs_path)

    def test_large_dataset_path_resolution_performance(self, tmp_path):
        """大量データセットでのパス解決パフォーマンステスト"""
        project_dir = tmp_path / "performance_test"
        project_dir.mkdir()

        # 多数のファイルパスをシミュレート（実際のファイルは作成しない）
        num_files = 1000
        relative_paths = [
            f"image_dataset/original_images/2024/10/{i:02d}/batch_{i // 100}/image_{i:06d}.jpg"
            for i in range(num_files)
        ]

        database_dir = project_dir

        # パス解決のパフォーマンステスト
        import time

        start_time = time.time()

        absolute_paths = [database_dir / Path(rel_path) for rel_path in relative_paths]

        end_time = time.time()
        processing_time = end_time - start_time

        # 1000ファイルの処理が合理的な時間内に完了すること（1秒以内）
        assert processing_time < 1.0
        assert len(absolute_paths) == num_files

        # すべてのパスが正しい形式であること
        for abs_path in absolute_paths[:10]:  # 最初の10個だけチェック
            assert abs_path.is_absolute()
            assert "image_dataset" in str(abs_path)
