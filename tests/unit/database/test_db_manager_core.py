"""ImageDatabaseManager コアメソッドのユニットテスト

カバー対象:
- _get_current_project_id
- register_original_image / _prepare_image_metadata
- register_processed_image
- get_image_metadata / get_image_annotations
- get_models / get_tagger_models / get_score_models / get_captioner_models / get_upscaler_models / get_llm_models
- get_total_image_count / get_images_count_only
- detect_duplicate_image
- save_error_record / mark_errors_resolved_batch
- get_image_id_by_filepath
- get_dataset_status / get_annotation_status_counts
- filter_by_annotation_status
- get_low_res_image_path
- check_processed_image_exists
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
from lorairo.database.repository.project import ProjectRepository
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_image_repo() -> Mock:
    """モック化された ImageRepository (ADR 0035 段階 4)。"""

    return Mock(spec=ImageRepository)


@pytest.fixture
def mock_annotation_repo() -> Mock:
    """モック化された AnnotationRepository (ADR 0035 段階 5)。"""
    from lorairo.database.repository.annotation_record import AnnotationRepository

    return Mock(spec=AnnotationRepository)


@pytest.fixture
def mock_model_repo() -> Mock:
    """モック化された ModelRepository (ADR 0035 段階 1)。"""

    return Mock(spec=ModelRepository)


@pytest.fixture
def mock_provider_batch_repo() -> Mock:
    """モック化された ProviderBatchRepository (ADR 0035 段階 6)。"""
    from lorairo.database.repository.provider_batch import ProviderBatchRepository

    return Mock(spec=ProviderBatchRepository)


@pytest.fixture
def mock_project_repo() -> Mock:
    """モック化された ProjectRepository を返す (ADR 0035 段階 2)。"""
    return Mock(spec=ProjectRepository)


@pytest.fixture
def mock_error_record_repo() -> Mock:
    """モック化された ErrorRecordRepository を返す (ADR 0035 段階 3)。"""
    return Mock(spec=ErrorRecordRepository)


@pytest.fixture
def mock_config_service() -> Mock:
    """モック化された ConfigurationService を返す。"""
    svc = Mock(spec=ConfigurationService)
    svc.get_image_processing_config.return_value = {"upscaler": "RealESRGAN_x4plus"}
    return svc


@pytest.fixture
def manager(
    mock_config_service: Mock,
    mock_model_repo: Mock,
    mock_project_repo: Mock,
    mock_error_record_repo: Mock,
    mock_image_repo: Mock,
    mock_annotation_repo: Mock,
    mock_provider_batch_repo: Mock,
) -> ImageDatabaseManager:
    """ImageDatabaseManager のインスタンスを返す（依存はすべてモック）。

    ADR 0035 段階 6 (#423): legacy facade 撤廃後、Manager は各 Aggregate Repo を
    composition で保持する。全 Repo を Mock 注入してテストの独立性を確保する。
    """
    return ImageDatabaseManager(
        config_service=mock_config_service,
        fsm=None,
        model_repo=mock_model_repo,
        project_repo=mock_project_repo,
        error_record_repo=mock_error_record_repo,
        image_repo=mock_image_repo,
        annotation_repo=mock_annotation_repo,
        provider_batch_repo=mock_provider_batch_repo,
    )


# ---------------------------------------------------------------------------
# _get_current_project_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentProjectId:
    """_get_current_project_id メソッドのテスト"""

    def test_returns_cached_value_without_db_access(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock
    ) -> None:
        """キャッシュ済みの場合はリポジトリを呼ばずにキャッシュ値を返す。"""
        manager._cached_project_id = 42
        result = manager._get_current_project_id()
        assert result == 42
        # ADR 0035 段階 2: ensure_project は project_repo 経由で呼ばれる (DI contract)
        mock_project_repo.ensure_project.assert_not_called()

    def test_returns_none_when_project_root_unavailable(self, manager: ImageDatabaseManager) -> None:
        """project root 取得に失敗 (RuntimeError) したとき None を返す。"""
        # get_current_project_root は _get_current_project_id 内で lazy import されるため
        # db_core モジュール上のシンボルをパッチする。
        # _get_current_project_id は (RuntimeError, OSError, ValueError) を catch する。
        with patch(
            "lorairo.database.db_core.get_current_project_root", side_effect=RuntimeError("no root")
        ):
            result = manager._get_current_project_id()
        assert result is None

    def test_returns_none_when_ensure_project_fails(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock
    ) -> None:
        """ensure_project が SQLAlchemyError を投げたとき None を返す (project_id 未設定で続行)。"""
        mock_project_repo.ensure_project.side_effect = SQLAlchemyError("DB error")
        fake_root = Path("/fake/project")
        with patch("lorairo.database.db_core.get_current_project_root", return_value=fake_root):
            result = manager._get_current_project_id()
        assert result is None

    def test_caches_project_id_on_success(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock
    ) -> None:
        """正常取得後は _cached_project_id にキャッシュされる。"""
        mock_project_repo.ensure_project.return_value = 7

        fake_root = Path("/fake/project")
        with patch("lorairo.database.db_core.get_current_project_root", return_value=fake_root):
            # .lorairo-project は存在しないパスなので OSError が発生し project_root.name が使われる
            result = manager._get_current_project_id()

        assert result == 7
        assert manager._cached_project_id == 7

    def test_falls_back_to_project_root_name_on_non_dict_metadata(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock, tmp_path: Path
    ) -> None:
        """`.lorairo-project` が JSON object でない (list/string 等) なら project_root.name で fallback。

        Regression test for PR #476 review (P2): 旧 silent return は AttributeError を
        吸収していた。新仕様でも malformed metadata を recoverable に扱う。
        """
        project_root = tmp_path / "fake-project"
        project_root.mkdir()
        # 有効な JSON だが dict でない (list)
        (project_root / ".lorairo-project").write_text("[]", encoding="utf-8")
        mock_project_repo.ensure_project.return_value = 42

        with patch("lorairo.database.db_core.get_current_project_root", return_value=project_root):
            result = manager._get_current_project_id()

        assert result == 42
        # project_root.name でフォールバック呼び出し
        # ADR 0035 段階 2: DI contract — project_repo 経由で呼ばれる
        args, _ = mock_project_repo.ensure_project.call_args
        assert args[0] == "fake-project"


# ---------------------------------------------------------------------------
# register_processed_image
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterProcessedImage:
    """register_processed_image メソッドのテスト"""

    def test_returns_none_when_missing_required_keys(self, manager: ImageDatabaseManager) -> None:
        """必須キーが不足しているとき None を返す。"""
        incomplete_info: dict = {"width": 512}  # height, has_alpha が欠如
        result = manager.register_processed_image(1, Path("/data/img.jpg"), incomplete_info)
        assert result is None

    def test_returns_id_on_success(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """リポジトリが ID を返すとき、その ID を返す。"""
        mock_image_repo.add_processed_image.return_value = 99
        info = {"width": 512, "height": 512, "has_alpha": False}
        result = manager.register_processed_image(1, Path("/data/img.jpg"), info)
        assert result == 99

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """リポジトリが SQLAlchemyError を送出したとき呼び出し元に伝播 (silent return しない)。"""
        mock_image_repo.add_processed_image.side_effect = SQLAlchemyError("db error")
        info = {"width": 512, "height": 512, "has_alpha": False}
        with pytest.raises(SQLAlchemyError):
            manager.register_processed_image(1, Path("/data/img.jpg"), info)


# ---------------------------------------------------------------------------
# get_image_metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageMetadata:
    """get_image_metadata メソッドのテスト"""

    def test_returns_none_when_image_not_found(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """リポジトリが None を返すとき None を返す。"""
        mock_image_repo.get_image_metadata.return_value = None
        result = manager.get_image_metadata(9999)
        assert result is None

    def test_returns_metadata_dict_on_success(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """リポジトリが辞書を返すとき、その辞書を返す。"""
        expected = {"id": 1, "stored_image_path": "/data/img.jpg"}
        mock_image_repo.get_image_metadata.return_value = expected
        result = manager.get_image_metadata(1)
        assert result == expected

    def test_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """リポジトリが SQLAlchemyError を送出したとき例外が伝播する。"""
        mock_image_repo.get_image_metadata.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_image_metadata(1)


# ---------------------------------------------------------------------------
# get_image_annotations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageAnnotations:
    """get_image_annotations メソッドのテスト"""

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """リポジトリが SQLAlchemyError を送出したとき呼び出し元に伝播。"""
        mock_image_repo.get_image_annotations.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_image_annotations(1)

    def test_returns_repository_result_on_success(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """正常系ではリポジトリの返値をそのまま返す。"""
        expected = {"tags": [{"tag": "cat"}], "captions": [], "scores": [], "ratings": []}
        mock_image_repo.get_image_annotations.return_value = expected
        result = manager.get_image_annotations(1)
        assert result == expected


# ---------------------------------------------------------------------------
# get_models / get_*_models
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetModels:
    """モデル取得メソッドのテスト (ADR 0035 段階 1: ModelRepository 経由)"""

    def test_get_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_models: SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        mock_model_repo.get_models.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_models()

    def test_get_tagger_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_tagger_models: SQLAlchemyError は呼び出し元に伝播。"""
        mock_model_repo.get_models_by_type.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_tagger_models()

    def test_get_score_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_score_models: SQLAlchemyError は呼び出し元に伝播。"""
        mock_model_repo.get_models_by_type.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_score_models()

    def test_get_captioner_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_captioner_models: SQLAlchemyError は呼び出し元に伝播。"""
        mock_model_repo.get_models_by_type.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_captioner_models()

    def test_get_upscaler_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_upscaler_models: SQLAlchemyError は呼び出し元に伝播。"""
        mock_model_repo.get_models_by_type.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_upscaler_models()

    def test_get_llm_models_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_llm_models: SQLAlchemyError は呼び出し元に伝播。"""
        mock_model_repo.get_models_by_type.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_llm_models()

    def test_get_models_returns_list_on_success(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_models: 正常系では ModelRepository の返値をそのまま返す。"""
        expected = [{"id": 1, "name": "model_a"}]
        mock_model_repo.get_models.return_value = expected
        assert manager.get_models() == expected

    def test_get_tagger_models_passes_correct_type(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_tagger_models は 'tags' タイプで ModelRepository を呼び出す。"""
        mock_model_repo.get_models_by_type.return_value = []
        manager.get_tagger_models()
        mock_model_repo.get_models_by_type.assert_called_once_with("tags")

    def test_get_llm_models_passes_multimodal_type(
        self, manager: ImageDatabaseManager, mock_model_repo: Mock
    ) -> None:
        """get_llm_models は 'multimodal' タイプで ModelRepository を呼び出す。"""
        mock_model_repo.get_models_by_type.return_value = []
        manager.get_llm_models()
        mock_model_repo.get_models_by_type.assert_called_once_with("multimodal")


# ---------------------------------------------------------------------------
# get_total_image_count / get_images_count_only
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageCounting:
    """画像件数取得メソッドのテスト"""

    def test_get_total_image_count_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        mock_image_repo.get_total_image_count.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_total_image_count()

    def test_get_total_image_count_returns_count_on_success(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """正常系ではリポジトリの値を返す。"""
        mock_image_repo.get_total_image_count.return_value = 42
        assert manager.get_total_image_count() == 42

    def test_get_images_count_only_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        mock_image_repo.get_images_count_only.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_images_count_only()


# ---------------------------------------------------------------------------
# detect_duplicate_image
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectDuplicateImage:
    """detect_duplicate_image メソッドのテスト"""

    def test_returns_none_when_phash_calculation_fails(self, manager: ImageDatabaseManager) -> None:
        """pHash 計算失敗時は None を返す（重複なしとして扱う）。"""
        with patch("lorairo.database.db_manager.calculate_phash", side_effect=ValueError("bad image")):
            result = manager.detect_duplicate_image(Path("/data/img.jpg"))
        assert result is None

    def test_returns_none_when_no_duplicate(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """重複がない場合は None を返す。"""
        attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        with (
            patch("lorairo.database.db_manager.calculate_phash", return_value="aabbccdd"),
            patch.object(FileSystemManager, "get_image_info", return_value=attrs),
        ):
            mock_image_repo.find_phash_candidates.return_value = []
            result = manager.detect_duplicate_image(Path("/data/img.jpg"))
        assert result is None

    def test_returns_image_id_when_duplicate_confirmed(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """pHash 一致かつ属性一致 (重複確定) の場合は既存の image_id を返す (ADR 0061)。"""
        attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        with (
            patch("lorairo.database.db_manager.calculate_phash", return_value="aabbccdd"),
            patch.object(FileSystemManager, "get_image_info", return_value=attrs),
        ):
            mock_image_repo.find_phash_candidates.return_value = [{"id": 5, **attrs}]
            result = manager.detect_duplicate_image(Path("/data/img.jpg"))
        assert result == 5

    def test_returns_none_when_variant(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """pHash 一致だが属性差がある別版は重複とみなさず None を返す (ADR 0061)。"""
        attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        candidate = {"id": 5, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": True}
        with (
            patch("lorairo.database.db_manager.calculate_phash", return_value="aabbccdd"),
            patch.object(FileSystemManager, "get_image_info", return_value=attrs),
        ):
            mock_image_repo.find_phash_candidates.return_value = [candidate]
            result = manager.detect_duplicate_image(Path("/data/img.jpg"))
        assert result is None

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """リポジトリの SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        with (
            patch("lorairo.database.db_manager.calculate_phash", return_value="aabbccdd"),
            patch.object(FileSystemManager, "get_image_info", return_value=attrs),
        ):
            mock_image_repo.find_phash_candidates.side_effect = SQLAlchemyError("db error")
            with pytest.raises(SQLAlchemyError):
                manager.detect_duplicate_image(Path("/data/img.jpg"))

    def test_returns_none_on_oserror(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """pHash 計算で OSError 系 (PermissionError, UnidentifiedImageError 等) が出たら None。

        Regression test for PR #476 review (P2): 旧 silent return は OSError も
        catch していた。新仕様でも per-file tolerance を維持し directory scan 全体を
        止めない。
        """
        with patch(
            "lorairo.database.db_manager.calculate_phash",
            side_effect=PermissionError("cannot read"),
        ):
            result = manager.detect_duplicate_image(Path("/data/img.jpg"))
        assert result is None
        mock_image_repo.find_phash_candidates.assert_not_called()


# ---------------------------------------------------------------------------
# save_error_record
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveErrorRecord:
    """save_error_record メソッドのテスト (ADR 0035 段階 3: error_record_repo 経由)"""

    def test_returns_error_id_on_success(
        self, manager: ImageDatabaseManager, mock_error_record_repo: Mock
    ) -> None:
        """正常系では error_record_repo が返した error_id を返す。"""
        mock_error_record_repo.save_error_record.return_value = 10
        result = manager.save_error_record(
            operation_type="annotation",
            error_type="APIError",
            error_message="timeout",
        )
        assert result == 10

    def test_returns_minus_one_on_exception(
        self, manager: ImageDatabaseManager, mock_error_record_repo: Mock
    ) -> None:
        """例外が発生した場合は -1 を返す (二次エラー防止、PR #476)。"""
        mock_error_record_repo.save_error_record.side_effect = Exception("db error")
        result = manager.save_error_record(
            operation_type="registration",
            error_type="FileNotFoundError",
            error_message="file missing",
        )
        assert result == -1


# ---------------------------------------------------------------------------
# mark_errors_resolved_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMarkErrorsResolvedBatch:
    """mark_errors_resolved_batch メソッドのテスト (ADR 0035 段階 3: error_record_repo 経由)"""

    def test_returns_success_tuple_on_success(
        self, manager: ImageDatabaseManager, mock_error_record_repo: Mock
    ) -> None:
        """正常系では error_record_repo の返値をそのまま返す。"""
        mock_error_record_repo.mark_errors_resolved_batch.return_value = (True, 3)
        result = manager.mark_errors_resolved_batch([1, 2, 3])
        assert result == (True, 3)

    def test_raises_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_error_record_repo: Mock
    ) -> None:
        """DB 失敗時は SQLAlchemyError を呼び出し元へ伝播させる。"""
        mock_error_record_repo.mark_errors_resolved_batch.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.mark_errors_resolved_batch([1, 2, 3])


# ---------------------------------------------------------------------------
# get_image_id_by_filepath
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageIdByFilepath:
    """get_image_id_by_filepath メソッドのテスト"""

    def test_returns_id_on_success(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """正常系ではリポジトリの返値を返す。"""
        mock_image_repo.get_image_id_by_filepath.return_value = 7
        result = manager.get_image_id_by_filepath("/data/img.jpg")
        assert result == 7

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """DB 失敗時は SQLAlchemyError を呼び出し元へ伝播させる。"""
        mock_image_repo.get_image_id_by_filepath.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_image_id_by_filepath("/data/img.jpg")

    def test_returns_none_when_not_found(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """リポジトリが None を返すとき None を返す。"""
        mock_image_repo.get_image_id_by_filepath.return_value = None
        result = manager.get_image_id_by_filepath("/nonexistent/img.jpg")
        assert result is None


# ---------------------------------------------------------------------------
# get_dataset_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDatasetStatus:
    """get_dataset_status メソッドのテスト"""

    def test_returns_ready_when_images_exist(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """画像が存在するとき status = 'ready' を返す。"""
        mock_image_repo.get_total_image_count.return_value = 5
        result = manager.get_dataset_status()
        assert result["status"] == "ready"
        assert result["total_images"] == 5

    def test_returns_empty_when_no_images(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """画像が 0 件のとき status = 'empty' を返す。"""
        mock_image_repo.get_total_image_count.return_value = 0
        result = manager.get_dataset_status()
        assert result["status"] == "empty"
        assert result["total_images"] == 0

    def test_returns_error_status_on_sqlalchemy_error(self, manager: ImageDatabaseManager) -> None:
        """get_total_image_count が SQLAlchemyError を送出したとき status = 'error' を返す。

        UI status バー向けの silent return を維持 (coding-style.md の境界層変換に該当)。
        """
        with patch.object(manager, "get_total_image_count", side_effect=SQLAlchemyError("db error")):
            result = manager.get_dataset_status()
        assert result["status"] == "error"
        assert result["total_images"] == 0


# ---------------------------------------------------------------------------
# get_low_res_image_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLowResImagePath:
    """get_low_res_image_path メソッドのテスト"""

    def test_returns_path_when_found(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """処理済み画像が見つかった場合はパスを返す。"""
        mock_image_repo.get_processed_image.return_value = {"stored_image_path": "/data/low_res.jpg"}
        result = manager.get_low_res_image_path(1)
        assert result == "/data/low_res.jpg"

    def test_returns_none_when_not_found(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """処理済み画像が見つからない場合は None を返す。"""
        mock_image_repo.get_processed_image.return_value = None
        result = manager.get_low_res_image_path(1)
        assert result is None

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """DB 失敗時は SQLAlchemyError を呼び出し元へ伝播させる。"""
        mock_image_repo.get_processed_image.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.get_low_res_image_path(1)

    def test_returns_none_when_path_missing_from_metadata(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """メタデータに stored_image_path が無い場合は None を返す。"""
        mock_image_repo.get_processed_image.return_value = {"width": 512}
        result = manager.get_low_res_image_path(1)
        assert result is None


# ---------------------------------------------------------------------------
# check_processed_image_exists
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckProcessedImageExists:
    """check_processed_image_exists メソッドのテスト"""

    def test_returns_metadata_when_exists(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """処理済み画像が存在するとき、そのメタデータを返す。"""
        expected = {"id": 3, "stored_image_path": "/data/512.jpg"}
        mock_image_repo.get_processed_image.return_value = expected
        result = manager.check_processed_image_exists(1, 512)
        assert result == expected

    def test_returns_none_when_not_exists(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """処理済み画像が存在しないとき None を返す。"""
        mock_image_repo.get_processed_image.return_value = None
        result = manager.check_processed_image_exists(1, 512)
        assert result is None

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """DB 失敗時は SQLAlchemyError を呼び出し元へ伝播させる。"""
        mock_image_repo.get_processed_image.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.check_processed_image_exists(1, 512)


# ---------------------------------------------------------------------------
# register_original_image (エラーパス)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterOriginalImage:
    """register_original_image の主要エラーパステスト"""

    def test_returns_none_when_image_info_unavailable(self, manager: ImageDatabaseManager) -> None:
        """fsm.get_image_info が None を返すとき None を返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = None

        result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)
        assert result is None

    def test_returns_none_when_phash_calculation_fails(self, manager: ImageDatabaseManager) -> None:
        """pHash 計算時に ValueError が発生したとき None を返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 512, "height": 512, "has_alpha": False}

        with patch("lorairo.database.db_manager.calculate_phash", side_effect=ValueError("bad image")):
            result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)
        assert result is None

    def test_returns_none_when_storage_save_fails(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """fsm.save_original_image が None を返すとき None を返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 512, "height": 512, "has_alpha": False}
        mock_fsm.save_original_image.return_value = None

        with patch("lorairo.database.db_manager.calculate_phash", return_value="aabb"):
            mock_image_repo.find_phash_candidates.return_value = []
            result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)
        assert result is None

    def test_returns_none_on_oserror_from_metadata_prep(
        self, manager: ImageDatabaseManager, mock_image_repo: Mock
    ) -> None:
        """_prepare_image_metadata 経由で OSError (UnidentifiedImageError 等) が出たら None。

        Regression test for PR #476 review (P1): 旧 silent return は OSError も
        catch していた。新仕様でも per-file tolerance を維持し worker 全体を止めない。
        PIL の UnidentifiedImageError は OSError サブクラス。
        """
        mock_fsm = Mock()
        mock_fsm.get_image_info.side_effect = OSError("cannot identify image file")

        result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is None
        mock_image_repo.find_phash_candidates.assert_not_called()
        mock_image_repo.add_original_image.assert_not_called()


# ---------------------------------------------------------------------------
# register_prompt_tags (タグが空のとき早期リターン)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterPromptTags:
    """register_prompt_tags メソッドのテスト"""

    def test_returns_early_when_tags_empty(
        self, manager: ImageDatabaseManager, mock_annotation_repo: Mock
    ) -> None:
        """タグリストが空のとき何もしない。"""
        manager.register_prompt_tags(1, [])
        mock_annotation_repo.save_annotations.assert_not_called()

    def test_calls_save_tags_with_correct_structure(
        self, manager: ImageDatabaseManager, mock_annotation_repo: Mock
    ) -> None:
        """タグが存在するとき save_annotations を呼び出す。"""
        manager.register_prompt_tags(1, ["cat", "dog"])
        mock_annotation_repo.save_annotations.assert_called_once()
        call_args = mock_annotation_repo.save_annotations.call_args[0]
        image_id_passed = call_args[0]
        annotations = call_args[1]
        assert image_id_passed == 1
        assert len(annotations["tags"]) == 2
        assert annotations["tags"][0]["tag"] == "cat"
        assert annotations["tags"][0]["existing"] is True


# ---------------------------------------------------------------------------
# filter_by_annotation_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterByAnnotationStatus:
    """filter_by_annotation_status メソッドのテスト"""

    def test_returns_empty_list_when_error_mode_has_no_errors(
        self,
        manager: ImageDatabaseManager,
        mock_image_repo: Mock,
        mock_error_record_repo: Mock,
    ) -> None:
        """error=True かつエラー画像 ID が空のとき空リストを返す。"""
        mock_image_repo.get_session.return_value = MagicMock()
        # ADR 0035 段階 3 (#423): error_record_repo 経由で取得される。
        mock_error_record_repo.get_error_image_ids.return_value = []
        result = manager.filter_by_annotation_status(error=True)
        assert result == []

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_image_repo: Mock) -> None:
        """セッション取得で SQLAlchemyError が発生したら呼び出し元へ伝播させる。"""
        mock_image_repo.get_session.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            manager.filter_by_annotation_status(completed=True)
