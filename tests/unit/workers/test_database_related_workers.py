"""
分割済みデータベース関連ワーカーの改善されたユニットテスト
- 過度なMockを避け、実際のオブジェクトを使用
- 外部依存（ファイルシステム）のみMock化
- API名やインポートパスの問題を検出可能
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.image import ImageRepository
from lorairo.gui.workers.base import CancellationError
from lorairo.gui.workers.registration_worker import (
    DatabaseRegistrationResult,
    DatabaseRegistrationWorker,
)
from lorairo.gui.workers.search_worker import SearchWorker
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.search_models import SearchConditions
from lorairo.filesystem import FileSystemManager


class TestDatabaseRegistrationWorker:
    """DatabaseRegistrationWorker の改善されたユニットテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_image_files(self, temp_dir):
        """モック画像ファイル（実際のファイルを作成）"""
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"test_image_{i}.jpg"
            image_file.write_bytes(b"fake_image_data")
            image_files.append(image_file)
        return image_files

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService（Mockしない）"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository（Mockしない）"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager（Mockしない）"""
        return ImageDatabaseManager(config_service=real_config_service, image_repo=real_repository)

    @pytest.fixture
    def mock_fsm(self, mock_image_files):
        """ファイルシステムのみMock化（外部依存）"""
        mock = Mock(spec=FileSystemManager)
        mock.get_image_files.return_value = mock_image_files
        return mock

    def test_api_method_names_are_correct(self, temp_dir, real_db_manager, mock_fsm):
        """
        APIメソッド名が正しいことをテスト
        - このテストは実際のregister_image → register_image_with_side_effectsエラーを検出できる
        """
        DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        # 実際のDatabaseManagerのメソッドが存在することを確認 (#633: 統一エントリへ移行)
        assert hasattr(real_db_manager, "register_image_with_side_effects")
        assert hasattr(real_db_manager, "get_image_metadata")  # get_image_by_idではない！

        # メソッドが呼び出し可能であることを確認
        assert callable(real_db_manager.register_image_with_side_effects)
        assert callable(real_db_manager.get_image_metadata)

    def test_import_paths_are_correct(self):
        """
        インポートパスが正しいことをテスト
        - このテストは実際の...database.db_coreインポートエラーを検出できる
        """
        # 分割済みworkerがインポート可能であることを確認
        # 依存するモジュールがインポート可能であることを確認
        from lorairo.database.db_core import resolve_stored_path  # インポートエラーを検出
        from lorairo.database.schema import CaptionAnnotationData, TagAnnotationData
        from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker

        # クラスが正しく定義されていることを確認
        assert DatabaseRegistrationWorker is not None
        assert resolve_stored_path is not None

    def test_worker_execution_with_real_objects(self, temp_dir, real_db_manager, mock_fsm):
        """
        実際のオブジェクトを使用したワーカー実行テスト
        - Mock以外の実際の連携をテスト
        """
        # #633: 統一登録エントリ経由になったため register_image_with_side_effects を Mock 化
        from lorairo.database.db_manager import RegistrationOutcome, RegistrationSideEffectResult

        with patch.object(real_db_manager, "register_image_with_side_effects") as mock_register:
            mock_register.return_value = RegistrationSideEffectResult(
                RegistrationOutcome.REGISTERED, 1, {"id": 1, "path": "test"}
            )

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 結果の検証
            assert isinstance(result, DatabaseRegistrationResult)
            assert result.registered_count == 3  # 3つのファイル
            assert result.variant_count == 0
            assert result.skipped_count == 0
            assert result.error_count == 0

            # 統一エントリが各画像で呼ばれたことを確認
            assert mock_register.call_count == 3

    def test_execute_collects_per_file_detail(self, temp_dir, real_db_manager, mock_fsm):
        """登録結果に per-file 詳細 (filename / outcome / image_id) と directory を含む。

        Wireframes v11 Frame 1「登録完了サマリ」の詳細行・「既存#N を表示」リンク用。
        DUPLICATE は既存 ID、VARIANT / REGISTERED は新規 ID が image_id に入る。
        """
        from lorairo.database.db_manager import RegistrationOutcome, RegistrationSideEffectResult
        from lorairo.gui.workers.registration_worker import RegistrationDetailItem

        # mock_image_files は test_image_0.jpg / _1 / _2 の3件。順に異なる outcome を返す。
        with patch.object(real_db_manager, "register_image_with_side_effects") as mock_register:
            mock_register.side_effect = [
                RegistrationSideEffectResult(RegistrationOutcome.REGISTERED, 10, {"id": 10}),
                RegistrationSideEffectResult(RegistrationOutcome.VARIANT, 11, {"id": 11}),
                RegistrationSideEffectResult(RegistrationOutcome.DUPLICATE, 4412, {"id": 4412}),
            ]

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

        assert result.directory == temp_dir
        assert result.detail == [
            RegistrationDetailItem("test_image_0.jpg", RegistrationOutcome.REGISTERED, 10),
            RegistrationDetailItem("test_image_1.jpg", RegistrationOutcome.VARIANT, 11),
            RegistrationDetailItem("test_image_2.jpg", RegistrationOutcome.DUPLICATE, 4412),
        ]

    def test_associated_files_processing_integration(self, temp_dir, real_db_manager, mock_fsm):
        """
        関連ファイル処理の統合テスト
        - タグファイル・キャプションファイル処理の実際の連携をテスト
        """
        # テスト用ファイル作成
        image_file = temp_dir / "test.jpg"
        tag_file = temp_dir / "test.txt"
        caption_file = temp_dir / "test.caption"

        image_file.write_bytes(b"fake_image")
        tag_file.write_text("tag1, tag2, tag3", encoding="utf-8")
        caption_file.write_text("test caption", encoding="utf-8")

        mock_fsm.get_image_files.return_value = [image_file]

        # DB操作をMock化 (#633: detect_duplicate_image は統一エントリ内で処理されるため除去)
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_tags") as mock_save_tags,
            patch.object(real_db_manager, "save_captions") as mock_save_captions,
        ):
            mock_register.return_value = (1, {"id": 1})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            worker.execute()

            # 関連ファイル処理が呼ばれたことを確認
            mock_save_tags.assert_called_once()
            mock_save_captions.assert_called_once()

            # タグデータの構造確認
            tag_call_args = mock_save_tags.call_args
            assert tag_call_args[0][0] == 1  # image_id
            tag_data = tag_call_args[0][1]  # tags_data
            assert len(tag_data) == 3
            assert tag_data[0]["tag"] == "tag1"

    def test_cancellation_behavior(self, temp_dir, real_db_manager, mock_fsm):
        """キャンセル動作テスト"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        worker.cancel()

        with pytest.raises(CancellationError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_directory_handling(self, temp_dir, real_db_manager):
        """空ディレクトリ処理テスト"""
        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = []

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        result = worker.execute()

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0


class TestSearchWorker:
    """SearchWorker の改善されたユニットテスト"""

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationServiceを使用"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepositoryを使用"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManagerを使用"""
        return ImageDatabaseManager(config_service=real_config_service, image_repo=real_repository)

    @pytest.fixture
    def search_conditions(self):
        """テスト用検索条件"""
        return SearchConditions(
            search_type="tags",
            keywords=["test", "sample"],
            tag_logic="and",
        )

    def test_search_worker_api_method_names(self, real_db_manager, search_conditions):
        """
        SearchWorkerのAPIメソッド名が正しいことをテスト
        - get_images_by_filterメソッドが存在することを確認
        """
        worker = SearchWorker(real_db_manager, search_conditions)

        # 実際のDB ManagerのAPIが存在することを確認
        assert hasattr(real_db_manager, "get_images_by_filter")
        assert callable(real_db_manager.get_images_by_filter)

        # Workerが正しく初期化されることを確認
        assert worker.db_manager is real_db_manager
        assert worker.search_conditions == search_conditions

    def test_search_with_real_objects(self, real_db_manager, search_conditions):
        """
        実際のオブジェクトを使用した検索テスト
        - データベースアクセスのみMock化
        """
        # DB検索結果をMock化（実際のDBアクセスを避ける）
        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = (
                [
                    {"id": 1, "stored_image_path": "/test/image1.jpg"},
                    {"id": 2, "stored_image_path": "/test/image2.jpg"},
                ],
                2,
            )

            worker = SearchWorker(real_db_manager, search_conditions)
            result = worker.execute()

            # 結果の検証
            assert result.total_count == 2
            assert len(result.image_metadata) == 2
            assert result.filter_conditions == search_conditions
            assert result.search_time > 0

            # 実際のAPIに正しいパラメータが渡されたことを確認（ImageFilterCriteria形式）
            expected_criteria = search_conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

    def test_search_conditions_processing(self, real_db_manager):
        """
        検索条件の処理が正しいことをテスト
        - 日付範囲やonly_untaggedの処理を確認
        """
        from datetime import date

        conditions = SearchConditions(
            search_type="caption",
            keywords=["test caption"],
            tag_logic="and",
            date_filter_enabled=True,
            date_range_start=date(2023, 1, 1),
            date_range_end=date(2023, 12, 31),
            only_untagged=True,
        )

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = ([], 0)

            worker = SearchWorker(real_db_manager, conditions)
            worker.execute()

            # 日付範囲が正しく処理されることを確認（ImageFilterCriteria形式）
            expected_criteria = conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

    def test_search_applies_aspect_ratio_filter(self, real_db_manager):
        """SearchWorker経由でアスペクト比フィルターが適用されることを確認"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            aspect_ratio_filter="正方形 (1:1)",
        )

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = (
                [
                    {"id": 1, "width": 1024, "height": 1024},
                    {"id": 2, "width": 1920, "height": 1080},
                ],
                2,
            )

            worker = SearchWorker(real_db_manager, conditions)
            result = worker.execute()

            # 正方形画像のみ残ることを確認
            assert result.total_count == 1
            assert len(result.image_metadata) == 1
            assert result.image_metadata[0]["id"] == 1
            expected_criteria = conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

    def test_cancellation_behavior(self, real_db_manager, search_conditions):
        """キャンセル動作テスト"""
        worker = SearchWorker(real_db_manager, search_conditions)
        worker.cancel()

        with pytest.raises(CancellationError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_search_result_handling(self, real_db_manager, search_conditions):
        """空の検索結果処理テスト"""
        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = ([], 0)

            worker = SearchWorker(real_db_manager, search_conditions)
            result = worker.execute()

            assert result.total_count == 0
            assert len(result.image_metadata) == 0

    def test_successful_search_does_not_emit_fake_batch_progress(self, real_db_manager, search_conditions):
        """検索成功時に fake search_batch_* の batch_progress を emit しない"""
        image_metadata = [{"id": i, "stored_image_path": f"/test/image{i}.jpg"} for i in range(1, 126)]

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = (image_metadata, len(image_metadata))

            worker = SearchWorker(real_db_manager, search_conditions)
            worker._report_batch_progress = Mock()

            result = worker.execute()

            assert result.total_count == len(image_metadata)
            assert result.image_metadata == image_metadata
            assert result.filter_conditions == search_conditions
            worker._report_batch_progress.assert_not_called()


class TestRegisterSingleImage:
    """_register_single_image() の単体テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def worker_setup(self, temp_dir):
        """worker と mock オブジェクトのセットアップ"""
        mock_db_manager = Mock(spec=ImageDatabaseManager)
        mock_fsm = Mock(spec=FileSystemManager)

        worker = DatabaseRegistrationWorker(temp_dir, mock_db_manager, mock_fsm)

        # ループ内のスロットリング付き進捗報告をモック
        worker._report_batch_progress_throttled = Mock()
        worker._report_progress_throttled = Mock()

        return worker, mock_db_manager, mock_fsm

    @staticmethod
    def _side_effect_result(outcome, image_id=1):
        """RegistrationSideEffectResult を生成するヘルパー (#633)。"""
        from lorairo.database.db_manager import RegistrationSideEffectResult

        metadata = {"id": image_id} if image_id is not None else None
        return RegistrationSideEffectResult(outcome, image_id, metadata)

    def test_register_single_image_new_returns_registered_outcome(self, temp_dir, worker_setup):
        """新規画像 → REGISTERED outcome を返し、統一エントリへ委譲する (#633)。"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.REGISTERED, 1
        )

        outcome, image_id = worker._register_single_image(image_path, 0, 1)

        assert outcome is RegistrationOutcome.REGISTERED
        assert image_id == 1
        mock_db_manager.register_image_with_side_effects.assert_called_once()
        worker._report_batch_progress_throttled.assert_called_once()
        worker._report_progress_throttled.assert_called_once()

    def test_register_single_image_duplicate_returns_duplicate_outcome(self, temp_dir, worker_setup):
        """重複 → DUPLICATE outcome を返す (#633: 統一エントリ内で skip 扱い)。"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.DUPLICATE, 42
        )

        outcome, image_id = worker._register_single_image(image_path, 0, 1)

        assert outcome is RegistrationOutcome.DUPLICATE
        assert image_id == 42

    def test_register_single_image_variant_returns_variant_outcome(self, temp_dir, worker_setup):
        """別版 → VARIANT outcome を返す (#633)。"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.VARIANT, 7
        )

        outcome, image_id = worker._register_single_image(image_path, 0, 1)

        assert outcome is RegistrationOutcome.VARIANT
        assert image_id == 7

    def test_register_single_image_failed_returns_failed_outcome(self, temp_dir, worker_setup):
        """登録失敗 → FAILED outcome、image_id=-1 (#633)。"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.FAILED, None
        )

        outcome, image_id = worker._register_single_image(image_path, 0, 1)

        assert outcome is RegistrationOutcome.FAILED
        assert image_id == -1

    def test_register_single_image_forwards_annotations_and_cache(self, temp_dir, worker_setup):
        """事前読み込み annotations / tag_id_cache を統一エントリへ素通しする (#633)。"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.REGISTERED, 1
        )
        annotations = {"tags": ["t1"], "captions": []}
        tag_id_cache = {"t1": 100}

        worker._register_single_image(image_path, 0, 1, annotations=annotations, tag_id_cache=tag_id_cache)

        call = mock_db_manager.register_image_with_side_effects.call_args
        assert call.kwargs["associated_annotations"] is annotations
        assert call.kwargs["tag_id_cache"] is tag_id_cache

    def test_register_single_image_progress_reporting(self, temp_dir, worker_setup):
        """スロットリング付き進捗報告が呼ばれる"""
        from lorairo.database.db_manager import RegistrationOutcome

        worker, mock_db_manager, _mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.return_value = self._side_effect_result(
            RegistrationOutcome.REGISTERED, 1
        )

        _outcome, _image_id = worker._register_single_image(image_path, 5, 100)

        # バッチ進捗報告の呼び出しを確認
        worker._report_batch_progress_throttled.assert_called_once_with(
            6, 100, image_path.name, force_emit=False
        )

        # 通常進捗報告の呼び出しを確認
        worker._report_progress_throttled.assert_called_once()
        call_args = worker._report_progress_throttled.call_args
        assert call_args[0][0] > 10  # percentage >= 10

    def test_register_single_image_propagates_save_error(self, temp_dir, worker_setup):
        """統一エントリ内の save 例外は呼び出し元へ伝播する (#633)。"""
        worker, mock_db_manager, _mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")
        mock_db_manager.register_image_with_side_effects.side_effect = Exception("Tag save failed")

        with pytest.raises(Exception, match="Tag save failed"):
            worker._register_single_image(image_path, 0, 1)


class TestBuildRegistrationResult:
    """_build_registration_result() の単体テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager"""
        return ImageDatabaseManager(config_service=real_config_service, image_repo=real_repository)

    @pytest.fixture
    def mock_fsm(self):
        """ファイルシステムマネージャーのMock"""
        return Mock(spec=FileSystemManager)

    @pytest.fixture
    def worker(self, temp_dir, real_db_manager, mock_fsm):
        """DatabaseRegistrationWorker インスタンス"""
        return DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

    def test_build_registration_result_normal_case(self, worker):
        """通常ケース: 登録3、スキップ2、エラー1"""
        stats = {"registered": 3, "variant": 0, "skipped": 2, "errors": 1}
        processed_paths = [Path("img1.jpg"), Path("img2.jpg"), Path("img3.jpg")]
        start_time = 0.0

        with patch("time.time", return_value=1.5):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert isinstance(result, DatabaseRegistrationResult)
        assert result.registered_count == 3
        assert result.skipped_count == 2
        assert result.error_count == 1
        assert result.processed_paths == processed_paths
        assert result.total_processing_time > 0

    def test_build_registration_result_all_registered(self, worker):
        """すべてが登録された場合"""
        stats = {"registered": 10, "variant": 0, "skipped": 0, "errors": 0}
        processed_paths = [Path(f"img{i}.jpg") for i in range(10)]
        start_time = 0.0

        with patch("time.time", return_value=2.0):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.registered_count == 10
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert len(result.processed_paths) == 10
        assert result.total_processing_time == 2.0

    def test_build_registration_result_all_skipped(self, worker):
        """すべてがスキップされた場合"""
        stats = {"registered": 0, "variant": 0, "skipped": 10, "errors": 0}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=1.0):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 10
        assert result.error_count == 0
        assert len(result.processed_paths) == 0

    def test_build_registration_result_all_errors(self, worker):
        """すべてがエラーになった場合"""
        stats = {"registered": 0, "variant": 0, "skipped": 0, "errors": 10}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=3.5):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 10
        assert len(result.processed_paths) == 0
        assert result.total_processing_time == 3.5

    def test_build_registration_result_processing_time_recorded(self, worker):
        """処理時間が正確に記録されるか"""
        stats = {"registered": 5, "variant": 0, "skipped": 3, "errors": 2}
        processed_paths = [Path(f"img{i}.jpg") for i in range(5)]
        start_time = 10.0

        with patch("time.time", return_value=15.5):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.total_processing_time == 5.5
        assert result.total_processing_time > 0

    def test_build_registration_result_processed_paths_included(self, worker):
        """processed_paths が正確に含まれるか"""
        processed_paths = [Path("img1.jpg"), Path("img2.jpg"), Path("img3.jpg")]
        stats = {"registered": 3, "variant": 0, "skipped": 0, "errors": 0}
        start_time = 0.0

        with patch("time.time", return_value=1.0):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.processed_paths == processed_paths
        assert len(result.processed_paths) == 3
        assert all(isinstance(p, Path) for p in result.processed_paths)

    def test_build_registration_result_info_log_output(self, worker):
        """INFO ログが出力されるか"""
        stats = {"registered": 5, "variant": 0, "skipped": 2, "errors": 1}
        processed_paths = [Path(f"img{i}.jpg") for i in range(5)]
        start_time = 0.0

        with (
            patch("time.time", return_value=2.0),
            patch("lorairo.gui.workers.registration_worker.logger") as mock_logger,
        ):
            worker._build_registration_result(stats, processed_paths, [], start_time)

            # INFO ログが呼ばれたことを確認
            mock_logger.info.assert_called_once()

            # ログメッセージの内容確認
            log_message = mock_logger.info.call_args[0][0]
            assert "データベース登録完了" in log_message
            assert "登録=5" in log_message
            assert "別版=0" in log_message
            assert "スキップ=2" in log_message
            assert "エラー=1" in log_message

    def test_build_registration_result_info_log_only(self, worker):
        """INFO ログのみが出力されるか（DEBUG ログは出力されないか）"""
        stats = {"registered": 3, "variant": 0, "skipped": 1, "errors": 1}
        processed_paths = [Path(f"img{i}.jpg") for i in range(3)]
        start_time = 0.0

        with (
            patch("time.time", return_value=1.5),
            patch("lorairo.gui.workers.registration_worker.logger") as mock_logger,
        ):
            worker._build_registration_result(stats, processed_paths, [], start_time)

            # DEBUG ログが呼ばれていないことを確認
            mock_logger.debug.assert_not_called()

            # INFO ログが呼ばれたことを確認
            assert mock_logger.info.called

    def test_build_registration_result_empty_result(self, worker):
        """空の結果を処理"""
        stats = {"registered": 0, "variant": 0, "skipped": 0, "errors": 0}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=0.1):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert result.processed_paths == []
        assert result.total_processing_time == 0.1

    def test_build_registration_result_type_validation(self, worker):
        """返却値が DatabaseRegistrationResult 型で、すべてのフィールドが存在するか"""
        stats = {"registered": 2, "variant": 0, "skipped": 1, "errors": 1}
        processed_paths = [Path("img1.jpg"), Path("img2.jpg")]
        start_time = 0.0

        with patch("time.time", return_value=2.5):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        # 型チェック
        assert isinstance(result, DatabaseRegistrationResult)

        # すべてのフィールドが存在するか (#633: variant_count を追加)
        assert hasattr(result, "registered_count")
        assert hasattr(result, "variant_count")
        assert hasattr(result, "skipped_count")
        assert hasattr(result, "error_count")
        assert hasattr(result, "processed_paths")
        assert hasattr(result, "total_processing_time")

        # フィールドの型チェック
        assert isinstance(result.registered_count, int)
        assert isinstance(result.variant_count, int)
        assert isinstance(result.skipped_count, int)
        assert isinstance(result.error_count, int)
        assert isinstance(result.processed_paths, list)
        assert isinstance(result.total_processing_time, float)

    def test_build_registration_result_counts_variants(self, worker):
        """#633: variant 統計が variant_count に反映される。"""
        stats = {"registered": 4, "variant": 3, "skipped": 1, "errors": 0}
        processed_paths = [Path(f"img{i}.jpg") for i in range(7)]
        start_time = 0.0

        with patch("time.time", return_value=1.0):
            result = worker._build_registration_result(stats, processed_paths, [], start_time)

        assert result.registered_count == 4
        assert result.variant_count == 3
        assert result.skipped_count == 1


