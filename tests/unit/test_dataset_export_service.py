"""DatasetExportService のユニットテスト

テスト方針:
- 依存関係はモック化し、DatasetExportService単体の振る舞いに焦点
- ファイルシステム操作は一時ディレクトリを使用
- データベース操作は模擬データでテスト
- kohya-ss/sd-scripts互換性を確認
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.services.dataset_export_service import DatasetExportService


class TestDatasetExportService:
    """DatasetExportService のユニットテスト"""

    @pytest.fixture
    def mock_config_service(self):
        """設定サービスのモック"""
        mock = Mock()
        return mock

    @pytest.fixture
    def mock_file_system_manager(self):
        """ファイルシステムマネージャーのモック"""
        mock = Mock()
        # copy_file メソッドのデフォルト実装
        mock.copy_file = Mock()
        return mock

    @pytest.fixture
    def mock_db_manager(self):
        """データベースマネージャーのモック"""
        mock = Mock()
        return mock

    @pytest.fixture
    def mock_search_processor(self):
        """検索プロセッサーのモック"""
        mock = Mock()
        return mock

    @pytest.fixture
    def dataset_export_service(
        self, mock_config_service, mock_file_system_manager, mock_db_manager, mock_search_processor
    ):
        """テスト対象のDatasetExportService"""
        return DatasetExportService(
            config_service=mock_config_service,
            file_system_manager=mock_file_system_manager,
            db_manager=mock_db_manager,
            search_processor=mock_search_processor,
        )

    @pytest.fixture
    def sample_image_data(self):
        """テスト用サンプル画像データ"""
        return {
            "metadata": {
                "id": 1,
                "width": 512,
                "height": 512,
                "format": "webp",
                "stored_image_path": "image_dataset/512/2024/01/01/test_project_00001.webp",
            },
            "tags": [
                {"tag": "anime", "tag_id": 1001, "confidence_score": 0.95},
                {"tag": "girl", "tag_id": 1002, "confidence_score": 0.90},
                {"tag": "school_uniform", "tag_id": 1003, "confidence_score": 0.85},
            ],
            "captions": [
                {"caption": "A young anime girl in school uniform", "confidence_score": 0.92},
                {"caption": "Beautiful anime character artwork", "confidence_score": 0.88},
            ],
        }

    def test_initialization(self, dataset_export_service):
        """DatasetExportService初期化テスト"""
        # Given, When: DatasetExportServiceが初期化される（フィクスチャで実行）

        # Then: 適切に初期化されている
        assert dataset_export_service.config_service is not None
        assert dataset_export_service.file_system_manager is not None
        assert dataset_export_service.db_manager is not None
        assert dataset_export_service.search_processor is not None

    def test_export_dataset_txt_format_success(
        self, dataset_export_service, mock_file_system_manager, sample_image_data
    ):
        """TXT形式エクスポート成功テスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            # Given: 処理済み画像パスとサンプルデータをモック
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            with (
                patch.object(
                    dataset_export_service,
                    "_resolve_processed_image_path",
                    return_value=processed_image_path,
                ),
                patch.object(
                    dataset_export_service, "_get_image_export_data", return_value=sample_image_data
                ),
            ):
                # When: TXT形式でエクスポート実行
                result_path = dataset_export_service.export_dataset_txt_format(
                    image_ids=[1], output_path=output_path, resolution=512, merge_caption=False
                )

                # Then: 適切にファイルが作成される
                assert result_path == output_path

                # ファイル内容を確認
                txt_file = output_path / "test_project_00001.txt"
                caption_file = output_path / "test_project_00001.caption"

                assert txt_file.exists()
                assert caption_file.exists()

                # タグファイルの内容確認
                with open(txt_file, encoding="utf-8") as f:
                    tags_content = f.read()
                assert "anime, girl, school_uniform" == tags_content

                # キャプションファイルの内容確認
                with open(caption_file, encoding="utf-8") as f:
                    caption_content = f.read()
                assert (
                    "A young anime girl in school uniform, Beautiful anime character artwork"
                    == caption_content
                )

                # ファイルコピーが呼び出されたことを確認
                mock_file_system_manager.copy_file.assert_called_once()

    def test_export_dataset_txt_format_with_merged_caption(
        self, dataset_export_service, mock_file_system_manager, sample_image_data
    ):
        """TXT形式エクスポート（キャプション統合）テスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            # Given: 処理済み画像パスとサンプルデータをモック
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            with (
                patch.object(
                    dataset_export_service,
                    "_resolve_processed_image_path",
                    return_value=processed_image_path,
                ),
                patch.object(
                    dataset_export_service, "_get_image_export_data", return_value=sample_image_data
                ),
            ):
                # When: キャプション統合でエクスポート実行
                dataset_export_service.export_dataset_txt_format(
                    image_ids=[1], output_path=output_path, resolution=512, merge_caption=True
                )

                # Then: タグファイルにキャプションも含まれる
                txt_file = output_path / "test_project_00001.txt"
                with open(txt_file, encoding="utf-8") as f:
                    content = f.read()

                expected = "anime, girl, school_uniform, A young anime girl in school uniform, Beautiful anime character artwork"
                assert content == expected

    def test_export_dataset_json_format_success(
        self, dataset_export_service, mock_file_system_manager, sample_image_data
    ):
        """JSON形式エクスポート成功テスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            # Given: 処理済み画像パスとサンプルデータをモック
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            with (
                patch.object(
                    dataset_export_service,
                    "_resolve_processed_image_path",
                    return_value=processed_image_path,
                ),
                patch.object(
                    dataset_export_service, "_get_image_export_data", return_value=sample_image_data
                ),
            ):
                # When: JSON形式でエクスポート実行
                result_path = dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

                # Then: 適切にファイルが作成される
                assert result_path == output_path

                # メタデータファイルの存在確認
                metadata_file = output_path / "metadata.json"
                assert metadata_file.exists()

                # JSON内容を確認
                with open(metadata_file, encoding="utf-8") as f:
                    metadata = json.load(f)

                expected_image_path = str(output_path / "test_project_00001.webp")
                assert expected_image_path in metadata

                image_metadata = metadata[expected_image_path]
                assert image_metadata["tags"] == "anime, girl, school_uniform"
                assert (
                    image_metadata["caption"]
                    == "A young anime girl in school uniform, Beautiful anime character artwork"
                )

    def test_export_dataset_txt_format_empty_image_list(self, dataset_export_service):
        """空の画像リストでのエクスポートエラーテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"

            # When & Then: 空の画像リストでValueError発生
            with pytest.raises(ValueError, match="image_ids list cannot be empty"):
                dataset_export_service.export_dataset_txt_format(image_ids=[], output_path=output_path)

    def test_export_dataset_json_format_empty_image_list(self, dataset_export_service):
        """空の画像リストでのJSON形式エクスポートエラーテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"

            # When & Then: 空の画像リストでValueError発生
            with pytest.raises(ValueError, match="image_ids list cannot be empty"):
                dataset_export_service.export_dataset_json_format(image_ids=[], output_path=output_path)

    def test_export_filtered_dataset_txt_format(
        self, dataset_export_service, mock_search_processor, mock_file_system_manager
    ):
        """フィルター条件でのエクスポートテスト（TXT形式）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            with patch.object(
                dataset_export_service, "export_dataset_txt_format", return_value=output_path
            ) as mock_export:
                # When: 事前にフィルターされた画像IDでエクスポート実行
                image_ids = [1, 2]
                result = dataset_export_service.export_filtered_dataset(
                    image_ids=image_ids,
                    output_path=output_path,
                    format_type="txt",
                    resolution=512,
                )

                # Then: TXT形式エクスポートが呼び出される
                mock_export.assert_called_once_with([1, 2], output_path, 512)
                assert result == output_path

    def test_export_filtered_dataset_invalid_format(self, dataset_export_service, mock_search_processor):
        """無効なフォーマット指定でのエクスポートエラーテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"

            # When & Then: 無効なフォーマット指定でValueError発生
            with pytest.raises(ValueError, match="Unsupported format_type: invalid"):
                dataset_export_service.export_filtered_dataset(
                    image_ids=[1], output_path=output_path, format_type="invalid"
                )

    def test_resolve_processed_image_path_success(self, dataset_export_service, mock_db_manager):
        """処理済み画像パス解決成功テスト"""
        # Given: データベースから処理済み画像メタデータを返す
        processed_metadata = {"stored_image_path": "image_dataset/512/2024/01/01/test_project_00001.webp"}
        mock_db_manager.check_processed_image_exists.return_value = processed_metadata

        with patch("lorairo.services.dataset_export_service.resolve_stored_path") as mock_resolve:
            Path("/resolved/path/test_project_00001.webp")
            resolved_path_mock = Mock()
            resolved_path_mock.exists.return_value = True
            mock_resolve.return_value = resolved_path_mock

            # When: 処理済み画像パスを解決
            result = dataset_export_service._resolve_processed_image_path(1, 512)

            # Then: 適切なパスが返される
            assert result == resolved_path_mock
            mock_db_manager.check_processed_image_exists.assert_called_once_with(1, 512)
            mock_resolve.assert_called_once_with("image_dataset/512/2024/01/01/test_project_00001.webp")

    def test_resolve_processed_image_path_not_found(self, dataset_export_service, mock_db_manager):
        """処理済み画像パス解決失敗テスト"""
        # Given: データベースから処理済み画像が見つからない
        mock_db_manager.check_processed_image_exists.return_value = None

        # When: 処理済み画像パスを解決
        result = dataset_export_service._resolve_processed_image_path(1, 512)

        # Then: Noneが返される
        assert result is None

    def test_get_image_export_data_success(
        self, dataset_export_service, mock_db_manager, sample_image_data
    ):
        """画像エクスポートデータ取得成功テスト"""
        # Given: データベースから画像データを返す
        mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
        mock_db_manager.get_image_annotations.return_value = {
            "tags": sample_image_data["tags"],
            "captions": sample_image_data["captions"],
        }

        # When: 画像エクスポートデータを取得
        result = dataset_export_service._get_image_export_data(1)

        # Then: 適切なデータが返される
        assert result is not None
        assert result["metadata"] == sample_image_data["metadata"]
        assert result["tags"] == sample_image_data["tags"]
        assert result["captions"] == sample_image_data["captions"]

    def test_get_image_export_data_not_found(self, dataset_export_service, mock_db_manager):
        """画像エクスポートデータ取得失敗テスト"""
        # Given: データベースから画像メタデータが見つからない
        mock_db_manager.get_image_metadata.return_value = None

        # When: 画像エクスポートデータを取得
        result = dataset_export_service._get_image_export_data(1)

        # Then: Noneが返される
        assert result is None

    def test_get_available_resolutions(self, dataset_export_service, mock_db_manager):
        """利用可能解像度取得テスト"""

        # Given: データベースから解像度別の存在チェック結果を返す
        def check_exists_side_effect(image_id, resolution):
            if image_id == 1 and resolution in [512, 768]:
                return {"stored_image_path": f"image_dataset/{resolution}/test.webp"}
            return None

        mock_db_manager.check_processed_image_exists.side_effect = check_exists_side_effect

        # When: 利用可能解像度を取得
        result = dataset_export_service.get_available_resolutions([1, 2])

        # Then: 適切な解像度マップが返される
        assert result[1] == [512, 768]
        assert result[2] == []

    def test_validate_export_requirements(self, dataset_export_service, sample_image_data):
        """エクスポート要件検証テスト"""

        # Given: 一部の画像で処理済み画像が存在しない
        def resolve_side_effect(image_id, resolution):
            return Path("/mock/path.webp") if image_id == 1 else None

        def get_data_side_effect(image_id):
            return sample_image_data if image_id == 1 else None

        with (
            patch.object(
                dataset_export_service, "_resolve_processed_image_path", side_effect=resolve_side_effect
            ),
            patch.object(
                dataset_export_service, "_get_image_export_data", side_effect=get_data_side_effect
            ),
        ):
            # When: エクスポート要件を検証
            report = dataset_export_service.validate_export_requirements([1, 2, 3], 512)

            # Then: 適切な検証レポートが返される
            assert report["total_images"] == 3
            assert report["valid_images"] == 1
            assert report["missing_processed"] == 2
            assert len(report["issues"]) == 2
            assert "Missing processed image for ID 2 at 512px" in report["issues"]
            assert "Missing processed image for ID 3 at 512px" in report["issues"]

    def test_export_with_missing_processed_image(self, dataset_export_service, sample_image_data):
        """処理済み画像が見つからない場合のエクスポートテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            # Given: 処理済み画像パスが見つからない
            with (
                patch.object(dataset_export_service, "_resolve_processed_image_path", return_value=None),
                patch.object(
                    dataset_export_service, "_get_image_export_data", return_value=sample_image_data
                ),
            ):
                # When: エクスポート実行
                result_path = dataset_export_service.export_dataset_txt_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

                # Then: エクスポートは完了するが、ファイルは作成されない
                assert result_path == output_path
                assert not (output_path / "test_project_00001.txt").exists()
