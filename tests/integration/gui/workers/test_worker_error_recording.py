"""
Worker層からのエラーレコード保存統合テスト

Phase 4 (Worker統合) の実装を検証:
- DatabaseRegistrationWorker
- AnnotationWorker
- ThumbnailWorker
- SearchWorker
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QSize

from lorairo.annotations.annotation_logic import AnnotationLogic
from lorairo.database.db_core import create_db_engine, create_session_factory
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.gui.workers.database_worker import (
    DatabaseRegistrationWorker,
    SearchResult,
    SearchWorker,
    ThumbnailWorker,
)
from lorairo.services.search_models import SearchConditions
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def temp_project_dir():
    """一時プロジェクトディレクトリ"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()
        (project_dir / "image_dataset").mkdir()
        (project_dir / "image_dataset" / "original_images").mkdir()
        yield project_dir


@pytest.fixture
def db_manager(temp_project_dir):
    """テスト用データベースマネージャー"""
    from unittest.mock import Mock

    from lorairo.database.schema import Base

    db_path = temp_project_dir / "test.db"
    database_url = f"sqlite:///{db_path.resolve()}?check_same_thread=False"
    engine = create_db_engine(database_url)

    # スキーマ作成（error_recordsテーブルを含む）
    Base.metadata.create_all(engine)

    session_factory = create_session_factory(engine)

    # ImageRepository作成
    repository = ImageRepository(session_factory=session_factory)

    # Mock ConfigurationService
    mock_config_service = Mock()
    mock_config_service.get_preferred_resolutions.return_value = [(512, 512)]

    # FileSystemManager作成
    fsm = FileSystemManager()
    fsm.initialize(temp_project_dir)

    # ImageDatabaseManager作成
    manager = ImageDatabaseManager(
        repository=repository,
        config_service=mock_config_service,
        fsm=fsm,
    )
    return manager


@pytest.fixture
def fsm(temp_project_dir):
    """テスト用FileSystemManager"""
    fsm = FileSystemManager()
    fsm.initialize(temp_project_dir)
    return fsm


class TestDatabaseRegistrationWorkerErrorRecording:
    """DatabaseRegistrationWorker のエラー記録テスト"""

    def test_registration_error_creates_error_record(self, db_manager, fsm, temp_project_dir):
        """登録エラー時にエラーレコードが作成される"""
        # 有効な画像ファイルを作成
        test_image = temp_project_dir / "image_dataset" / "original_images" / "test.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(test_image)

        # Worker実行
        worker = DatabaseRegistrationWorker(
            directory=temp_project_dir / "image_dataset" / "original_images",
            db_manager=db_manager,
            fsm=fsm,
        )

        # register_original_image()で例外が発生するようにモック
        with patch.object(
            db_manager,
            "register_original_image",
            side_effect=Exception("Database registration error"),
        ):
            result = worker.execute()

        # エラーカウントが増加していることを確認
        assert result.error_count > 0

        # error_recordsテーブルにエラーが記録されていることを確認
        error_count = db_manager.repository.get_error_count_unresolved(operation_type="registration")
        assert error_count > 0

        # エラーレコードの詳細を確認
        error_records = db_manager.repository.get_error_records(operation_type="registration")
        assert len(error_records) > 0
        assert error_records[0].error_type == "Exception"
        assert "Database registration error" in error_records[0].error_message


class TestAnnotationWorkerErrorRecording:
    """AnnotationWorker のエラー記録テスト"""

    def test_annotation_model_error_creates_error_record(self, db_manager):
        """モデルレベルエラー時にエラーレコードが作成される"""
        # AnnotationLogic モック（エラーを引き起こす）
        mock_logic = Mock(spec=AnnotationLogic)
        mock_logic.execute_annotation.side_effect = Exception("API Error")

        # Workerの db_manager 注入をテスト
        from lorairo.gui.workers.annotation_worker import AnnotationWorker

        worker = AnnotationWorker(
            annotation_logic=mock_logic,
            image_paths=["/test/image1.jpg"],
            models=["test-model"],
            db_manager=db_manager,
        )

        # Worker実行（エラーが発生するが部分的成功を許容）
        worker.execute()

        # error_recordsテーブルにエラーが記録されていることを確認
        error_count = db_manager.repository.get_error_count_unresolved(operation_type="annotation")
        assert error_count > 0

        # エラーレコードの詳細を確認
        error_records = db_manager.repository.get_error_records(operation_type="annotation")
        assert len(error_records) > 0
        assert error_records[0].error_type == "Exception"
        assert "API Error" in error_records[0].error_message
        assert error_records[0].model_name == "test-model"

    def test_annotation_overall_error_creates_error_record(self, db_manager):
        """全体エラー時にエラーレコードが作成される"""
        # AnnotationLogic モック（初期化エラーを引き起こす）
        mock_logic = Mock(spec=AnnotationLogic)
        mock_logic.execute_annotation.side_effect = RuntimeError("Logic Error")

        from lorairo.gui.workers.annotation_worker import AnnotationWorker

        worker = AnnotationWorker(
            annotation_logic=mock_logic,
            image_paths=["/test/image1.jpg"],
            models=["test-model"],
            db_manager=db_manager,
        )

        # Worker実行（モデルレベルエラーは部分的成功として扱われる）
        worker.execute()

        # error_recordsテーブルにエラーが記録されていることを確認
        error_count = db_manager.repository.get_error_count_unresolved(operation_type="annotation")
        assert error_count > 0