class TestRegistrationErrorHandling:
    """エラーハンドリング・統合テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_image_files(self, temp_dir):
        """モック画像ファイル（複数パターン対応）"""
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"test_image_{i}.jpg"
            image_file.write_bytes(b"fake_image_data")
            image_files.append(image_file)
        return image_files

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager"""
        return ImageDatabaseManager(config_service=real_config_service, image_repo=real_repository)

    @pytest.fixture
    def mock_fsm(self, mock_image_files):
        """ファイルシステムのみMock化"""
        mock = Mock(spec=FileSystemManager)
        mock.get_image_files.return_value = mock_image_files
        return mock

    @pytest.fixture
    def worker_setup(self, temp_dir, real_db_manager, mock_fsm):
        """ワーカー初期化フィクスチャ"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        return worker, real_db_manager, mock_fsm

    def test_cancellation_during_execution(self, worker_setup):
        """キャンセル実行時にCancellationErrorが発生することを確認"""
        worker, _, _ = worker_setup
        worker.cancel()

        with pytest.raises(CancellationError, match="処理がキャンセルされました"):
            worker.execute()

    def test_cancellation_mid_loop(self, temp_dir, real_db_manager, mock_fsm):
        """2件処理後のキャンセル確認"""
        # 3つの画像ファイルを用意
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"image_{i}.jpg"
            image_file.write_bytes(b"fake")
            image_files.append(image_file)
        mock_fsm.get_image_files.return_value = image_files

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        # register_original_imageをMock化 (#633: detect_duplicate_image は統一エントリ内で処理されるため除去)
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(worker, "_check_cancellation") as mock_cancel,
        ):
            mock_register.return_value = (1, {})

            # 2回目のチェック時にキャンセル
            def cancel_on_second_call():
                if mock_cancel.call_count >= 2:
                    raise CancellationError("処理がキャンセルされました")

            mock_cancel.side_effect = cancel_on_second_call

            with pytest.raises(CancellationError, match="処理がキャンセルされました"):
                worker.execute()

    def test_exception_in_db_registration(self, temp_dir, real_db_manager, mock_fsm):
        """register_original_imageが例外を発生した場合の処理確認 (#633: 統一エントリ経由)"""
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_error_record") as mock_save_error,
        ):
            mock_register.side_effect = ValueError("登録エラー")

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # save_error_recordが呼ばれたことを確認
            assert mock_save_error.called
            # error_countが増加したことを確認
            assert result.error_count == 3

    def test_secondary_error_in_save_error_record(self, temp_dir, real_db_manager, mock_fsm):
        """save_error_record自体が例外を発生した場合の処理確認 (#633: 統一エントリ経由)"""
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_error_record") as mock_save_error,
            patch("lorairo.gui.workers.registration_worker.logger") as mock_logger,
        ):
            mock_register.side_effect = ValueError("登録エラー")
            mock_save_error.side_effect = Exception("エラー保存失敗")

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 処理が継続されること（クラッシュしないこと）
            assert result.error_count == 3
            # logger.error で二次エラーが記録されることを確認
            # save_error_record の例外ハンドルで logger.error() が呼ばれる
            assert any(
                "エラーレコード保存失敗（二次エラー）" in str(call)
                for call in mock_logger.error.call_args_list
            )

    def test_progress_reporting_sequence(self, temp_dir, real_db_manager, mock_fsm):
        """進捗報告の呼び出し順序確認"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(worker, "_report_progress") as mock_progress,
            patch.object(worker, "_report_progress_throttled") as mock_progress_throttled,
            patch.object(worker, "_report_batch_progress_throttled") as mock_batch,
        ):
            mock_register.return_value = (1, {})

            worker.execute()

            # 進捗報告が呼ばれたことを確認
            assert mock_progress.called
            assert mock_progress_throttled.called
            # 最初の呼び出しで "画像ファイルを検索中..." を確認
            first_call = mock_progress.call_args_list[0]
            assert "画像ファイルを検索中" in first_call[0][1]
            # 最後の呼び出しで "データベース登録完了" を確認
            last_call = mock_progress.call_args_list[-1]
            assert "データベース登録完了" in last_call[0][1]
            # バッチ進捗が呼ばれたことを確認
            assert mock_batch.call_count >= 3

    def test_empty_directory_handling_integration(self, temp_dir, real_db_manager):
        """空ディレクトリ処理テスト（統合テスト版）"""
        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = []

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        result = worker.execute()

        # 全カウントが0であることを確認
        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0
        # 早期リターンで processed_paths が空であることを確認
        assert len(result.processed_paths) == 0

    def test_integration_with_split_methods(self, temp_dir, real_db_manager, mock_fsm):
        """分割メソッド（_register_single_image, _build_registration_result）の協調確認 (#633: 統一エントリ経由)"""
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
        ):
            mock_register.return_value = (1, {"id": 1})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 単一メソッド版と同じ動作を確認
            assert isinstance(result, DatabaseRegistrationResult)
            assert result.registered_count == 3
            assert result.skipped_count == 0
            assert result.error_count == 0
            assert len(result.processed_paths) == 3

    def test_integration_duplicate_detection_with_file_processing(
        self, temp_dir, real_db_manager, mock_fsm
    ):
        """重複検出時の関連ファイル処理確認"""
        # テスト用ファイル作成
        image_file = temp_dir / "duplicate_test.jpg"
        tag_file = temp_dir / "duplicate_test.txt"
        caption_file = temp_dir / "duplicate_test.caption"

        image_file.write_bytes(b"fake_image")
        tag_file.write_text("tag1, tag2", encoding="utf-8")
        caption_file.write_text("test caption", encoding="utf-8")

        mock_fsm.get_image_files.return_value = [image_file]

        # #633: 重複時の関連ファイル取り込みは統一エントリ register_image_with_side_effects
        # 内の _import_associated_files が担う。register_original_image を重複扱いにして
        # 実 entry を通すことで、save_tags/save_captions が既存 ID へ呼ばれることを確認する。
        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_tags") as mock_save_tags,
            patch.object(real_db_manager, "save_captions") as mock_save_captions,
            patch.object(real_db_manager.image_repo, "add_filename_alias") as mock_alias,
        ):
            # 重複画像を返す（既存 image_id = 999, classification=duplicate）
            mock_register.return_value = (999, {"phash_classification": "duplicate"})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 重複時でも関連ファイルが既存 ID(999) へ取り込まれることを確認
            mock_save_tags.assert_called_once()
            assert mock_save_tags.call_args[0][0] == 999
            mock_save_captions.assert_called_once()
            assert mock_save_captions.call_args[0][0] == 999
            # 重複時は filename alias が登録される
            mock_alias.assert_called_once()
            # スキップ数が増加することを確認
            assert result.skipped_count == 1

    def test_duplicate_skipped_even_if_alias_registration_fails(self, temp_dir, real_db_manager, mock_fsm):
        """add_filename_alias が SQLAlchemyError を送出しても skipped_count が増加する"""
        from sqlalchemy.exc import SQLAlchemyError

        image_file = temp_dir / "alias_fail_test.jpg"
        tag_file = temp_dir / "alias_fail_test.txt"
        image_file.write_bytes(b"fake_image")
        tag_file.write_text("tag1", encoding="utf-8")
        mock_fsm.get_image_files.return_value = [image_file]

        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_tags"),
            patch.object(real_db_manager, "save_captions"),
            patch.object(
                real_db_manager.image_repo,
                "add_filename_alias",
                side_effect=SQLAlchemyError("table not found"),
            ),
        ):
            # 重複扱い（既存 ID=999）。alias 登録は SQLAlchemyError で失敗するが
            # _register_filename_alias が握り潰すため skipped 集計は継続する (#633)。
            mock_register.return_value = (999, {"phash_classification": "duplicate"})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            assert result.skipped_count == 1
            assert result.error_count == 0

    def test_high_volume_image_processing(self, temp_dir, real_db_manager):
        """100個の画像処理時のパフォーマンステスト"""
        # 100個の画像ファイルを作成
        image_files = []
        for i in range(100):
            image_file = temp_dir / f"image_{i:03d}.jpg"
            image_file.write_bytes(b"x" * 1000)  # 小さめのダミーデータ
            image_files.append(image_file)

        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = image_files

        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
        ):
            mock_register.return_value = (1, {})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 100件全て処理されたことを確認
            assert result.registered_count == 100
            assert result.total_processing_time >= 0  # 処理時間が記録されること
            assert len(result.processed_paths) == 100

    def test_progress_report_call_count_verification(self, temp_dir, real_db_manager, mock_fsm):
        """進捗報告呼び出し回数の確認"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        with (
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(worker, "_report_progress") as mock_progress,
            patch.object(worker, "_report_progress_throttled") as mock_progress_throttled,
            patch.object(worker, "_report_batch_progress_throttled") as mock_batch,
        ):
            mock_register.return_value = (1, {})

            worker.execute()

            # _report_progress の呼び出し回数：開始 + ループ内 + 完了
            # 最低3回（開始、開始2、完了）以上
            assert mock_progress.call_count >= 3
            assert mock_progress_throttled.call_count == 3
            # _report_batch_progress_throttled は画像ごとに1回呼ばれる（3回）
            assert mock_batch.call_count == 3


class TestRegisterImageWithSideEffects:
    """register_image_with_side_effects() の副作用統一テスト (ADR 0061 §4, #633)。

    旧 TestRegisterSingleImageUnits の関連ファイル取り込み詳細は、責務が
    db_manager の統一エントリへ移ったため本クラスへ移設した。
    """

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def manager_setup(self):
        """register_original_image をモックした ImageDatabaseManager。"""
        mock_image_repo = Mock()
        manager = ImageDatabaseManager(config_service=ConfigurationService(), image_repo=mock_image_repo)
        manager.save_tags = Mock()
        manager.save_captions = Mock()
        mock_fsm = Mock(spec=FileSystemManager)
        return manager, mock_image_repo, mock_fsm

    def _patch_register(self, manager, return_value):
        return patch.object(manager, "register_original_image", return_value=return_value)

    def test_new_image_imports_into_new_id_no_alias(self, temp_dir, manager_setup):
        """新規画像 → REGISTERED、関連ファイルを新規 ID へ取り込み、alias は登録しない。"""
        from lorairo.database.db_manager import RegistrationOutcome

        manager, mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "new.jpg"
        image_path.write_bytes(b"fake")
        (temp_dir / "new.txt").write_text("tag1, tag2", encoding="utf-8")

        with self._patch_register(manager, (5, {"phash_classification": "new"})):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.REGISTERED
        assert result.image_id == 5
        manager.save_tags.assert_called_once()
        assert manager.save_tags.call_args[0][0] == 5
        mock_image_repo.add_filename_alias.assert_not_called()

    def test_variant_imports_into_variant_id_no_alias(self, temp_dir, manager_setup):
        """別版 → VARIANT、関連ファイルを別版(新規)ID へ取り込み、alias は登録しない。"""
        from lorairo.database.db_manager import RegistrationOutcome

        manager, mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "variant.jpg"
        image_path.write_bytes(b"fake")
        (temp_dir / "variant.caption").write_text("a caption", encoding="utf-8")

        with self._patch_register(manager, (8, {"phash_classification": "variant"})):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.VARIANT
        assert result.image_id == 8
        manager.save_captions.assert_called_once()
        assert manager.save_captions.call_args[0][0] == 8
        mock_image_repo.add_filename_alias.assert_not_called()

    def test_duplicate_imports_into_existing_id_with_alias(self, temp_dir, manager_setup):
        """重複 → DUPLICATE、関連ファイルを既存 ID へ取り込み、alias を登録する。"""
        from lorairo.database.db_manager import RegistrationOutcome

        manager, mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "dup.jpg"
        image_path.write_bytes(b"fake")
        (temp_dir / "dup.txt").write_text("t1", encoding="utf-8")

        with self._patch_register(manager, (99, {"phash_classification": "duplicate"})):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.DUPLICATE
        assert result.image_id == 99
        manager.save_tags.assert_called_once()
        assert manager.save_tags.call_args[0][0] == 99
        mock_image_repo.add_filename_alias.assert_called_once_with(99, "dup")

    def test_failed_registration_returns_failed_no_side_effects(self, temp_dir, manager_setup):
        """register_original_image が None → FAILED、副作用なし。"""
        from lorairo.database.db_manager import RegistrationOutcome

        manager, mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "fail.jpg"
        image_path.write_bytes(b"fake")
        (temp_dir / "fail.txt").write_text("t1", encoding="utf-8")

        with self._patch_register(manager, None):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.FAILED
        assert result.image_id is None
        manager.save_tags.assert_not_called()
        mock_image_repo.add_filename_alias.assert_not_called()

    def test_no_associated_files_skips_imports(self, temp_dir, manager_setup):
        """関連ファイル不在 → REGISTERED だが save は呼ばれない。"""
        from lorairo.database.db_manager import RegistrationOutcome

        manager, _mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "lonely.jpg"
        image_path.write_bytes(b"fake")

        with self._patch_register(manager, (1, {"phash_classification": "new"})):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.REGISTERED
        manager.save_tags.assert_not_called()
        manager.save_captions.assert_not_called()

    def test_multiple_tags_parsed_into_tag_data(self, temp_dir, manager_setup):
        """複数タグが TagAnnotationData として save_tags に渡る。"""
        manager, _mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "multi.jpg"
        image_path.write_bytes(b"fake")
        (temp_dir / "multi.txt").write_text("tag1, tag2, tag3", encoding="utf-8")

        with self._patch_register(manager, (1, {"phash_classification": "new"})):
            manager.register_image_with_side_effects(image_path, mock_fsm)

        manager.save_tags.assert_called_once()
        tags_data = manager.save_tags.call_args[0][1]
        assert [t["tag"] for t in tags_data] == ["tag1", "tag2", "tag3"]
        assert all(t["existing"] is True for t in tags_data)
        assert all(t["is_edited_manually"] is False for t in tags_data)

    def test_preloaded_annotations_used_without_file_read(self, temp_dir, manager_setup):
        """事前読み込み annotations が渡された場合はそれを使う (ファイル不在でも保存)。"""
        manager, _mock_image_repo, mock_fsm = manager_setup
        image_path = temp_dir / "preloaded.jpg"
        image_path.write_bytes(b"fake")  # .txt は作らない

        annotations = {"tags": ["pre1"], "captions": ["precap"]}
        with self._patch_register(manager, (3, {"phash_classification": "new"})):
            manager.register_image_with_side_effects(
                image_path, mock_fsm, associated_annotations=annotations
            )

        manager.save_tags.assert_called_once()
        manager.save_captions.assert_called_once()

    def test_alias_failure_does_not_break_outcome(self, temp_dir, manager_setup):
        """alias 登録の SQLAlchemyError は握り潰され outcome は DUPLICATE のまま。"""
        from sqlalchemy.exc import SQLAlchemyError

        from lorairo.database.db_manager import RegistrationOutcome

        manager, mock_image_repo, mock_fsm = manager_setup
        mock_image_repo.add_filename_alias.side_effect = SQLAlchemyError("no table")
        image_path = temp_dir / "dup2.jpg"
        image_path.write_bytes(b"fake")

        with self._patch_register(manager, (7, {"phash_classification": "duplicate"})):
            result = manager.register_image_with_side_effects(image_path, mock_fsm)

        assert result.outcome is RegistrationOutcome.DUPLICATE
        assert result.image_id == 7
