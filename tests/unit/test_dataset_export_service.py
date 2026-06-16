"""DatasetExportService のユニットテスト

テスト方針:
- 依存関係はモック化し、DatasetExportService単体の振る舞いに焦点
- ファイルシステム操作は一時ディレクトリを使用
- データベース操作は模擬データでテスト
- kohya-ss/sd-scripts互換性を確認
"""

import json
import tempfile
from datetime import UTC, datetime
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
        # 既定では外部 tag_db 不在 (変換せず素通し、ADR 0068 graceful degradation)
        mock.annotation_repo.get_merged_reader.return_value = None
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
                assert "A young anime girl in school uniform" == caption_content

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

                expected = "anime, girl, school_uniform, A young anime girl in school uniform"
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
                assert image_metadata["caption"] == "A young anime girl in school uniform"

    def test_export_dataset_txt_format_deduplicates_tags_and_excludes_rejected(
        self, dataset_export_service, mock_file_system_manager
    ):
        """TXT export は rejected を除外し、同じタグ文字列を1回だけ出力する。"""
        image_data = {
            "metadata": {"id": 1},
            "tags": [
                {"tag": "1girl", "model_id": 1, "is_edited_manually": False, "rejected_at": None},
                {"tag": "1girl", "model_id": 2, "is_edited_manually": True, "rejected_at": None},
                {"tag": "blue_hair", "model_id": 1, "rejected_at": datetime(2026, 6, 11, tzinfo=UTC)},
                {"tag": "black_hair", "model_id": 1, "rejected_at": None},
            ],
            "captions": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            with (
                patch.object(
                    dataset_export_service,
                    "_resolve_processed_image_path",
                    return_value=processed_image_path,
                ),
                patch.object(dataset_export_service, "_get_image_export_data", return_value=image_data),
            ):
                dataset_export_service.export_dataset_txt_format([1], output_path)

            with open(output_path / "test_project_00001.txt", encoding="utf-8") as f:
                assert f.read() == "1girl, black_hair"

    def test_export_dataset_txt_format_uses_single_manual_caption(
        self, dataset_export_service, mock_file_system_manager
    ):
        """複数 caption は rejected 除外後、手動編集を優先して1本だけ出力する。"""
        image_data = {
            "metadata": {"id": 1},
            "tags": [],
            "captions": [
                {
                    "caption": "ai caption",
                    "is_edited_manually": False,
                    "updated_at": datetime(2026, 6, 10, tzinfo=UTC),
                    "rejected_at": None,
                },
                {
                    "caption": "manual caption",
                    "is_edited_manually": True,
                    "updated_at": datetime(2026, 6, 9, tzinfo=UTC),
                    "rejected_at": None,
                },
                {
                    "caption": "rejected caption",
                    "is_edited_manually": True,
                    "updated_at": datetime(2026, 6, 11, tzinfo=UTC),
                    "rejected_at": datetime(2026, 6, 11, tzinfo=UTC),
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            with (
                patch.object(
                    dataset_export_service,
                    "_resolve_processed_image_path",
                    return_value=processed_image_path,
                ),
                patch.object(dataset_export_service, "_get_image_export_data", return_value=image_data),
            ):
                dataset_export_service.export_dataset_txt_format([1], output_path)

            with open(output_path / "test_project_00001.caption", encoding="utf-8") as f:
                assert f.read() == "manual caption"

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

    # ─── score_labels Export (Issue #284 / ADR 0028) ───────────────────────

    @pytest.fixture
    def sample_score_labels(self):
        """canonical scorer の score_labels (ADR 0028 の構造化形式)"""
        return [
            {
                "label": "very aesthetic",
                "model": "aesthetic_shadow_v1",
                "model_id": 1,
                "is_edited_manually": False,
            },
            {
                "label": "aesthetic",
                "model": "cafe_aesthetic",
                "model_id": 2,
                "is_edited_manually": False,
            },
        ]

    def test_get_image_export_data_includes_score_labels(
        self, dataset_export_service, mock_db_manager, sample_image_data, sample_score_labels
    ):
        """_get_image_export_data の return に score_labels が含まれる (ADR 0028)。"""
        mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
        mock_db_manager.get_image_annotations.return_value = {
            "tags": sample_image_data["tags"],
            "captions": sample_image_data["captions"],
            "score_labels": sample_score_labels,
        }

        result = dataset_export_service._get_image_export_data(1)

        assert result is not None
        assert "score_labels" in result
        assert result["score_labels"] == sample_score_labels

    def test_get_image_export_data_empty_score_labels(
        self, dataset_export_service, mock_db_manager, sample_image_data
    ):
        """annotations に score_labels key がない場合 (旧データ互換) は空 list を返す。"""
        mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
        mock_db_manager.get_image_annotations.return_value = {
            "tags": sample_image_data["tags"],
            "captions": sample_image_data["captions"],
            # score_labels なし
        }

        result = dataset_export_service._get_image_export_data(1)

        assert result is not None
        assert result["score_labels"] == []

    def test_export_dataset_json_format_includes_score_labels(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
        sample_score_labels,
    ):
        """JSON Export の metadata に score_labels が構造化 list で含まれる (ADR 0028)。

        silent バグ防止: ``db_manager.get_image_annotations`` 経由で score_labels が
        取れる経路まで含めて検証する (Codex 指摘の盲点を mock レベルで塞ぐ)。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            # _get_image_export_data は mock しない (実経路を test)
            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "score_labels": sample_score_labels,
                "ratings": [],
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=processed_image_path,
            ):
                dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

            metadata_file = output_path / "metadata.json"
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
            expected_image_path = str(output_path / "test_project_00001.webp")
            entry = metadata[expected_image_path]

            assert "score_labels" in entry
            assert len(entry["score_labels"]) == 2
            # ADR 0028: model 名と label を常に組で保持
            models = [sl["model"] for sl in entry["score_labels"]]
            labels = [sl["label"] for sl in entry["score_labels"]]
            assert "aesthetic_shadow_v1" in models
            assert "cafe_aesthetic" in models
            assert "very aesthetic" in labels
            assert "aesthetic" in labels

    def test_export_dataset_json_format_empty_score_labels(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
    ):
        """JSON Export で score_labels が空の場合、metadata の値は [] となる。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "score_labels": [],
                "ratings": [],
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=processed_image_path,
            ):
                dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

            metadata_file = output_path / "metadata.json"
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
            expected_image_path = str(output_path / "test_project_00001.webp")
            assert metadata[expected_image_path]["score_labels"] == []

    def test_export_dataset_json_format_silent_drop_regression(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
    ):
        """Regression: get_image_annotations が score_labels key を返却しない場合に
        export が key 欠落で KeyError 等の悪化を起こさず、graceful に [] へ
        fallback することを検証する (PR #286 Codex 指摘の核)。

        将来 ``get_image_annotations`` の戻り値仕様変更時にこの test が早期警告となる。
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            # 旧仕様 (score_labels key 欠落) を mock で再現
            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "ratings": [],
                # score_labels key は意図的に欠落
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=Path("/mock/processed/test_project_00001.webp"),
            ):
                dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

            metadata_file = output_path / "metadata.json"
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
            entry = metadata[str(output_path / "test_project_00001.webp")]
            assert "score_labels" in entry
            assert entry["score_labels"] == []

    def test_get_image_export_data_includes_quality_summary(
        self, dataset_export_service, mock_db_manager, sample_image_data, sample_score_labels
    ):
        """_get_image_export_data の return に quality_summary が含まれる (ADR 0029)。"""
        mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
        mock_db_manager.get_image_annotations.return_value = {
            "tags": sample_image_data["tags"],
            "captions": sample_image_data["captions"],
            "score_labels": sample_score_labels,
            "quality_summary": {
                "mapping_version": "quality-tier-v1",
                "tier": "best quality",
                "is_unanimous": False,
                "known_count": 2,
                "unknown_count": 0,
                "no_score": False,
                "votes": [],
            },
        }

        result = dataset_export_service._get_image_export_data(1)

        assert result is not None
        assert "quality_summary" in result
        assert result["quality_summary"]["tier"] == "best quality"

    def test_export_dataset_json_format_includes_quality_summary(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
        sample_score_labels,
    ):
        """JSON Export の metadata に quality_summary が構造化 dict で含まれる (ADR 0029)。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            quality_summary = {
                "mapping_version": "quality-tier-v1",
                "tier": "masterpiece",
                "is_unanimous": True,
                "known_count": 2,
                "unknown_count": 0,
                "no_score": False,
                "votes": [
                    {
                        "model": "aesthetic_shadow_v1",
                        "source": "score_label",
                        "raw_label": "very aesthetic",
                        "quality_tier": "masterpiece",
                    },
                ],
            }
            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "score_labels": sample_score_labels,
                "ratings": [],
                "quality_summary": quality_summary,
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=processed_image_path,
            ):
                dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

            metadata_file = output_path / "metadata.json"
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
            entry = metadata[str(output_path / "test_project_00001.webp")]

            assert "quality_summary" in entry
            assert entry["quality_summary"]["tier"] == "masterpiece"
            assert entry["quality_summary"]["is_unanimous"] is True
            assert entry["quality_summary"]["mapping_version"] == "quality-tier-v1"

    def test_export_dataset_json_format_missing_quality_summary_fallback(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
    ):
        """get_image_annotations が quality_summary key を欠落しても KeyError しない (graceful fallback)。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()

            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "score_labels": [],
                "ratings": [],
                # quality_summary 欠落 (旧仕様互換)
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=Path("/mock/processed/test_project_00001.webp"),
            ):
                dataset_export_service.export_dataset_json_format(
                    image_ids=[1], output_path=output_path, resolution=512
                )

            metadata_file = output_path / "metadata.json"
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
            entry = metadata[str(output_path / "test_project_00001.webp")]
            assert "quality_summary" in entry
            assert entry["quality_summary"] == {}

    def test_export_dataset_txt_format_excludes_score_labels(
        self,
        dataset_export_service,
        mock_db_manager,
        mock_file_system_manager,
        sample_image_data,
        sample_score_labels,
    ):
        """TXT Export では score_labels が tags / caption ファイルに混入しない (ADR 0028)。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            processed_image_path = Path("/mock/processed/test_project_00001.webp")

            mock_db_manager.get_image_metadata.return_value = sample_image_data["metadata"]
            mock_db_manager.get_image_annotations.return_value = {
                "tags": sample_image_data["tags"],
                "captions": sample_image_data["captions"],
                "scores": [],
                "score_labels": sample_score_labels,
                "ratings": [],
            }
            with patch.object(
                dataset_export_service,
                "_resolve_processed_image_path",
                return_value=processed_image_path,
            ):
                dataset_export_service.export_dataset_txt_format(
                    image_ids=[1], output_path=output_path, resolution=512, merge_caption=False
                )

            txt_file = output_path / "test_project_00001.txt"
            caption_file = output_path / "test_project_00001.caption"
            tags_content = txt_file.read_text(encoding="utf-8")
            caption_content = caption_file.read_text(encoding="utf-8")

            # ADR 0028 / 0027: content tag 専用 file に score_labels 混入禁止
            for label in ["very aesthetic", "aesthetic"]:
                assert label not in tags_content
            for model in ["aesthetic_shadow_v1", "cafe_aesthetic"]:
                assert model not in tags_content
                assert model not in caption_content

    def test_get_available_resolutions(self, dataset_export_service, mock_db_manager):
        """利用可能解像度取得テスト"""

        # Given: バッチ取得メソッドがモックの結果を返す
        mock_db_manager.get_batch_available_resolutions.return_value = {
            1: [512, 768],
            2: [],
        }

        # When: 利用可能解像度を取得
        result = dataset_export_service.get_available_resolutions([1, 2])

        # Then: バッチメソッドが1回だけ呼ばれ、適切な解像度マップが返される
        mock_db_manager.get_batch_available_resolutions.assert_called_once_with([1, 2])
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


class FakeExportReader:
    """convert_tags を実経路で動かす最小 MergedTagReader スタブ (export 用)。"""

    def __init__(self, mapping: dict[str, str], *, types: dict[str, str] | None = None) -> None:
        self._mapping = mapping
        self._types = types or {}
        self.seen_formats: list[str] = []

    def get_format_id(self, format_name: str) -> int:
        self.seen_formats.append(format_name)
        return 1

    def search_tags_bulk(
        self, tags: list[str], format_name: str | None = None, resolve_preferred: bool = True
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for tag in tags:
            key = tag.lower()
            if key in self._mapping:
                result[tag] = {"tag": self._mapping[key], "type_name": self._types.get(key)}
        return result


@pytest.mark.unit
class TestExportTagFormatResolution:
    """ADR 0068 Phase 3: export 時の canonical 解決 + meta 除外のテスト。"""

    @pytest.fixture
    def mock_config_service(self):
        return Mock()

    @pytest.fixture
    def mock_file_system_manager(self):
        mock = Mock()
        mock.copy_file = Mock()
        return mock

    @pytest.fixture
    def mock_search_processor(self):
        return Mock()

    def _make_service(self, reader, mock_file_system_manager, mock_config_service, mock_search_processor):
        db_manager = Mock()
        db_manager.annotation_repo.get_merged_reader.return_value = reader
        return DatasetExportService(
            config_service=mock_config_service,
            file_system_manager=mock_file_system_manager,
            db_manager=db_manager,
            search_processor=mock_search_processor,
        )

    def test_txt_resolves_format_and_excludes_meta(
        self, mock_file_system_manager, mock_config_service, mock_search_processor
    ):
        """TXT export は target format の canonical へ解決し meta タグを除外する。"""
        reader = FakeExportReader(
            {"anime": "anime", "girl": "1girl", "highres": "highres"},
            types={"highres": "meta"},
        )
        service = self._make_service(
            reader, mock_file_system_manager, mock_config_service, mock_search_processor
        )
        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "girl"}, {"tag": "highres"}],
            "captions": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format([1], output_path)

            content = (output_path / "test_project_00001.txt").read_text(encoding="utf-8")
            # girl -> 1girl (canonical)、highres (meta) は除外
            assert content == "anime, 1girl"

    def test_json_resolves_format_and_excludes_meta(
        self, mock_file_system_manager, mock_config_service, mock_search_processor
    ):
        """JSON export も canonical 解決 + meta 除外を行う。"""
        reader = FakeExportReader(
            {"anime": "anime", "girl": "1girl", "highres": "highres"},
            types={"highres": "meta"},
        )
        service = self._make_service(
            reader, mock_file_system_manager, mock_config_service, mock_search_processor
        )
        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "girl"}, {"tag": "highres"}],
            "captions": [],
            "score_labels": [],
            "quality_summary": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_json_format([1], output_path)

            metadata = json.loads((output_path / "metadata.json").read_text(encoding="utf-8"))
            entry = metadata[str(output_path / "test_project_00001.webp")]
            assert entry["tags"] == "anime, 1girl"

    def test_tag_format_argument_is_forwarded(
        self, mock_file_system_manager, mock_config_service, mock_search_processor
    ):
        """tag_format 引数が convert_tags の対象 format として使われること。"""
        reader = FakeExportReader({"anime": "anime"})
        service = self._make_service(
            reader, mock_file_system_manager, mock_config_service, mock_search_processor
        )
        image_data = {"metadata": {"id": 1}, "tags": [{"tag": "anime"}], "captions": []}
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format([1], output_path, tag_format="e621")

            assert "e621" in reader.seen_formats

    def test_no_reader_keeps_formatted_tags(
        self, mock_file_system_manager, mock_config_service, mock_search_processor
    ):
        """外部 tag_db 不在時は整形済みタグをそのまま出力する (graceful degradation)。"""
        service = self._make_service(
            None, mock_file_system_manager, mock_config_service, mock_search_processor
        )
        image_data = {
            "metadata": {"id": 1},
            "tags": [{"tag": "anime"}, {"tag": "girl"}],
            "captions": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "export"
            output_path.mkdir()
            with (
                patch.object(
                    service,
                    "_resolve_processed_image_path",
                    return_value=Path("/mock/processed/test_project_00001.webp"),
                ),
                patch.object(service, "_get_image_export_data", return_value=image_data),
            ):
                service.export_dataset_txt_format([1], output_path)

            content = (output_path / "test_project_00001.txt").read_text(encoding="utf-8")
            assert content == "anime, girl"


@pytest.mark.unit
class TestExportWithCriteria:
    """DatasetExportService.export_with_criteria() のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        return Mock()

    @pytest.fixture
    def dataset_export_service(self, mock_db_manager):
        return DatasetExportService(
            config_service=Mock(),
            file_system_manager=Mock(),
            db_manager=mock_db_manager,
            search_processor=Mock(),
        )

    def test_criteria_path_calls_db_filter(self, dataset_export_service, mock_db_manager, tmp_path):
        """criteria 指定時に db_manager.get_images_by_filter が呼ばれ export_filtered_dataset に委譲される"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        mock_db_manager.get_images_by_filter.return_value = ([{"id": 1}, {"id": 2}], 2)

        with patch.object(
            dataset_export_service, "export_filtered_dataset", return_value=tmp_path
        ) as mock_export:
            criteria = ImageFilterCriteria(tags=["cat"])
            result = dataset_export_service.export_with_criteria(
                output_path=tmp_path,
                criteria=criteria,
            )

        mock_db_manager.get_images_by_filter.assert_called_once_with(criteria)
        mock_export.assert_called_once_with(
            image_ids=[1, 2],
            output_path=tmp_path,
            format_type="txt",
            resolution=512,
        )
        assert result == tmp_path

    def test_image_ids_path_emits_deprecation_warning(self, dataset_export_service, tmp_path):
        """image_ids 指定時に DeprecationWarning が発行される"""
        import warnings

        with patch.object(dataset_export_service, "export_filtered_dataset", return_value=tmp_path):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                dataset_export_service.export_with_criteria(
                    output_path=tmp_path,
                    image_ids=[1, 2, 3],
                )

        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "image_ids" in str(w[0].message).lower() or "deprecated" in str(w[0].message).lower()

    def test_image_ids_path_skips_db_query(self, dataset_export_service, mock_db_manager, tmp_path):
        """image_ids 指定時は DB フィルタクエリを実行しない"""
        import warnings

        with patch.object(dataset_export_service, "export_filtered_dataset", return_value=tmp_path):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                dataset_export_service.export_with_criteria(
                    output_path=tmp_path,
                    image_ids=[1, 2],
                )

        mock_db_manager.get_images_by_filter.assert_not_called()

    def test_no_args_raises_value_error(self, dataset_export_service, tmp_path):
        """criteria も image_ids も指定しない場合 ValueError が発生する"""
        with pytest.raises(ValueError, match="criteria または image_ids"):
            dataset_export_service.export_with_criteria(output_path=tmp_path)

    def test_criteria_empty_result_completes_without_error(
        self, dataset_export_service, mock_db_manager, tmp_path
    ):
        """criteria フィルタ結果が 0 件でも例外なく完了する"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        mock_db_manager.get_images_by_filter.return_value = ([], 0)
        criteria = ImageFilterCriteria(tags=["nonexistent_xyz"])

        result = dataset_export_service.export_with_criteria(
            output_path=tmp_path,
            criteria=criteria,
        )

        assert result == tmp_path

    def test_json_format_delegates_to_json_method(self, dataset_export_service, mock_db_manager, tmp_path):
        """format_type='json' のとき export_dataset_json_format が呼ばれる"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        mock_db_manager.get_images_by_filter.return_value = ([{"id": 1}], 1)

        with patch.object(
            dataset_export_service, "export_dataset_json_format", return_value=tmp_path
        ) as mock_json:
            criteria = ImageFilterCriteria(tags=["cat"])
            dataset_export_service.export_with_criteria(
                output_path=tmp_path,
                format_type="json",
                criteria=criteria,
            )

        mock_json.assert_called_once()

    def test_both_criteria_and_image_ids_raises_value_error(self, dataset_export_service, tmp_path):
        """criteria と image_ids を同時に指定すると ValueError が発生する"""
        from lorairo.database.filter_criteria import ImageFilterCriteria

        criteria = ImageFilterCriteria(tags=["cat"])
        with pytest.raises(ValueError, match="同時に指定"):
            dataset_export_service.export_with_criteria(
                output_path=tmp_path,
                criteria=criteria,
                image_ids=[1, 2, 3],
            )


# ---------------------------------------------------------------------------
# 追加フィクスチャ・ヘルパー (エラーパステスト用)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config_service() -> MagicMock:
    """ConfigurationService のモック。"""
    return MagicMock()


@pytest.fixture()
def mock_file_system_manager() -> MagicMock:
    """FileSystemManager のモック。"""
    return MagicMock()


@pytest.fixture()
def mock_db_manager() -> MagicMock:
    """ImageDatabaseManager のモック。"""
    mock = MagicMock()
    # 既定では外部 tag_db 不在 (変換せず素通し、ADR 0068 graceful degradation)
    mock.annotation_repo.get_merged_reader.return_value = None
    return mock


@pytest.fixture()
def mock_search_processor() -> MagicMock:
    """SearchCriteriaProcessor のモック。"""
    return MagicMock()


@pytest.fixture()
def service(
    mock_config_service: MagicMock,
    mock_file_system_manager: MagicMock,
    mock_db_manager: MagicMock,
    mock_search_processor: MagicMock,
) -> DatasetExportService:
    """DatasetExportService インスタンスを返す。"""
    return DatasetExportService(
        config_service=mock_config_service,
        file_system_manager=mock_file_system_manager,
        db_manager=mock_db_manager,
        search_processor=mock_search_processor,
    )


def _make_processed_metadata(path: str) -> dict:
    """check_processed_image_exists が返す辞書を生成する。"""
    return {"stored_image_path": path}


def _make_image_annotations(
    tags: list[str] | None = None,
    captions: list[str] | None = None,
) -> dict:
    """get_image_annotations が返す辞書を生成する。"""
    tag_list = [{"tag": t} for t in (tags or ["1girl"])]
    caption_list = [{"caption": c} for c in (captions or [])]
    return {
        "tags": tag_list,
        "captions": caption_list,
        "score_labels": [],
        "quality_summary": {},
    }


# ---------------------------------------------------------------------------
# export_dataset_txt_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportDatasetTxtFormat:
    """export_dataset_txt_format のテスト。"""

    def test_raises_value_error_when_image_ids_empty(
        self, service: DatasetExportService, tmp_path: Path
    ) -> None:
        """image_ids が空リストのとき ValueError を送出する。"""
        with pytest.raises(ValueError, match="image_ids list cannot be empty"):
            service.export_dataset_txt_format([], tmp_path)

    def test_creates_output_directory_when_missing(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """output_path が存在しない場合は自動作成される (line 82)。"""
        output_path = tmp_path / "new_output"
        assert not output_path.exists()
        mock_db_manager.check_processed_image_exists.return_value = None
        result = service.export_dataset_txt_format([1], output_path)
        assert output_path.exists()
        assert result == output_path

    def test_skips_image_when_no_export_data(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """export data が取得できない場合はスキップされる (lines 100-101)。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = None
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            result = service.export_dataset_txt_format([1], tmp_path)
        assert result == tmp_path

    def test_continues_on_per_image_exception(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        mock_file_system_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """個別画像の処理で例外が起きても continue して完了する (lines 134-136)。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = {"id": 1}
        mock_db_manager.get_image_annotations.return_value = _make_image_annotations()
        mock_file_system_manager.copy_file.side_effect = OSError("copy failed")
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            result = service.export_dataset_txt_format([1], tmp_path)
        assert result == tmp_path


# ---------------------------------------------------------------------------
# export_dataset_json_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportDatasetJsonFormat:
    """export_dataset_json_format のテスト。"""

    def test_raises_value_error_when_image_ids_empty(
        self, service: DatasetExportService, tmp_path: Path
    ) -> None:
        """image_ids が空リストのとき ValueError を送出する。"""
        with pytest.raises(ValueError, match="image_ids list cannot be empty"):
            service.export_dataset_json_format([], tmp_path)

    def test_creates_output_directory_when_missing(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """output_path が存在しない場合は自動作成される (line 170)。"""
        output_path = tmp_path / "new_json_output"
        assert not output_path.exists()
        mock_db_manager.check_processed_image_exists.return_value = None
        result = service.export_dataset_json_format([1], output_path)
        assert output_path.exists()
        assert result == output_path

    def test_skips_image_when_no_export_data(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """export data が取得できない場合はスキップされる (lines 192-193)。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = None
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            result = service.export_dataset_json_format([1], tmp_path)
        assert result == tmp_path

    def test_continues_on_per_image_exception(
        self,
        service: DatasetExportService,
        mock_db_manager: MagicMock,
        mock_file_system_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """個別画像の処理で例外が起きても continue して完了する (lines 227-229)。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = {"id": 1}
        mock_db_manager.get_image_annotations.return_value = _make_image_annotations()
        mock_file_system_manager.copy_file.side_effect = OSError("copy failed")
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            result = service.export_dataset_json_format([1], tmp_path)
        assert (tmp_path / "metadata.json").exists()
        assert result == tmp_path


# ---------------------------------------------------------------------------
# _resolve_processed_image_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveProcessedImagePath:
    """_resolve_processed_image_path の境界ケースをテスト。"""

    def test_returns_none_when_no_processed_metadata(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """check_processed_image_exists が None → None を返す。"""
        mock_db_manager.check_processed_image_exists.return_value = None
        result = service._resolve_processed_image_path(1, 512)
        assert result is None

    def test_returns_none_when_stored_path_missing_from_metadata(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """stored_image_path キーなし → None を返す (lines 351-352)。"""
        mock_db_manager.check_processed_image_exists.return_value = {"other_key": "value"}
        result = service._resolve_processed_image_path(1, 512)
        assert result is None

    def test_returns_none_when_resolved_path_does_not_exist(
        self, service: DatasetExportService, mock_db_manager: MagicMock, tmp_path: Path
    ) -> None:
        """resolve_stored_path が存在しないパスを返す → None (lines 356-357)。"""
        nonexistent = tmp_path / "ghost_image.png"
        assert not nonexistent.exists()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(nonexistent)
        )
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=nonexistent,
        ):
            result = service._resolve_processed_image_path(1, 512)
        assert result is None

    def test_returns_none_on_exception(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """check_processed_image_exists が例外 → None を返す (lines 361-363)。"""
        mock_db_manager.check_processed_image_exists.side_effect = RuntimeError("db error")
        result = service._resolve_processed_image_path(1, 512)
        assert result is None


# ---------------------------------------------------------------------------
# _get_image_export_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageExportData:
    """_get_image_export_data のテスト。"""

    def test_returns_none_when_metadata_missing(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """get_image_metadata が None → None を返す。"""
        mock_db_manager.get_image_metadata.return_value = None
        result = service._get_image_export_data(1)
        assert result is None

    def test_returns_none_on_exception(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """get_image_metadata が例外 → None を返す (lines 393-395)。"""
        mock_db_manager.get_image_metadata.side_effect = RuntimeError("db error")
        result = service._get_image_export_data(1)
        assert result is None

    def test_returns_data_dict_on_success(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """正常ケース: metadata + annotations を辞書で返す。"""
        mock_db_manager.get_image_metadata.return_value = {"id": 1, "file_path": "/img.png"}
        mock_db_manager.get_image_annotations.return_value = _make_image_annotations(
            tags=["1girl"], captions=["caption"]
        )
        result = service._get_image_export_data(1)
        assert result is not None
        assert result["tags"] == [{"tag": "1girl"}]
        assert result["captions"] == [{"caption": "caption"}]
        assert "metadata" in result


# ---------------------------------------------------------------------------
# export_filtered_dataset
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportFilteredDataset:
    """export_filtered_dataset のテスト。"""

    def test_returns_output_path_when_no_image_ids(
        self, service: DatasetExportService, tmp_path: Path
    ) -> None:
        """image_ids が空リストのとき output_path をそのまま返す。"""
        result = service.export_filtered_dataset([], tmp_path)
        assert result == tmp_path

    def test_raises_value_error_for_unsupported_format(
        self, service: DatasetExportService, tmp_path: Path
    ) -> None:
        """未対応 format_type で ValueError。"""
        with pytest.raises(ValueError, match="Unsupported format_type"):
            service.export_filtered_dataset([1], tmp_path, format_type="csv")

    def test_delegates_to_txt_format(self, service: DatasetExportService, tmp_path: Path) -> None:
        """format_type='txt' のとき export_dataset_txt_format を呼ぶ。"""
        with patch.object(service, "export_dataset_txt_format", return_value=tmp_path) as mock_txt:
            result = service.export_filtered_dataset([1, 2], tmp_path, format_type="txt")
        mock_txt.assert_called_once()
        assert result == tmp_path

    def test_delegates_to_json_format(self, service: DatasetExportService, tmp_path: Path) -> None:
        """format_type='json' のとき export_dataset_json_format を呼ぶ。"""
        with patch.object(service, "export_dataset_json_format", return_value=tmp_path) as mock_json:
            result = service.export_filtered_dataset([1], tmp_path, format_type="json")
        mock_json.assert_called_once()
        assert result == tmp_path


# ---------------------------------------------------------------------------
# validate_export_requirements
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateExportRequirements:
    """validate_export_requirements のテスト。"""

    def test_missing_processed_image_is_counted(
        self, service: DatasetExportService, mock_db_manager: MagicMock
    ) -> None:
        """処理済み画像なし → missing_processed がカウントされる (lines 438-442)。"""
        mock_db_manager.check_processed_image_exists.return_value = None
        report = service.validate_export_requirements([1, 2], 512)
        assert report["missing_processed"] == 2
        assert report["valid_images"] == 0
        assert len(report["issues"]) == 2

    def test_missing_export_data_is_counted(
        self, service: DatasetExportService, mock_db_manager: MagicMock, tmp_path: Path
    ) -> None:
        """処理済み画像あり・export data なし → missing_metadata がカウントされる (lines 446-449)。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = None
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            report = service.validate_export_requirements([1], 512)
        assert report["missing_metadata"] == 1
        assert report["valid_images"] == 0
        assert len(report["issues"]) == 1

    def test_valid_image_is_counted(
        self, service: DatasetExportService, mock_db_manager: MagicMock, tmp_path: Path
    ) -> None:
        """処理済み画像あり・export data あり → valid_images がカウントされる。"""
        processed_path = tmp_path / "img.png"
        processed_path.touch()
        mock_db_manager.check_processed_image_exists.return_value = _make_processed_metadata(
            str(processed_path)
        )
        mock_db_manager.get_image_metadata.return_value = {"id": 1}
        mock_db_manager.get_image_annotations.return_value = _make_image_annotations()
        with patch(
            "lorairo.services.dataset_export_service.resolve_stored_path",
            return_value=processed_path,
        ):
            report = service.validate_export_requirements([1], 512)
        assert report["valid_images"] == 1
        assert report["missing_processed"] == 0
        assert report["missing_metadata"] == 0
