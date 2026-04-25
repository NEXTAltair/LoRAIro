"""Export E2E 統合テスト

CLI / Service直接 / GUI の3経路が同一フィルタ条件から同一ファイルセットを
エクスポートすることを検証する。
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.cli.commands.export import _build_filter_criteria
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.dataset_export_service import DatasetExportService
from lorairo.storage.file_system import FileSystemManager


@pytest.mark.integration
class TestExportE2E:
    """GUI/CLI/Service 3経路の出力一致を検証するE2Eテスト"""

    @pytest.fixture
    def temp_project_dir(self):
        """テスト用プロジェクトディレクトリ（cat画像3枚入り）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "test_project_20240101_001"
            project_dir.mkdir()

            # 画像保存ディレクトリを作成
            img_dir = project_dir / "image_dataset" / "512" / "2024" / "01" / "01"
            img_dir.mkdir(parents=True)

            # テスト用ダミー画像ファイルを3件配置
            for i in range(1, 4):
                (img_dir / f"cat_img{i}.webp").write_bytes(b"fake_webp_data")

            yield project_dir

    @pytest.fixture
    def mock_config_service(self, temp_project_dir):
        """設定サービスモック"""
        mock = Mock()
        mock.get_database_directory.return_value = str(temp_project_dir)
        return mock

    @pytest.fixture
    def mock_db_manager(self, temp_project_dir):  # noqa: C901
        """データベースマネージャーモック（画像3件、cat タグ付き）"""
        mock = Mock()

        def get_metadata_side_effect(image_id: int) -> dict | None:
            if image_id in (1, 2, 3):
                return {
                    "id": image_id,
                    "width": 512,
                    "height": 512,
                    "format": "webp",
                    "stored_image_path": f"image_dataset/512/2024/01/01/cat_img{image_id}.webp",
                }
            return None

        def check_processed_side_effect(image_id: int, resolution: int) -> dict | None:
            if image_id in (1, 2, 3) and resolution == 512:
                return {"stored_image_path": f"image_dataset/512/2024/01/01/cat_img{image_id}.webp"}
            return None

        def get_tags_side_effect(image_id: int) -> list:
            if image_id in (1, 2, 3):
                return [{"tag": "cat", "tag_id": 1001, "confidence_score": 0.95}]
            return []

        def get_captions_side_effect(image_id: int) -> list:
            if image_id in (1, 2, 3):
                return [{"caption": "a cute cat", "confidence_score": 0.90}]
            return []

        def get_annotations_side_effect(image_id: int) -> dict:
            return {
                "tags": get_tags_side_effect(image_id),
                "captions": get_captions_side_effect(image_id),
            }

        def get_batch_available_resolutions_side_effect(image_ids: list[int]) -> dict[int, list[int]]:
            result: dict[int, list[int]] = {}
            for image_id in image_ids:
                available = [r for r in [512, 768, 1024, 1536] if check_processed_side_effect(image_id, r)]
                result[image_id] = available
            return result

        def get_images_by_filter_side_effect(criteria: ImageFilterCriteria):
            # tags に "cat" が含まれる場合のみ3件返す
            if criteria.tags and "cat" in criteria.tags:
                images = [
                    {"id": 1, "stored_image_path": "image_dataset/512/2024/01/01/cat_img1.webp"},
                    {"id": 2, "stored_image_path": "image_dataset/512/2024/01/01/cat_img2.webp"},
                    {"id": 3, "stored_image_path": "image_dataset/512/2024/01/01/cat_img3.webp"},
                ]
                return images, len(images)
            return [], 0

        mock.get_image_metadata.side_effect = get_metadata_side_effect
        mock.check_processed_image_exists.side_effect = check_processed_side_effect
        mock.get_tags.side_effect = get_tags_side_effect
        mock.get_captions.side_effect = get_captions_side_effect
        mock.get_image_annotations.side_effect = get_annotations_side_effect
        mock.get_batch_available_resolutions.side_effect = get_batch_available_resolutions_side_effect
        mock.get_images_by_filter.side_effect = get_images_by_filter_side_effect
        return mock

    @pytest.fixture
    def mock_search_processor(self):
        """SearchCriteriaProcessor モック"""
        return Mock()

    @pytest.fixture
    def export_service(self, mock_config_service, mock_db_manager, mock_search_processor, temp_project_dir):
        """DatasetExportService インスタンス（resolve_stored_path をモック済み）"""
        file_system_manager = FileSystemManager()
        with patch("lorairo.services.dataset_export_service.resolve_stored_path") as mock_resolve:

            def resolve_path(stored_path: str) -> Path:
                return temp_project_dir / stored_path

            mock_resolve.side_effect = resolve_path
            service = DatasetExportService(
                config_service=mock_config_service,
                file_system_manager=file_system_manager,
                db_manager=mock_db_manager,
                search_processor=mock_search_processor,
            )
            yield service

    def test_three_paths_produce_same_files(self, export_service, mock_db_manager):
        """CLI/Service直接/GUI の3経路が同一ファイルセットを出力する。"""
        criteria = ImageFilterCriteria(project_name="proj", tags=["cat"])

        with tempfile.TemporaryDirectory() as out_root:
            out1 = Path(out_root) / "path1"
            out2 = Path(out_root) / "path2"
            out3 = Path(out_root) / "path3"
            out1.mkdir()
            out2.mkdir()
            out3.mkdir()

            # Path 1: Service 直接
            export_service.export_with_criteria(
                criteria=criteria,
                output_path=out1,
                format_type="txt",
                resolution=512,
            )

            # Path 2: CLI _build_filter_criteria 経由
            cli_criteria = _build_filter_criteria(
                project_name="proj",
                tags="cat",
                excluded_tags=None,
                caption=None,
                manual_rating=None,
                ai_rating=None,
                include_nsfw=False,
                score_min=None,
                score_max=None,
            )
            export_service.export_with_criteria(
                criteria=cli_criteria,
                output_path=out2,
                format_type="txt",
                resolution=512,
            )

            # Path 3: GUI シミュレーション（事前ID解決 → export_filtered_dataset）
            all_images, _ = mock_db_manager.get_images_by_filter(criteria)
            image_ids = [img["id"] for img in all_images]
            export_service.export_filtered_dataset(
                image_ids=image_ids,
                output_path=out3,
                format_type="txt",
                resolution=512,
            )

            # 3経路の出力ファイル名セットが一致する
            files1 = {f.name for f in out1.iterdir()}
            files2 = {f.name for f in out2.iterdir()}
            files3 = {f.name for f in out3.iterdir()}
            assert files1 == files2 == files3
            assert len(files1) > 0  # 少なくとも何かファイルが出力されている
