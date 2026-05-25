"""ImageDatabaseManager 追加カバレッジテスト

未カバーパス対象:
- create_default (58-62)
- _get_current_project_id: metadata読み込み成功パス (86)
- _prepare_image_metadata: 成功パス (136-146)
- register_original_image: 成功パス・重複パス・例外パス (170-204)
- _handle_duplicate_image: 各パス (223-248)
- _generate_thumbnail_512px: DB登録失敗パス (290)
- save_tags/captions/scores/ratings: エラーパス (459-461, 465-476, 480-491, 495-506)
- register_prompt_tags: save_tags エラーパス (526-528)
- save_score: 各パス (534-549)
- get_processed_metadata: 各パス (608-622)
- get_manual_edit_model_id: (693-698)
- get_images_by_filter: 各パス (714-720)
- get_image_ids_from_directory: 各パス (789-814)
- get_annotation_status_counts: 各パス (837-870)
- filter_by_annotation_status: 完了・全件・例外パス (891-913)
- get_directory_images_metadata: 各パス (929-948)
- check_processed_image_exists: 存在する場合 (995)
- check_image_has_annotation: 各パス (1117-1138)
- get_annotated_image_ids: (1150)
- execute_filtered_search: 各パス (1164-1173)
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.project import ProjectRepository
from lorairo.services.configuration_service import ConfigurationService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repository() -> Mock:
    """モック化された ImageRepository を返す。"""
    return Mock(spec=ImageRepository)


@pytest.fixture
def mock_config_service() -> Mock:
    """モック化された ConfigurationService を返す。"""
    svc = Mock(spec=ConfigurationService)
    svc.get_image_processing_config.return_value = {"upscaler": "RealESRGAN_x4plus"}
    return svc


@pytest.fixture
def mock_project_repo() -> Mock:
    """モック化された ProjectRepository を返す (ADR 0035 段階 2)。"""
    return Mock(spec=ProjectRepository)


@pytest.fixture
def mock_error_record_repo() -> Mock:
    """モック化された ErrorRecordRepository を返す (ADR 0035 段階 3)。"""
    return Mock(spec=ErrorRecordRepository)


@pytest.fixture
def manager(
    mock_repository: Mock,
    mock_config_service: Mock,
    mock_project_repo: Mock,
    mock_error_record_repo: Mock,
) -> ImageDatabaseManager:
    """ImageDatabaseManager のインスタンスを返す（依存はすべてモック）。"""
    return ImageDatabaseManager(
        repository=mock_repository,
        config_service=mock_config_service,
        fsm=None,
        project_repo=mock_project_repo,
        error_record_repo=mock_error_record_repo,
    )


# ---------------------------------------------------------------------------
# create_default
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateDefault:
    """create_default ファクトリメソッドのテスト"""

    def test_creates_instance_with_defaults(self) -> None:
        """create_default はImageDatabaseManagerインスタンスを返す。"""
        mock_repo = Mock(spec=ImageRepository)
        mock_config = Mock(spec=ConfigurationService)
        with patch("lorairo.database.db_manager.ImageRepository", return_value=mock_repo):
            with patch(
                "lorairo.services.configuration_service.ConfigurationService",
                return_value=mock_config,
            ):
                instance = ImageDatabaseManager.create_default()
        assert isinstance(instance, ImageDatabaseManager)


# ---------------------------------------------------------------------------
# _get_current_project_id — metadata 読み込み成功パス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentProjectIdMetadata:
    """_get_current_project_id のメタデータ読み込みパスのテスト"""

    def test_uses_name_from_metadata_file(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock
    ) -> None:
        """メタデータファイルが存在するとき、そのname フィールドを使用する。"""
        # ADR 0035 段階 2: ensure_project は project_repo 経由で呼ばれる (DI contract)
        mock_project_repo.ensure_project.return_value = 10
        fake_root = Path("/tmp/fake_project")

        # .lorairo-project ファイルが読めるようにパッチ
        metadata_content = '{"name": "my_project"}'
        with patch("lorairo.database.db_core.get_current_project_root", return_value=fake_root):
            with patch("pathlib.Path.read_text", return_value=metadata_content):
                result = manager._get_current_project_id()

        assert result == 10
        mock_project_repo.ensure_project.assert_called_once_with("my_project", fake_root)

    def test_falls_back_to_dir_name_on_json_error(
        self, manager: ImageDatabaseManager, mock_project_repo: Mock
    ) -> None:
        """JSONDecodeError が発生したとき、ディレクトリ名にフォールバックする。"""
        mock_project_repo.ensure_project.return_value = 20
        fake_root = Path("/tmp/my_dir")

        with patch("lorairo.database.db_core.get_current_project_root", return_value=fake_root):
            with patch("pathlib.Path.read_text", side_effect=OSError("no file")):
                result = manager._get_current_project_id()

        assert result == 20
        mock_project_repo.ensure_project.assert_called_once_with("my_dir", fake_root)


# ---------------------------------------------------------------------------
# _prepare_image_metadata — 成功パス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrepareImageMetadata:
    """_prepare_image_metadata の成功パスのテスト"""

    def test_returns_metadata_phash_and_path_on_success(self, manager: ImageDatabaseManager) -> None:
        """全ステップ成功時に (metadata, phash, stored_path) タプルを返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/original.jpg")

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            result = manager._prepare_image_metadata(Path("/data/img.jpg"), mock_fsm)

        assert result is not None
        metadata, phash, stored_path = result
        assert phash == "abc123"
        assert stored_path == Path("/storage/original.jpg")
        assert metadata["phash"] == "abc123"
        assert "uuid" in metadata
        assert metadata["original_image_path"] == str(Path("/data/img.jpg"))


