"""Dataset Export Service 統合テスト

実際のファイルシステム操作とデータベース統合を含む統合テスト
kohya-ss/sd-scripts互換性の確認を含む
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.dataset_export_service import DatasetExportService
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor
from lorairo.storage.file_system import FileSystemManager


class TestDatasetExportIntegration:
    """DatasetExportService 統合テスト"""

    @pytest.fixture
    def temp_project_dir(self):
        """テスト用プロジェクトディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "test_project_20250101_001"
            project_dir.mkdir()

            # プロジェクト構造を作成
            image_dataset = project_dir / "image_dataset"
            image_dataset.mkdir()

            # 解像度ディレクトリを作成
            for resolution in [512, 768, 1024]:
                res_dir = image_dataset / str(resolution) / "2024" / "01" / "01"
                res_dir.mkdir(parents=True)

                # テスト用画像ファイルを作成
                test_image = res_dir / "test_project_00001.webp"
                test_image.write_bytes(b"fake_webp_data")

                test_image2 = res_dir / "test_project_00002.webp"
                test_image2.write_bytes(b"fake_webp_data_2")

            yield project_dir

    @pytest.fixture
    def mock_config_service(self, temp_project_dir):
        """設定サービス（実際のディレクトリ使用）"""
        mock = Mock()
        mock.get_database_directory.return_value = str(temp_project_dir)
        return mock

    @pytest.fixture
    def file_system_manager(self):
        """実際のFileSystemManagerインスタンス"""
        return FileSystemManager()

    @pytest.fixture
    def mock_db_manager(self, temp_project_dir):  # noqa: C901
        """データベースマネージャー（テストデータ付き）"""
        mock = Mock()

        # テスト用画像メタデータ
        def get_metadata_side_effect(image_id):
            if image_id == 1:
                return {
                    "id": 1,
                    "width": 512,
                    "height": 512,
                    "format": "webp",
                    "stored_image_path": "image_dataset/512/2024/01/01/test_project_00001.webp",
                }
            elif image_id == 2:
                return {
                    "id": 2,
                    "width": 768,
                    "height": 768,
                    "format": "webp",
                    "stored_image_path": "image_dataset/768/2024/01/01/test_project_00002.webp",
                }
            return None

        # テスト用処理済み画像チェック
        def check_processed_side_effect(image_id, resolution):
            if image_id == 1 and resolution == 512:
                return {"stored_image_path": "image_dataset/512/2024/01/01/test_project_00001.webp"}
            elif image_id == 2 and resolution == 768:
                return {"stored_image_path": "image_dataset/768/2024/01/01/test_project_00002.webp"}
            return None

        # テスト用タグデータ
        def get_tags_side_effect(image_id):
            if image_id == 1:
                return [
                    {"tag": "anime", "tag_id": 1001, "confidence_score": 0.95},
                    {"tag": "girl", "tag_id": 1002, "confidence_score": 0.90},
                ]
            elif image_id == 2:
                return [
                    {"tag": "landscape", "tag_id": 2001, "confidence_score": 0.88},
                    {"tag": "nature", "tag_id": 2002, "confidence_score": 0.85},
                ]
            return []

        # テスト用キャプションデータ
        def get_captions_side_effect(image_id):
            if image_id == 1:
                return [{"caption": "Anime girl character", "confidence_score": 0.92}]
            elif image_id == 2:
                return [{"caption": "Beautiful natural landscape", "confidence_score": 0.89}]
            return []

        def get_annotations_side_effect(image_id):
            tags = get_tags_side_effect(image_id)
            captions = get_captions_side_effect(image_id)
            return {"tags": tags, "captions": captions}

        mock.get_image_metadata.side_effect = get_metadata_side_effect
        mock.check_processed_image_exists.side_effect = check_processed_side_effect
        mock.get_tags.side_effect = get_tags_side_effect
        mock.get_captions.side_effect = get_captions_side_effect
        mock.get_image_annotations.side_effect = get_annotations_side_effect

        return mock

    @pytest.fixture
    def mock_search_processor(self):
        """検索プロセッサー"""
        mock = Mock()
        return mock

    @pytest.fixture
    def dataset_export_service(
        self,
        mock_config_service,
        file_system_manager,
        mock_db_manager,
        mock_search_processor,
        temp_project_dir,
    ):
        """統合テスト用DatasetExportService"""
        # resolve_stored_pathをモック化してテストディレクトリを参照
        with patch("lorairo.services.dataset_export_service.resolve_stored_path") as mock_resolve:

            def resolve_path(stored_path):
                return temp_project_dir / stored_path

            mock_resolve.side_effect = resolve_path

            service = DatasetExportService(
                config_service=mock_config_service,
                file_system_manager=file_system_manager,
                db_manager=mock_db_manager,
                search_processor=mock_search_processor,
            )
            yield service

    def test_txt_format_export_with_real_files(self, dataset_export_service, temp_project_dir):
        """実ファイルを使用したTXT形式エクスポート統合テスト"""
        with tempfile.TemporaryDirectory() as export_temp:
            export_path = Path(export_temp) / "dataset_export"
            export_path.mkdir()

            # When: TXT形式でエクスポート実行
            result_path = dataset_export_service.export_dataset_txt_format(
                image_ids=[1], output_path=export_path, resolution=512, merge_caption=False
            )

            # Then: 適切なファイルが作成される
            assert result_path == export_path

            # エクスポートされたファイルを確認
            exported_image = export_path / "test_project_00001.webp"
            txt_file = export_path / "test_project_00001.txt"
            caption_file = export_path / "test_project_00001.caption"

            assert exported_image.exists()
            assert txt_file.exists()
            assert caption_file.exists()

            # ファイル内容確認
            with open(txt_file, encoding="utf-8") as f:
                tags_content = f.read()
            assert tags_content == "anime, girl"

            with open(caption_file, encoding="utf-8") as f:
                caption_content = f.read()
            assert caption_content == "Anime girl character"

            # 画像ファイルが正しくコピーされているか確認
            assert exported_image.read_bytes() == b"fake_webp_data"

    def test_json_format_export_with_real_files(self, dataset_export_service, temp_project_dir):
        """実ファイルを使用したJSON形式エクスポート統合テスト"""
        with tempfile.TemporaryDirectory() as export_temp:
            export_path = Path(export_temp) / "dataset_export"
            export_path.mkdir()

            # When: JSON形式でエクスポート実行（複数画像）
            result_path = dataset_export_service.export_dataset_json_format(
                image_ids=[1, 2],
                output_path=export_path,
                resolution=512,  # 画像2は768pxだが、512pxを要求してエラーを確認
            )

            # Then: 適切なファイルが作成される
            assert result_path == export_path

            # メタデータファイルを確認
            metadata_file = export_path / "metadata.json"
            assert metadata_file.exists()

            # JSON内容確認
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)

            # 画像1のみがエクスポートされる（512px存在）
            image1_path = str(export_path / "test_project_00001.webp")
            assert image1_path in metadata
            assert metadata[image1_path]["tags"] == "anime, girl"
            assert metadata[image1_path]["caption"] == "Anime girl character"

            # 画像1がコピーされている確認
            exported_image1 = export_path / "test_project_00001.webp"
            assert exported_image1.exists()

    def test_multiple_images_different_resolutions(self, dataset_export_service, temp_project_dir):
        """異なる解像度の複数画像エクスポートテスト"""
        with tempfile.TemporaryDirectory() as export_temp:
            export_path = Path(export_temp) / "dataset_export"
            export_path.mkdir()

            # Given: 異なる解像度で利用可能な画像
            # 画像1: 512px, 画像2: 768px で各々エクスポート

            # When: 512px解像度で画像1をエクスポート
            dataset_export_service.export_dataset_txt_format(
                image_ids=[1], output_path=export_path, resolution=512
            )

            # Then: 画像1が正常にエクスポートされる
            assert (export_path / "test_project_00001.webp").exists()
            assert (export_path / "test_project_00001.txt").exists()

            # When: 768px解像度で画像2をエクスポート（別ディレクトリ）
            export_path_768 = Path(export_temp) / "dataset_export_768"
            export_path_768.mkdir()

            dataset_export_service.export_dataset_txt_format(
                image_ids=[2], output_path=export_path_768, resolution=768
            )

            # Then: 画像2が正常にエクスポートされる
            assert (export_path_768 / "test_project_00002.webp").exists()
            assert (export_path_768 / "test_project_00002.txt").exists()

            # タグ内容確認
            with open(export_path_768 / "test_project_00002.txt", encoding="utf-8") as f:
                tags_content = f.read()
            assert tags_content == "landscape, nature"

    def test_kohya_ss_compatibility_validation(self, dataset_export_service, temp_project_dir):
        """kohya-ss/sd-scripts互換性検証テスト"""
        with tempfile.TemporaryDirectory() as export_temp:
            export_path = Path(export_temp) / "kohya_compatible_dataset"
            export_path.mkdir()

            # When: kohya-ss互換形式でエクスポート
            dataset_export_service.export_dataset_txt_format(
                image_ids=[1], output_path=export_path, resolution=512, merge_caption=False
            )

            # Then: kohya-ss/sd-scriptsで期待される構造を確認

            # 1. 画像ファイルが存在
            image_file = export_path / "test_project_00001.webp"
            assert image_file.exists()

            # 2. 同名のタグファイルが存在
            tag_file = export_path / "test_project_00001.txt"
            assert tag_file.exists()

            # 3. タグファイルの形式確認（カンマ区切り、改行なし）
            with open(tag_file, encoding="utf-8") as f:
                content = f.read()
            assert not content.endswith("\n")  # 末尾に改行がない
            assert ", " in content  # カンマ+スペース区切り
            assert content == "anime, girl"

            # 4. キャプションファイルが存在（.captionは独立）
            caption_file = export_path / "test_project_00001.caption"
            assert caption_file.exists()

            # 5. JSON形式の確認
            json_export_path = Path(export_temp) / "json_dataset"
            json_export_path.mkdir()

            dataset_export_service.export_dataset_json_format(
                image_ids=[1],
                output_path=json_export_path,
                resolution=512,
                metadata_filename="meta_cap.json",  # kohya-ss標準名
            )

            # JSON構造確認
            json_file = json_export_path / "meta_cap.json"
            assert json_file.exists()

            with open(json_file, encoding="utf-8") as f:
                metadata = json.load(f)

            # kohya-ss期待形式: {画像パス: {tags: "...", caption: "..."}}
            image_path_key = str(json_export_path / "test_project_00001.webp")
            assert image_path_key in metadata
            assert "tags" in metadata[image_path_key]
            assert "caption" in metadata[image_path_key]

    def test_export_validation_report(self, dataset_export_service):
        """エクスポート検証レポートの統合テスト"""
        # When: 複数画像の検証実行
        report = dataset_export_service.validate_export_requirements([1, 2, 999], 512)

        # Then: 詳細な検証レポートが返される
        assert report["total_images"] == 3
        assert report["valid_images"] == 1  # 画像1のみ512pxで利用可能
        assert report["missing_processed"] == 2  # 画像2は768pxのみ、999は存在しない
        assert len(report["issues"]) == 2

        # 具体的な問題が記録されている
        issues = list(report["issues"])
        assert any("Missing processed image for ID 2 at 512px" in issue for issue in issues)
        assert any("Missing processed image for ID 999 at 512px" in issue for issue in issues)

    def test_available_resolutions_detection(self, dataset_export_service):
        """利用可能解像度検出の統合テスト"""
        # When: 利用可能解像度を検出
        resolution_map = dataset_export_service.get_available_resolutions([1, 2])

        # Then: 各画像で利用可能な解像度が正確に検出される
        assert 1 in resolution_map
        assert 2 in resolution_map

        # 画像1は512pxのみ利用可能
        assert 512 in resolution_map[1]
        assert 768 not in resolution_map[1]

        # 画像2は768pxのみ利用可能
        assert 768 in resolution_map[2]
        assert 512 not in resolution_map[2]

    def test_filtered_export_integration(self, dataset_export_service, mock_search_processor):
        """フィルター済み画像IDによるエクスポート統合テスト"""
        with tempfile.TemporaryDirectory() as export_temp:
            export_path = Path(export_temp) / "filtered_export"
            export_path.mkdir()

            # When: 事前にフィルターされた画像IDでエクスポート実行
            result_path = dataset_export_service.export_filtered_dataset(
                image_ids=[1],  # anime, girl タグの画像
                output_path=export_path,
                format_type="txt",
                resolution=512,
            )

            # Then: 指定した画像がエクスポートされる
            assert result_path == export_path
            assert (export_path / "test_project_00001.webp").exists()
            assert (export_path / "test_project_00001.txt").exists()