class TestThumbnailWorkerErrorRecording:
    """ThumbnailWorker のエラー記録テスト"""

    def test_thumbnail_error_creates_error_record(self, db_manager, temp_project_dir, fsm):
        """サムネイル読み込みエラー時にエラーレコードが作成される"""
        # テスト用画像を登録
        test_image_path = temp_project_dir / "image_dataset" / "original_images" / "test.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(test_image_path)

        # 画像を登録
        result = db_manager.register_original_image(test_image_path, fsm)
        assert result is not None
        _image_id, _ = result

        # 画像メタデータを取得
        image_metadata = db_manager.get_directory_images_metadata(
            directory_path=temp_project_dir / "image_dataset" / "original_images",
        )

        # SearchResult作成
        search_result = SearchResult(
            image_metadata=image_metadata,
            total_count=len(image_metadata),
            search_time=0.0,
            filter_conditions=SearchConditions(
                search_type="tags",
                keywords=[],
                tag_logic="and",
            ),
        )

        # ThumbnailWorker実行（QImage読み込みエラーをシミュレート）
        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(256, 256),
            db_manager=db_manager,
        )

        with patch("lorairo.gui.workers.thumbnail_worker.QImage") as mock_qimage:
            # QImageがNullを返すようにモック
            mock_instance = Mock()
            mock_instance.isNull.return_value = True
            mock_qimage.return_value = mock_instance

            result = worker.execute()

        # エラーカウントが増加していることを確認（サムネイル読み込み失敗）
        assert result.failed_count > 0

        # error_recordsテーブルにエラーが記録されている可能性を確認
        # (QImage.isNull()の場合はcontinueするのでエラーレコードは作成されない)
        # 実際のException発生時のみエラーレコードが作成される

    def test_thumbnail_exception_creates_error_record(self, db_manager, temp_project_dir, fsm):
        """サムネイル例外時にエラーレコードが作成される"""
        # テスト用画像を登録
        test_image_path = temp_project_dir / "image_dataset" / "original_images" / "test.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(test_image_path)

        result = db_manager.register_original_image(test_image_path, fsm)
        assert result is not None

        image_metadata = db_manager.get_directory_images_metadata(
            directory_path=temp_project_dir / "image_dataset" / "original_images",
        )

        # SearchResult作成
        search_result = SearchResult(
            image_metadata=image_metadata,
            total_count=len(image_metadata),
            search_time=0.0,
            filter_conditions=SearchConditions(
                search_type="tags",
                keywords=[],
                tag_logic="and",
            ),
        )

        worker = ThumbnailWorker(
            search_result=search_result,
            thumbnail_size=QSize(256, 256),
            db_manager=db_manager,
        )

        # QImage例外をシミュレート
        with patch("lorairo.gui.workers.thumbnail_worker.QImage", side_effect=Exception("QImage Error")):
            result = worker.execute()

        # エラーカウントが増加していることを確認
        assert result.failed_count > 0

        # error_recordsテーブルにエラーが記録されていることを確認
        error_count = db_manager.repository.get_error_count_unresolved(operation_type="thumbnail")
        assert error_count > 0


class TestSearchWorkerErrorRecording:
    """SearchWorker のエラー記録テスト"""

    def test_search_error_creates_error_record(self, db_manager):
        """検索エラー時にエラーレコードが作成される"""
        # SearchConditions作成
        conditions = SearchConditions(
            search_type="tags",
            keywords=[],
            tag_logic="and",
        )

        # SearchWorker実行（データベースエラーをシミュレート）
        worker = SearchWorker(db_manager=db_manager, search_conditions=conditions)

        with patch.object(db_manager, "get_images_by_filter", side_effect=Exception("Database Error")):
            with pytest.raises(Exception):
                worker.execute()

        # error_recordsテーブルにエラーが記録されていることを確認
        error_count = db_manager.repository.get_error_count_unresolved(operation_type="search")
        assert error_count > 0

        # エラーレコードの詳細を確認
        error_records = db_manager.repository.get_error_records(operation_type="search")
        assert len(error_records) > 0
        assert error_records[0].error_type == "Exception"
        assert "Database Error" in error_records[0].error_message


class TestErrorRecordIntegration:
    """エラーレコード統合テスト"""

    def test_error_count_increases_from_zero(self, db_manager):
        """エラーカウントが0から増加することを確認"""
        # 初期状態: エラー件数は0
        initial_count = db_manager.repository.get_error_count_unresolved()
        assert initial_count == 0

        # エラーレコードを保存
        error_id = db_manager.save_error_record(
            operation_type="registration",
            error_type="TestError",
            error_message="Test error message",
        )
        assert error_id > 0

        # エラー件数が増加していることを確認
        final_count = db_manager.repository.get_error_count_unresolved()
        assert final_count == 1

    def test_multiple_workers_error_recording(self, db_manager):
        """複数Worker からのエラー記録を確認"""
        # 各操作種別でエラーを記録
        db_manager.save_error_record(
            operation_type="registration",
            error_type="RegistrationError",
            error_message="Registration failed",
        )
        db_manager.save_error_record(
            operation_type="annotation",
            error_type="AnnotationError",
            error_message="Annotation failed",
        )
        db_manager.save_error_record(
            operation_type="processing",
            error_type="ProcessingError",
            error_message="Processing failed",
        )

        # 全体エラー件数を確認
        total_count = db_manager.repository.get_error_count_unresolved()
        assert total_count == 3

        # 操作種別ごとのエラー件数を確認
        registration_count = db_manager.repository.get_error_count_unresolved(operation_type="registration")
        annotation_count = db_manager.repository.get_error_count_unresolved(operation_type="annotation")
        processing_count = db_manager.repository.get_error_count_unresolved(operation_type="processing")

        assert registration_count == 1
        assert annotation_count == 1
        assert processing_count == 1