# ---------------------------------------------------------------------------
# register_original_image — 成功パス・重複パス・例外パス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterOriginalImageExtended:
    """register_original_image の追加テスト"""

    def test_returns_image_id_and_metadata_on_success(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """正常登録時に (image_id, metadata) を返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/img.jpg")
        mock_repository.find_duplicate_image_by_phash.return_value = None
        mock_repository.add_original_image.return_value = 100

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            with patch.object(manager, "_get_current_project_id", return_value=None):
                with patch.object(manager, "_generate_thumbnail_512px"):
                    result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is not None
        image_id, _metadata = result
        assert image_id == 100

    def test_returns_existing_id_when_duplicate(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """pHash で重複が見つかった場合、既存 ID とメタデータを返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/img.jpg")
        mock_repository.find_duplicate_image_by_phash.return_value = 5
        # check_processed_image_exists から既存512px有りを返す
        existing_meta = {"id": 5, "stored_image_path": "/storage/existing.jpg"}
        mock_repository.get_processed_image.return_value = existing_meta
        mock_repository.get_image_metadata.return_value = {"id": 5, "stored_image_path": "/s/e.jpg"}

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is not None
        existing_id, _metadata = result
        assert existing_id == 5

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """SQLAlchemyError は Worker boundary に伝播 (silent return しない)。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/img.jpg")
        mock_repository.find_duplicate_image_by_phash.return_value = None
        mock_repository.add_original_image.side_effect = SQLAlchemyError("DB crashed")

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            with patch.object(manager, "_get_current_project_id", return_value=None):
                with pytest.raises(SQLAlchemyError):
                    manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

    def test_returns_none_on_input_value_error(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """入力起因の ValueError は正常系扱いで None を返す。"""
        mock_fsm = Mock()
        # get_image_info が空辞書で _prepare_image_metadata が ValueError を raise
        mock_fsm.get_image_info.return_value = {}

        result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is None

    def test_thumbnail_generation_failure_does_not_prevent_registration(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """512px サムネイル生成に失敗しても、登録結果は返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/img.jpg")
        mock_repository.find_duplicate_image_by_phash.return_value = None
        mock_repository.add_original_image.return_value = 42

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            with patch.object(manager, "_get_current_project_id", return_value=None):
                with patch.object(
                    manager, "_generate_thumbnail_512px", side_effect=RuntimeError("thumb error")
                ):
                    result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is not None
        image_id, _ = result
        assert image_id == 42


# ---------------------------------------------------------------------------
# _handle_duplicate_image
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleDuplicateImage:
    """_handle_duplicate_image メソッドのテスト"""

    def test_generates_512px_when_not_exists(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """512px 画像が存在しない場合、生成を試みる。"""
        mock_fsm = Mock()
        # 512px 不在
        mock_repository.get_processed_image.return_value = None
        existing_meta = {"id": 3, "stored_image_path": "/s/orig.jpg"}
        mock_repository.get_image_metadata.return_value = existing_meta

        with patch.object(manager, "_generate_thumbnail_512px") as mock_gen:
            result = manager._handle_duplicate_image(3, Path("/data/img.jpg"), mock_fsm)

        mock_gen.assert_called_once()
        assert result[0] == 3

    def test_skips_generation_when_512px_exists(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """512px 画像が既に存在する場合、生成をスキップする。"""
        mock_fsm = Mock()
        existing_512px = {"id": 10, "stored_image_path": "/s/512.jpg"}
        mock_repository.get_processed_image.return_value = existing_512px
        mock_repository.get_image_metadata.return_value = {"id": 3, "stored_image_path": "/s/o.jpg"}

        with patch.object(manager, "_generate_thumbnail_512px") as mock_gen:
            result = manager._handle_duplicate_image(3, Path("/data/img.jpg"), mock_fsm)

        mock_gen.assert_not_called()
        assert result[0] == 3

    def test_handles_exception_during_512px_check(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """512px チェック中の例外は処理続行（メタデータは返す）。"""
        mock_fsm = Mock()
        mock_repository.get_processed_image.side_effect = [
            RuntimeError("check error"),
            {"id": 3, "stored_image_path": "/s/o.jpg"},
        ]
        mock_repository.get_image_metadata.return_value = {"id": 3, "stored_image_path": "/s/o.jpg"}

        result = manager._handle_duplicate_image(3, Path("/data/img.jpg"), mock_fsm)

        assert result[0] == 3

    def test_returns_empty_metadata_when_not_found(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """既存メタデータが取得できない場合、空辞書で返す。"""
        mock_fsm = Mock()
        mock_repository.get_processed_image.return_value = None
        # 最初の get_image_metadata (512px 生成用): None
        # 2番目の get_image_metadata (返却用): None
        mock_repository.get_image_metadata.return_value = None

        result = manager._handle_duplicate_image(3, Path("/data/img.jpg"), mock_fsm)

        assert result[0] == 3
        assert result[1] == {}


# ---------------------------------------------------------------------------
# _generate_thumbnail_512px — DB登録失敗パス (line 290)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateThumbnail512pxDbFailure:
    """_generate_thumbnail_512px の DB 登録失敗パスのテスト"""

    def test_logs_warning_when_db_registration_fails(self, manager: ImageDatabaseManager) -> None:
        """DB 登録が None を返した場合、警告を出す（例外はなし）。"""
        mock_fsm = Mock()
        processed_path = Path("/data/processed.jpg")
        processing_metadata = {"was_upscaled": False}

        with patch.object(
            manager, "_create_and_save_thumbnail", return_value=(processed_path, processing_metadata)
        ):
            with patch.object(manager, "_register_thumbnail_in_db", return_value=None):
                # 例外なしで正常終了
                manager._generate_thumbnail_512px(1, Path("/data/orig.jpg"), {}, mock_fsm)


# ---------------------------------------------------------------------------
# save_tags / save_captions / save_scores / save_ratings — エラーパス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveAnnotationMethods:
    """save_tags, save_captions, save_scores, save_ratings のテスト"""

    def test_save_tags_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_tags: リポジトリ例外が伝播する。"""
        mock_repository.save_annotations.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.save_tags(1, [])

    def test_save_captions_success_calls_repository(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_captions: 正常系でリポジトリを呼ぶ。"""
        caption_data = {"text": "caption", "model_id": 1, "is_edited_manually": False}
        manager.save_captions(1, [caption_data])
        mock_repository.save_annotations.assert_called_once()

    def test_save_captions_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_captions: リポジトリ例外が伝播する。"""
        mock_repository.save_annotations.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.save_captions(1, [])

    def test_save_scores_success_calls_repository(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_scores: 正常系でリポジトリを呼ぶ。"""
        score_data = {"score": 0.9, "model_id": 1, "is_edited_manually": False}
        manager.save_scores(1, [score_data])
        mock_repository.save_annotations.assert_called_once()

    def test_save_scores_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_scores: リポジトリ例外が伝播する。"""
        mock_repository.save_annotations.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.save_scores(1, [])

    def test_save_ratings_success_calls_repository(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_ratings: 正常系でリポジトリを呼ぶ。"""
        rating_data = {"rating": "general", "model_id": 1, "is_edited_manually": False}
        manager.save_ratings(1, [rating_data])
        mock_repository.save_annotations.assert_called_once()

    def test_save_ratings_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_ratings: リポジトリ例外が伝播する。"""
        mock_repository.save_annotations.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.save_ratings(1, [])


# ---------------------------------------------------------------------------
# register_prompt_tags — save_tags 例外パス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterPromptTagsException:
    """register_prompt_tags の例外パスのテスト"""

    def test_does_not_raise_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_tags が SQLAlchemyError を送出しても register_prompt_tags は raise しない (best-effort)。"""
        mock_repository.save_annotations.side_effect = SQLAlchemyError("DB error")
        # best-effort: SQLAlchemyError は warning に畳んで raise しない
        manager.register_prompt_tags(1, ["cat", "dog"])

    def test_does_not_raise_on_value_error(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_tags が ValueError を送出しても register_prompt_tags は raise しない (best-effort)。"""
        mock_repository.save_annotations.side_effect = ValueError("bad input")
        manager.register_prompt_tags(1, ["cat", "dog"])


# ---------------------------------------------------------------------------
# save_score
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveScore:
    """save_score メソッドのテスト"""

    def test_returns_early_when_score_is_none(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """score が None の場合、save_scores を呼ばない。"""
        manager.save_score(1, {"model_id": 1})
        mock_repository.save_annotations.assert_not_called()

    def test_returns_early_when_model_id_is_none(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """model_id が None の場合、save_scores を呼ばない。"""
        manager.save_score(1, {"score": 0.9})
        mock_repository.save_annotations.assert_not_called()

    def test_calls_save_scores_on_valid_data(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """score と model_id が揃っているとき save_scores を呼ぶ。"""
        manager.save_score(1, {"score": 0.85, "model_id": 2})
        mock_repository.save_annotations.assert_called_once()

    def test_does_not_raise_on_sqlalchemy_error(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """save_scores が SQLAlchemyError を送出しても save_score は raise しない (best-effort)。"""
        mock_repository.save_annotations.side_effect = SQLAlchemyError("DB error")
        # best-effort: SQLAlchemyError は warning に畳んで raise しない
        manager.save_score(1, {"score": 0.85, "model_id": 2})


# ---------------------------------------------------------------------------
# get_processed_metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetProcessedMetadata:
    """get_processed_metadata メソッドのテスト"""

    def test_returns_empty_list_when_no_processed_images(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """処理済み画像がないとき空リストを返す。"""
        mock_repository.get_processed_image.return_value = []
        result = manager.get_processed_metadata(1)
        assert result == []

    def test_returns_list_when_found(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """処理済み画像が存在するとき、そのリストを返す。"""
        expected = [{"id": 10, "stored_image_path": "/s/512.jpg"}]
        mock_repository.get_processed_image.return_value = expected
        result = manager.get_processed_metadata(1)
        assert result == expected

    def test_returns_empty_list_when_repository_returns_non_list(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """リポジトリがリスト以外（None等）を返したとき空リストを返す。"""
        mock_repository.get_processed_image.return_value = None
        result = manager.get_processed_metadata(1)
        assert result == []

    def test_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """リポジトリが例外を送出したとき、例外が伝播する。"""
        mock_repository.get_processed_image.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.get_processed_metadata(1)


# ---------------------------------------------------------------------------
# get_manual_edit_model_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetManualEditModelId:
    """get_manual_edit_model_id メソッドのテスト"""

    def test_returns_model_id_via_injected_model_repo(
        self, mock_repository: Mock, mock_config_service: Mock
    ) -> None:
        """injected model_repo の _get_or_create_manual_edit_model 経由で model_id を返す (DI contract)。

        PR #477 review (P2): クラス経由 static 呼び出しではなく、injected instance 経由で
        dispatch することを固定。test double / subclass override / tenant-aware wrapper を尊重する。
        """
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = Mock(return_value=mock_session)
        mock_session_ctx.__exit__ = Mock(return_value=False)
        mock_session_factory = Mock(return_value=mock_session_ctx)
        mock_model_repo = Mock()
        mock_model_repo.session_factory = mock_session_factory
        # injected model_repo のメソッドが呼ばれることを直接固定
        mock_model_repo._get_or_create_manual_edit_model = Mock(return_value=99)

        mgr = ImageDatabaseManager(
            repository=mock_repository,
            config_service=mock_config_service,
            model_repo=mock_model_repo,
        )
        result = mgr.get_manual_edit_model_id()

        assert result == 99
        # injected method が session 引数で呼ばれた
        mock_model_repo._get_or_create_manual_edit_model.assert_called_once_with(mock_session)

    def test_caches_model_id_on_second_call(self, mock_repository: Mock, mock_config_service: Mock) -> None:
        """2回目以降の呼び出しはキャッシュから返す (ADR 0035 段階 1)。"""
        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__ = Mock(return_value=mock_session)
        mock_session_ctx.__exit__ = Mock(return_value=False)
        mock_session_factory = Mock(return_value=mock_session_ctx)
        mock_model_repo = Mock()
        mock_model_repo.session_factory = mock_session_factory
        mock_model_repo._get_or_create_manual_edit_model = Mock(return_value=55)

        mgr = ImageDatabaseManager(
            repository=mock_repository,
            config_service=mock_config_service,
            model_repo=mock_model_repo,
        )
        # 1回目
        result1 = mgr.get_manual_edit_model_id()
        # 2回目
        result2 = mgr.get_manual_edit_model_id()

        assert result1 == 55
        assert result2 == 55
        # session_factory は1回だけ呼ばれる (キャッシュ機能)
        mock_session_factory.assert_called_once()
        # injected method も1回だけ呼ばれる
        mock_model_repo._get_or_create_manual_edit_model.assert_called_once()


# ---------------------------------------------------------------------------
# get_images_by_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImagesByFilter:
    """get_images_by_filter メソッドのテスト"""

    def test_returns_result_on_success(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """正常系ではリポジトリの結果を返す。"""
        expected = ([{"id": 1}], 1)
        mock_repository.get_images_by_filter.return_value = expected
        result = manager.get_images_by_filter()
        assert result == expected

    def test_raises_on_repository_exception(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """リポジトリ例外が伝播する。"""
        mock_repository.get_images_by_filter.side_effect = RuntimeError("DB error")
        with pytest.raises(RuntimeError):
            manager.get_images_by_filter()


# ---------------------------------------------------------------------------
# get_image_ids_from_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageIdsFromDirectory:
    """get_image_ids_from_directory メソッドのテスト"""

    def test_returns_ids_using_provided_fsm(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """fsm が設定されているとき、それを使って画像 ID を返す。"""
        mock_fsm = Mock()
        mock_fsm.get_image_files.return_value = [Path("/data/img1.jpg"), Path("/data/img2.jpg")]
        manager_with_fsm = ImageDatabaseManager(
            repository=mock_repository,
            config_service=Mock(spec=ConfigurationService),
            fsm=mock_fsm,
        )

        with patch.object(manager_with_fsm, "detect_duplicate_image", side_effect=[1, 2]):
            result = manager_with_fsm.get_image_ids_from_directory(Path("/data"))

        assert result == [1, 2]

    def test_uses_temp_fsm_when_no_fsm(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """fsm がないとき、一時的な FileSystemManager を作成して使う。"""
        from lorairo.storage.file_system import FileSystemManager

        mock_temp_fsm = Mock(spec=FileSystemManager)
        mock_temp_fsm.get_image_files.return_value = [Path("/data/img.jpg")]

        # get_image_ids_from_directory 内の lazy import は
        # lorairo.storage.file_system.FileSystemManager を参照するため、
        # そのシンボルをパッチする
        with patch("lorairo.storage.file_system.FileSystemManager", return_value=mock_temp_fsm):
            with patch.object(manager, "detect_duplicate_image", return_value=7):
                result = manager.get_image_ids_from_directory(Path("/data"))

        assert result == [7]

    def test_skips_images_where_duplicate_not_found(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """detect_duplicate_image が None を返す画像はスキップする。"""
        mock_fsm = Mock()
        mock_fsm.get_image_files.return_value = [Path("/data/img1.jpg"), Path("/data/img2.jpg")]
        manager_with_fsm = ImageDatabaseManager(
            repository=mock_repository,
            config_service=Mock(spec=ConfigurationService),
            fsm=mock_fsm,
        )

        with patch.object(manager_with_fsm, "detect_duplicate_image", side_effect=[None, 5]):
            result = manager_with_fsm.get_image_ids_from_directory(Path("/data"))

        assert result == [5]

    def test_raises_on_os_error(self, manager: ImageDatabaseManager) -> None:
        """ディレクトリ走査の OSError は呼び出し元に伝播 (silent return しない)。"""
        from lorairo.storage.file_system import FileSystemManager

        mock_temp_fsm = Mock(spec=FileSystemManager)
        mock_temp_fsm.get_image_files.side_effect = OSError("fsm error")

        with patch("lorairo.storage.file_system.FileSystemManager", return_value=mock_temp_fsm):
            with pytest.raises(OSError, match="fsm error"):
                manager.get_image_ids_from_directory(Path("/data"))

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """detect_duplicate_image 経由の SQLAlchemyError は呼び出し元に伝播。"""
        from lorairo.storage.file_system import FileSystemManager

        mock_temp_fsm = Mock(spec=FileSystemManager)
        mock_temp_fsm.get_image_files.return_value = [Path("/data/a.jpg")]
        mock_repository.find_duplicate_image_by_phash.side_effect = SQLAlchemyError("DB error")

        with patch("lorairo.storage.file_system.FileSystemManager", return_value=mock_temp_fsm):
            with patch("lorairo.database.db_manager.calculate_phash", return_value="abc"):
                with pytest.raises(SQLAlchemyError):
                    manager.get_image_ids_from_directory(Path("/data"))


# ---------------------------------------------------------------------------
# get_annotation_status_counts
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAnnotationStatusCounts:
    """get_annotation_status_counts メソッドのテスト"""

    def test_returns_zero_counts_when_no_images(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """画像が 0 件のとき全て 0 を返す。"""
        mock_repository.get_total_image_count.return_value = 0
        result = manager.get_annotation_status_counts()
        assert result == {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}

    def test_returns_counts_when_images_exist(
        self,
        manager: ImageDatabaseManager,
        mock_repository: Mock,
        mock_error_record_repo: Mock,
    ) -> None:
        """画像が存在するとき、セッションを使ってカウントを返す。"""
        mock_repository.get_total_image_count.return_value = 10
        # ADR 0035 段階 3 (#423): error_record_repo 経由で取得される。
        mock_error_record_repo.get_error_count_unresolved.return_value = 2

        # セッションのモック
        mock_result = Mock()
        mock_result.scalar.return_value = 7
        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.get_annotation_status_counts()

        assert result["total"] == 10
        assert result["completed"] == 7
        assert result["error"] == 2
        assert result["completion_rate"] == 70.0

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        mock_repository.get_total_image_count.return_value = 5
        mock_repository.get_session.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(SQLAlchemyError):
            manager.get_annotation_status_counts()


# ---------------------------------------------------------------------------
# filter_by_annotation_status — 完了・全件パス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterByAnnotationStatusExtended:
    """filter_by_annotation_status の追加テスト"""

    def test_returns_completed_images_using_session(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """completed=True のとき、セッションで完了画像を返す。"""
        mock_row = MagicMock()
        mock_row._mapping = {"id": 1, "stored_image_path": "/s/img.jpg"}
        mock_result = Mock()
        mock_result.fetchall.return_value = [mock_row]

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.filter_by_annotation_status(completed=True)

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_returns_all_images_when_no_filter(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """completed=False, error=False のとき、全画像を返す。"""
        mock_row = MagicMock()
        mock_row._mapping = {"id": 2, "stored_image_path": "/s/img2.jpg"}
        mock_result = Mock()
        mock_result.fetchall.return_value = [mock_row]

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.filter_by_annotation_status()

        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_returns_error_images_when_error_ids_exist(
        self,
        manager: ImageDatabaseManager,
        mock_repository: Mock,
        mock_error_record_repo: Mock,
    ) -> None:
        """error=True でエラー ID が存在するとき、get_images_by_ids の結果を返す。"""
        # ADR 0035 段階 3 (#423): error_record_repo 経由で取得される。
        mock_error_record_repo.get_error_image_ids.return_value = [3, 4]
        expected = [{"id": 3}, {"id": 4}]
        mock_repository.get_images_by_ids.return_value = expected

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.filter_by_annotation_status(error=True)

        assert result == expected

    def test_returns_empty_list_when_error_mode_no_error_ids(
        self,
        manager: ImageDatabaseManager,
        mock_repository: Mock,
        mock_error_record_repo: Mock,
    ) -> None:
        """error=True でエラー ID が空のとき、空リストを返す (line 906)。"""
        # ADR 0035 段階 3 (#423): error_record_repo 経由で取得される。
        mock_error_record_repo.get_error_image_ids.return_value = []

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.filter_by_annotation_status(error=True)

        assert result == []


# ---------------------------------------------------------------------------
# get_directory_images_metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDirectoryImagesMetadata:
    """get_directory_images_metadata メソッドのテスト"""

    def test_returns_empty_list_when_no_image_ids(self, manager: ImageDatabaseManager) -> None:
        """画像 ID が取得できない場合は空リストを返す。"""
        with patch.object(manager, "get_image_ids_from_directory", return_value=[]):
            result = manager.get_directory_images_metadata(Path("/data"))
        assert result == []

    def test_returns_metadata_for_found_images(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """画像 ID からメタデータを取得して返す。"""
        mock_repository.get_image_metadata.return_value = {"id": 1, "stored_image_path": "/s/img.jpg"}

        with patch.object(manager, "get_image_ids_from_directory", return_value=[1]):
            result = manager.get_directory_images_metadata(Path("/data"))

        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_skips_images_with_no_metadata(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """get_image_metadata が None を返す画像はスキップする。"""
        mock_repository.get_image_metadata.return_value = None

        with patch.object(manager, "get_image_ids_from_directory", return_value=[1, 2]):
            result = manager.get_directory_images_metadata(Path("/data"))

        assert result == []

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        with patch.object(manager, "get_image_ids_from_directory", side_effect=SQLAlchemyError("err")):
            with pytest.raises(SQLAlchemyError):
                manager.get_directory_images_metadata(Path("/data"))

    def test_raises_on_os_error(self, manager: ImageDatabaseManager) -> None:
        """OSError は呼び出し元に伝播 (silent return しない)。"""
        with patch.object(manager, "get_image_ids_from_directory", side_effect=OSError("io")):
            with pytest.raises(OSError, match="io"):
                manager.get_directory_images_metadata(Path("/data"))


# ---------------------------------------------------------------------------
# check_processed_image_exists — 存在する場合のパス (line 995)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckProcessedImageExistsLogging:
    """check_processed_image_exists の存在確認ログパスのテスト"""

    def test_returns_metadata_dict_and_logs_when_found(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """処理済み画像が見つかったとき、辞書を返す。"""
        expected = {"id": 5, "stored_image_path": "/s/512.jpg"}
        mock_repository.get_processed_image.return_value = expected
        result = manager.check_processed_image_exists(1, 512)
        assert result == expected


# ---------------------------------------------------------------------------
# check_image_has_annotation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckImageHasAnnotation:
    """check_image_has_annotation メソッドのテスト"""

    def test_returns_true_when_annotation_exists(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """アノテーションが存在するとき True を返す。"""
        mock_result = Mock()
        mock_result.scalar.return_value = 1

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.check_image_has_annotation(1)

        assert result is True

    def test_returns_false_when_no_annotation(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """アノテーションが存在しないとき False を返す。"""
        mock_result = Mock()
        mock_result.scalar.return_value = None

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_repository.get_session.return_value = mock_session

        result = manager.check_image_has_annotation(1)

        assert result is False

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        mock_repository.get_session.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(SQLAlchemyError):
            manager.check_image_has_annotation(1)


# ---------------------------------------------------------------------------
# get_annotated_image_ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAnnotatedImageIds:
    """get_annotated_image_ids メソッドのテスト"""

    def test_delegates_to_repository(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """リポジトリに委譲してアノテーション済み ID セットを返す。"""
        mock_repository.get_annotated_image_ids.return_value = {1, 3}
        result = manager.get_annotated_image_ids([1, 2, 3])
        assert result == {1, 3}
        mock_repository.get_annotated_image_ids.assert_called_once_with([1, 2, 3])


# ---------------------------------------------------------------------------
# execute_filtered_search
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteFilteredSearch:
    """execute_filtered_search メソッドのテスト"""

    def test_returns_results_on_success(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """正常系では (images, total_count) を返す。"""
        mock_repository.get_images_by_filter.return_value = ([{"id": 1}], 1)

        result = manager.execute_filtered_search({})

        assert result[1] == 1
        assert len(result[0]) == 1

    def test_raises_on_sqlalchemy_error(self, manager: ImageDatabaseManager) -> None:
        """SQLAlchemyError は呼び出し元に伝播 (silent return しない)。"""
        with patch.object(manager, "get_images_by_filter", side_effect=SQLAlchemyError("err")):
            with pytest.raises(SQLAlchemyError):
                manager.execute_filtered_search({})


# ---------------------------------------------------------------------------
# register_original_image — project_id 付与パス (line 182)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRegisterOriginalImageProjectId:
    """register_original_image の project_id 付与パスのテスト"""

    def test_adds_project_id_to_metadata_when_available(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """_get_current_project_id が値を返すとき、metadata に project_id を付与する。"""
        mock_fsm = Mock()
        mock_fsm.get_image_info.return_value = {"width": 800, "height": 600, "has_alpha": False}
        mock_fsm.save_original_image.return_value = Path("/storage/img.jpg")
        mock_repository.find_duplicate_image_by_phash.return_value = None
        mock_repository.add_original_image.return_value = 101

        with patch("lorairo.database.db_manager.calculate_phash", return_value="abc123"):
            with patch.object(manager, "_get_current_project_id", return_value=5):
                with patch.object(manager, "_generate_thumbnail_512px"):
                    result = manager.register_original_image(Path("/data/img.jpg"), mock_fsm)

        assert result is not None
        image_id, _metadata = result
        assert image_id == 101
        # project_id が add_original_image に渡された metadata に付与されているはず
        call_args = mock_repository.add_original_image.call_args[0][0]
        assert call_args.get("project_id") == 5


# ---------------------------------------------------------------------------
# _handle_duplicate_image — 512px チェックで例外が発生するパス (lines 236-237)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleDuplicateImageCheckException:
    """_handle_duplicate_image の check_processed_image_exists 例外パスのテスト"""

    def test_logs_warning_and_continues_when_512px_check_raises(
        self, manager: ImageDatabaseManager, mock_repository: Mock
    ) -> None:
        """check_processed_image_exists が例外を送出しても処理続行し、メタデータを返す。"""
        mock_fsm = Mock()
        mock_repository.get_image_metadata.return_value = {"id": 3, "stored_image_path": "/s/o.jpg"}

        with patch.object(
            manager, "check_processed_image_exists", side_effect=RuntimeError("check failed")
        ):
            result = manager._handle_duplicate_image(3, Path("/data/img.jpg"), mock_fsm)

        assert result[0] == 3
        assert result[1] == {"id": 3, "stored_image_path": "/s/o.jpg"}


# ---------------------------------------------------------------------------
# get_batch_available_resolutions (line 995)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetBatchAvailableResolutions:
    """get_batch_available_resolutions メソッドのテスト"""

    def test_delegates_to_repository(self, manager: ImageDatabaseManager, mock_repository: Mock) -> None:
        """リポジトリに委譲して解像度マッピングを返す。"""
        expected = {1: [512], 2: [256, 512]}
        mock_repository.get_batch_available_resolutions.return_value = expected

        result = manager.get_batch_available_resolutions([1, 2])

        assert result == expected
        mock_repository.get_batch_available_resolutions.assert_called_once_with([1, 2])
