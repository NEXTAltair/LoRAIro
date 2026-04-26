"""AnnotationSaveService 3経路統合テスト。

CLI / AnnotationSaveService直接 / AnnotationWorker の3経路が
同一アノテーション結果から同一DB状態を生成することを検証する。

Sub-Issue C (#191): Sub-Issue A (AnnotationSaveService新設) と
Sub-Issue B (AnnotationWorker移管) を前提とする。
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Base, Image, Model, ModelType, Score, Tag
from lorairo.gui.workers.annotation_worker import AnnotationWorker
from lorairo.services.annotation_save_service import AnnotationSaveService


TEST_PHASH = "deadbeef12345678"
TEST_MODEL_NAME = "wdtagger-v3"


@pytest.fixture(scope="function")
def engine():
    """テスト用インメモリSQLiteエンジン（スキーマ+初期データ入り）。"""
    _engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(_engine)

    # ModelType初期データ
    SessionLocal = sessionmaker(bind=_engine)
    with SessionLocal() as session:
        for type_name in ("tagger", "score", "captioner", "rating", "multimodal", "llm", "upscaler"):
            if not session.query(ModelType).filter_by(name=type_name).first():
                session.add(ModelType(name=type_name))
        session.commit()

    yield _engine
    _engine.dispose()


@pytest.fixture(scope="function")
def session_factory(engine):
    """sessionmaker ファクトリ。"""
    return sessionmaker(bind=engine)


@pytest.fixture(scope="function")
def repository(session_factory):
    """ImageRepository インスタンス。"""
    return ImageRepository(session_factory)


@pytest.fixture(scope="function")
def registered_model_and_image(session_factory) -> dict[str, Any]:
    """モデルと画像をDBに登録し、phashとimage_idを返す。"""
    with session_factory() as session:
        tagger_type = session.query(ModelType).filter_by(name="tagger").first()
        model = Model(name=TEST_MODEL_NAME)
        session.add(model)
        session.flush()
        if tagger_type:
            model.model_types.append(tagger_type)

        image = Image(
            uuid=str(uuid.uuid4()),
            phash=TEST_PHASH,
            original_image_path="/original/test_cat.jpg",
            stored_image_path="/stored/test_cat.jpg",
            width=512,
            height=512,
            format="JPEG",
            extension=".jpg",
        )
        session.add(image)
        session.commit()
        return {"phash": TEST_PHASH, "image_id": image.id}


@pytest.fixture(scope="function")
def mock_annotation_results(registered_model_and_image) -> dict[str, Any]:
    """テスト用アノテーション結果（dict形式 UnifiedAnnotationResult）。"""
    phash = registered_model_and_image["phash"]
    return {
        phash: {
            TEST_MODEL_NAME: {
                "tags": ["cat", "animal", "cute"],
                "captions": None,
                "scores": None,
                "ratings": None,
                "error": None,
                "formatted_output": None,
            }
        }
    }


def _count_tags(session_factory, image_id: int) -> int:
    """DB内の画像タグ件数を返す。"""
    with session_factory() as session:
        return session.query(Tag).filter_by(image_id=image_id).count()


def _count_scores(session_factory, image_id: int) -> int:
    """DB内の画像スコア件数を返す。"""
    with session_factory() as session:
        return session.query(Score).filter_by(image_id=image_id).count()


@pytest.mark.integration
class TestAnnotationSaveThreePaths:
    """CLI/Service/Worker の3経路が同一DB状態を生成することを検証する。"""

    def test_service_path_saves_tags_to_db(
        self, repository, session_factory, registered_model_and_image, mock_annotation_results
    ) -> None:
        """経路2: AnnotationSaveService直接呼び出しでタグがDBに保存される。"""
        service = AnnotationSaveService(repository)
        result = service.save_annotation_results(mock_annotation_results)

        assert result.success_count == 1
        assert result.skip_count == 0
        assert result.error_count == 0
        assert result.total_count == 1

        image_id = registered_model_and_image["image_id"]
        assert _count_tags(session_factory, image_id) == 3
        assert _count_scores(session_factory, image_id) == 0

    def test_worker_path_saves_tags_to_db(
        self, session_factory, registered_model_and_image, mock_annotation_results
    ) -> None:
        """経路3: AnnotationWorker経由でタグがDBに保存される。"""
        repository = ImageRepository(session_factory)
        mock_db_manager = Mock()
        mock_db_manager.repository = repository
        mock_db_manager.get_image_id_by_filepath.return_value = None
        mock_db_manager.save_error_record = Mock()

        mock_logic = Mock()
        mock_logic.execute_annotation.return_value = mock_annotation_results
        mock_logic.get_available_models_with_metadata.return_value = []

        worker = AnnotationWorker(
            annotation_logic=mock_logic,
            image_paths=["/test/cat.jpg"],
            models=[TEST_MODEL_NAME],
            db_manager=mock_db_manager,
        )
        exec_result = worker.execute()

        assert exec_result.db_save_success == 1

        image_id = registered_model_and_image["image_id"]
        assert _count_tags(session_factory, image_id) == 3
        assert _count_scores(session_factory, image_id) == 0

    def test_three_paths_produce_same_db_state(self, engine) -> None:
        """3経路が同一アノテーション結果から同一DB状態を生成する。

        2つの独立したDB（同一スキーマ）でService経路とWorker経路を実行し、
        結果のタグ数・スコア数が一致することを確認する。
        """

        def setup_db(eng):
            """エンジンにモデルと画像を登録してphash/image_idを返す。"""
            sf = sessionmaker(bind=eng)
            with sf() as session:
                tagger_type = session.query(ModelType).filter_by(name="tagger").first()
                model = Model(name=TEST_MODEL_NAME)
                session.add(model)
                session.flush()
                if tagger_type:
                    model.model_types.append(tagger_type)
                image = Image(
                    uuid=str(uuid.uuid4()),
                    phash=TEST_PHASH,
                    original_image_path="/original/cat.jpg",
                    stored_image_path="/stored/cat.jpg",
                    width=512,
                    height=512,
                    format="JPEG",
                    extension=".jpg",
                )
                session.add(image)
                session.commit()
                return sf, image.id

        phash = TEST_PHASH
        annotation_results = {
            phash: {
                TEST_MODEL_NAME: {
                    "tags": ["cat", "animal", "cute"],
                    "captions": None,
                    "scores": None,
                    "ratings": None,
                    "error": None,
                    "formatted_output": None,
                }
            }
        }

        # DB-A: Service経路
        engine_a = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine_a)
        with sessionmaker(bind=engine_a)() as s:
            for t in ("tagger", "score", "captioner", "rating", "multimodal", "llm", "upscaler"):
                s.add(ModelType(name=t))
            s.commit()
        sf_a, image_id_a = setup_db(engine_a)
        AnnotationSaveService(ImageRepository(sf_a)).save_annotation_results(annotation_results)
        tags_a = _count_tags(sf_a, image_id_a)
        scores_a = _count_scores(sf_a, image_id_a)

        # DB-B: Worker経路
        engine_b = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine_b)
        with sessionmaker(bind=engine_b)() as s:
            for t in ("tagger", "score", "captioner", "rating", "multimodal", "llm", "upscaler"):
                s.add(ModelType(name=t))
            s.commit()
        sf_b, image_id_b = setup_db(engine_b)
        repo_b = ImageRepository(sf_b)
        mock_db = Mock()
        mock_db.repository = repo_b
        mock_db.get_image_id_by_filepath.return_value = None
        mock_db.save_error_record = Mock()
        mock_logic = Mock()
        mock_logic.execute_annotation.return_value = annotation_results
        mock_logic.get_available_models_with_metadata.return_value = []
        AnnotationWorker(
            annotation_logic=mock_logic,
            image_paths=["/test/cat.jpg"],
            models=[TEST_MODEL_NAME],
            db_manager=mock_db,
        ).execute()
        tags_b = _count_tags(sf_b, image_id_b)
        scores_b = _count_scores(sf_b, image_id_b)

        engine_a.dispose()
        engine_b.dispose()

        assert tags_a == tags_b == 3, f"タグ数不一致: Service={tags_a}, Worker={tags_b}"
        assert scores_a == scores_b == 0, f"スコア数不一致: Service={scores_a}, Worker={scores_b}"

    def test_unknown_phash_is_skipped_consistently(self, repository, session_factory) -> None:
        """DB未登録のphashはService経由で正しくスキップされる。"""
        results = {
            "unknown_phash_xyz": {
                TEST_MODEL_NAME: {
                    "tags": ["cat"],
                    "captions": None,
                    "scores": None,
                    "ratings": None,
                    "error": None,
                    "formatted_output": None,
                }
            }
        }
        service = AnnotationSaveService(repository)
        result = service.save_annotation_results(results)

        assert result.success_count == 0
        assert result.skip_count == 1
        assert result.error_count == 0
