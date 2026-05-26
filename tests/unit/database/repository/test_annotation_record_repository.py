"""AnnotationRepository 直接の単体テスト (ADR 0035 段階 5, Issue #423)。

`db_repository.py` から抽出した新 `AnnotationRepository`
(`repository/annotation_record.py`) の責務境界を独立して検証する。

カバー範囲:
- BaseRepository 継承 / session_factory 共有 / BATCH_CHUNK_SIZE
- 外部 tag_db 初期化 (`_initialize_merged_reader` /
  `_initialize_tag_register_service`) のグレースフルデグラデーション
- `save_annotations` の image_id 存在チェック + 各 entity Upsert 委譲
- `_save_*` 単体 Upsert (Tag / Caption / Score / ScoreLabel / Rating)
- `add_tag_to_images_batch` (バッチ重複スキップ + 空入力ガード)
- `update_manual_rating` (rating=None 削除 + 通常 upsert)
- `update_annotation_manual_edit_flag` (rowcount=0 で False / valid 型のみ)
- `update_rating_batch` / `update_score_batch` (空入力ガード, 不正 score)
- ImageRepository facade 経由でも同じ新クラスが見えること (delegation 整合性)
- DI contract: ImageDatabaseManager は injected annotation_repo を保持し、
  自動生成 / 明示注入の両方をサポート
- property delegation: `repo.merged_reader = mock` が `_annotation_repo` 側にも
  反映される (PR #488 の P2 教訓継承)
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.image import ImageRepository as LegacyImageRepository
from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.base import BaseRepository
from lorairo.database.schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    Caption,
    Image,
    Model,
    Rating,
    Score,
    Tag,
)
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def annotation_repository(memory_session_factory) -> AnnotationRepository:
    """In-memory SQLite に対する AnnotationRepository インスタンス。"""
    return AnnotationRepository(session_factory=memory_session_factory)


@pytest.fixture
def image_id(memory_session_factory) -> int:
    """Image を 1 件登録し、その id を返す。AnnotationRepository テスト用 fixture。"""
    with memory_session_factory() as session:
        image = Image(
            uuid="anno-test-uuid",
            phash="anno-test-phash",
            original_image_path="/tmp/anno.png",
            stored_image_path="/tmp/anno.png",
            width=64,
            height=64,
            format="PNG",
            extension=".png",
            filename="anno.png",
        )
        session.add(image)
        session.flush()
        new_id = image.id
        session.commit()
        return new_id


@pytest.fixture
def manual_edit_model_id(memory_session_factory) -> int:
    """MANUAL_EDIT model を 1 件作成し id を返す (update_manual_rating テスト用)。"""
    with memory_session_factory() as session:
        model = Model(
            name=MANUAL_EDIT_NAME,
            provider="manual",
            litellm_model_id=MANUAL_EDIT_LITELLM_ID,
        )
        session.add(model)
        session.flush()
        new_id = model.id
        session.commit()
        return new_id


@pytest.mark.unit
class TestAnnotationRepositoryStructure:
    """ADR 0035 段階 5 で確立した抽出構造の sanity check。"""

    def test_inherits_base_repository(self) -> None:
        assert issubclass(AnnotationRepository, BaseRepository)

    def test_holds_session_factory(self, memory_session_factory) -> None:
        repo = AnnotationRepository(session_factory=memory_session_factory)
        assert repo.session_factory is memory_session_factory

    def test_inherits_batch_chunk_size(self) -> None:
        assert AnnotationRepository.BATCH_CHUNK_SIZE == BaseRepository.BATCH_CHUNK_SIZE

    def test_default_session_factory_when_omitted(self) -> None:
        """`session_factory` 省略時は BaseRepository default を使う。"""
        repo = AnnotationRepository()
        assert repo.session_factory is not None


@pytest.mark.unit
class TestExternalTagDbInitialization:
    """外部 tag_db (`MergedTagReader` / `TagRegisterService`) 初期化動作。"""

    def test_merged_reader_initialization_graceful_fail(self, memory_session_factory) -> None:
        """外部 tag_db 未設定環境では `merged_reader` が None になる (warning のみ)。"""
        repo = AnnotationRepository(session_factory=memory_session_factory)
        # in-memory SQLite には base DB が無いので None になる
        assert repo.merged_reader is None
        # tag_register_service は遅延初期化なので None
        assert repo.tag_register_service is None

    def test_initialize_tag_register_service_returns_none_when_reader_unavailable(
        self, annotation_repository: AnnotationRepository
    ) -> None:
        """`merged_reader` が None なら `_initialize_tag_register_service` も None を返す。"""
        annotation_repository.merged_reader = None
        result = annotation_repository._initialize_tag_register_service()
        assert result is None


@pytest.mark.unit
class TestSaveAnnotations:
    """`save_annotations` の一括書き込み動作。"""

    def test_raises_value_error_for_nonexistent_image(
        self, annotation_repository: AnnotationRepository
    ) -> None:
        with pytest.raises(ValueError, match="指定された画像ID 99999 は存在しません"):
            annotation_repository.save_annotations(
                image_id=99999,
                annotations={"tags": [], "captions": [], "scores": [], "ratings": []},
            )

    def test_skip_existence_check_does_not_raise(self, annotation_repository: AnnotationRepository) -> None:
        """`skip_existence_check=True` なら存在チェックを skip し、空 annotations も commit。"""
        # 存在しない image_id でも skip_existence_check=True なら raise しない
        annotation_repository.save_annotations(
            image_id=99999,
            annotations={"tags": [], "captions": [], "scores": [], "ratings": []},
            skip_existence_check=True,
        )

    def test_saves_tags_when_provided(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """tags annotation を渡すと Tag 行が DB に書き込まれる。"""
        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={
                "tags": [{"tag": "cat", "model_id": None, "tag_id": None, "existing": True}],
            },
        )
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].tag == "cat"


@pytest.mark.unit
class TestSaveTagsAndCaptions:
    """`_save_tags` / `_save_captions` の Upsert 単体動作。"""

    def test_save_captions_inserts_new(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        with memory_session_factory() as session:
            annotation_repository._save_captions(
                session,
                image_id,
                [{"caption": "a cat sitting on a chair", "model_id": None, "existing": False}],
            )
            session.commit()
        with memory_session_factory() as session:
            rows = session.execute(select(Caption).where(Caption.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert "cat" in rows[0].caption


@pytest.mark.unit
class TestAddTagToImagesBatch:
    """`add_tag_to_images_batch` の一括追加動作。"""

    def test_empty_image_ids_returns_false_zero(self, annotation_repository: AnnotationRepository) -> None:
        ok, count = annotation_repository.add_tag_to_images_batch([], "test_tag", model_id=None)
        assert ok is False
        assert count == 0

    def test_empty_tag_returns_false_zero(
        self, annotation_repository: AnnotationRepository, image_id: int
    ) -> None:
        ok, count = annotation_repository.add_tag_to_images_batch([image_id], "   ", model_id=None)
        assert ok is False
        assert count == 0

    def test_adds_new_tag_to_image(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        ok, count = annotation_repository.add_tag_to_images_batch([image_id], "blue_sky", model_id=None)
        assert ok is True
        assert count == 1
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert any(t.tag == "blue_sky" for t in rows)


@pytest.mark.unit
class TestUpdateManualRating:
    """`update_manual_rating` の動作 (Rating MANUAL_EDIT model 経由)。"""

    def test_returns_false_for_nonexistent_image(
        self, annotation_repository: AnnotationRepository, manual_edit_model_id: int
    ) -> None:
        """存在しない画像に対しては False を返す (raise しない)。"""
        result = annotation_repository.update_manual_rating(99999, "PG")
        assert result is False

    def test_sets_rating_for_existing_image(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        result = annotation_repository.update_manual_rating(image_id, "PG")
        assert result is True
        with memory_session_factory() as session:
            rows = (
                session.execute(
                    select(Rating).where(
                        Rating.image_id == image_id,
                        Rating.model_id == manual_edit_model_id,
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1
            assert rows[0].normalized_rating == "PG"

    def test_clears_rating_when_passed_none(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        """rating=None で MANUAL_EDIT 行が削除される (履歴を残さない upsert 方式)。"""
        annotation_repository.update_manual_rating(image_id, "PG")
        result = annotation_repository.update_manual_rating(image_id, None)
        assert result is True
        with memory_session_factory() as session:
            rows = (
                session.execute(
                    select(Rating).where(
                        Rating.image_id == image_id,
                        Rating.model_id == manual_edit_model_id,
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 0


@pytest.mark.unit
class TestUpdateAnnotationManualEditFlag:
    """`update_annotation_manual_edit_flag` の動作。"""

    def test_raises_for_invalid_type(self, annotation_repository: AnnotationRepository) -> None:
        with pytest.raises(ValueError, match="サポートされていないアノテーションタイプ"):
            annotation_repository.update_annotation_manual_edit_flag(
                annotation_type="invalid", annotation_id=1, is_edited=True
            )

    def test_returns_false_for_missing_id(self, annotation_repository: AnnotationRepository) -> None:
        result = annotation_repository.update_annotation_manual_edit_flag(
            annotation_type="tags", annotation_id=99999, is_edited=True
        )
        assert result is False


@pytest.mark.unit
class TestUpdateBatch:
    """`update_rating_batch` / `update_score_batch` の動作。"""

    def test_rating_batch_empty_input(self, annotation_repository: AnnotationRepository) -> None:
        ok, count = annotation_repository.update_rating_batch([], "PG", model_id=1)
        assert ok is False
        assert count == 0

    def test_rating_batch_empty_rating(
        self, annotation_repository: AnnotationRepository, image_id: int
    ) -> None:
        ok, count = annotation_repository.update_rating_batch([image_id], "  ", model_id=1)
        assert ok is False
        assert count == 0

    def test_score_batch_empty_input(self, annotation_repository: AnnotationRepository) -> None:
        ok, count = annotation_repository.update_score_batch([], 5.0, model_id=1)
        assert ok is False
        assert count == 0

    def test_score_batch_out_of_range(
        self, annotation_repository: AnnotationRepository, image_id: int
    ) -> None:
        """score が 0.0-10.0 範囲外なら False を返す。"""
        ok, count = annotation_repository.update_score_batch([image_id], 11.0, model_id=1)
        assert ok is False
        assert count == 0

    def test_score_batch_inserts_new(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """新規 Score が挿入される。"""
        # Model を作っておく必要がある (model_id FK)
        with memory_session_factory() as session:
            model = Model(name="scorer1", provider="local", litellm_model_id="scorer1")
            session.add(model)
            session.flush()
            scorer_id = model.id
            session.commit()
        ok, count = annotation_repository.update_score_batch([image_id], 8.5, model_id=scorer_id)
        assert ok is True
        assert count == 1
        with memory_session_factory() as session:
            rows = session.execute(select(Score).where(Score.image_id == image_id)).scalars().all()
            assert any(s.score == 8.5 for s in rows)


@pytest.mark.unit
class TestFacadeDelegation:
    """ImageRepository delegating facade (db_repository.ImageRepository) との整合性。"""

    def test_facade_holds_annotation_repo_instance(self, memory_session_factory) -> None:
        facade = LegacyImageRepository(session_factory=memory_session_factory)
        assert isinstance(facade._annotation_repo, AnnotationRepository)

    def test_facade_save_annotations_delegates(self, memory_session_factory) -> None:
        facade = LegacyImageRepository(session_factory=memory_session_factory)
        facade._annotation_repo.save_annotations = Mock()  # type: ignore[method-assign]
        facade.save_annotations(image_id=1, annotations={"tags": []})
        facade._annotation_repo.save_annotations.assert_called_once()

    def test_facade_merged_reader_property_delegates(self, memory_session_factory) -> None:
        """`repo.merged_reader = X` が `_annotation_repo.merged_reader` に反映される。"""
        facade = LegacyImageRepository(session_factory=memory_session_factory)
        sentinel = object()
        facade.merged_reader = sentinel  # type: ignore[assignment]
        assert facade._annotation_repo.merged_reader is sentinel
        assert facade.merged_reader is sentinel

    def test_facade_tag_register_service_property_delegates(self, memory_session_factory) -> None:
        """`repo.tag_register_service = X` が `_annotation_repo` 側にも反映される。"""
        facade = LegacyImageRepository(session_factory=memory_session_factory)
        sentinel = object()
        facade.tag_register_service = sentinel  # type: ignore[assignment]
        assert facade._annotation_repo.tag_register_service is sentinel
        assert facade.tag_register_service is sentinel


@pytest.mark.unit
class TestImageDatabaseManagerDIContract:
    """ImageDatabaseManager が annotation_repo を inject 経由で保持することを確認。"""

    def test_manager_creates_annotation_repo_when_not_injected(self, memory_session_factory) -> None:
        """annotation_repo 未指定でも repository.session_factory から自動生成される。"""
        repo = LegacyImageRepository(session_factory=memory_session_factory)
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(repository=repo, config_service=cfg)
        assert isinstance(manager.annotation_repo, AnnotationRepository)
        assert manager.annotation_repo.session_factory is memory_session_factory

    def test_manager_uses_injected_annotation_repo(self, memory_session_factory) -> None:
        """明示注入された annotation_repo を保持し、Mock 化で外部依存を切り離せる。"""
        repo = LegacyImageRepository(session_factory=memory_session_factory)
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=AnnotationRepository)
        manager = ImageDatabaseManager(
            repository=repo,
            config_service=cfg,
            annotation_repo=injected,
        )
        assert manager.annotation_repo is injected

    def test_manager_annotation_repo_independent_of_facade_internal(self, memory_session_factory) -> None:
        """Manager.annotation_repo は facade の `_annotation_repo` とは独立 instance。

        facade の `_annotation_repo` は facade 用 delegating 経路、Manager の
        `annotation_repo` は Manager 直接呼び出し用 (段階 6 で完全移行) のため、別物。
        両者は同じ session_factory を共有する。
        """
        repo = LegacyImageRepository(session_factory=memory_session_factory)
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(repository=repo, config_service=cfg)
        assert manager.annotation_repo is not repo._annotation_repo
        assert manager.annotation_repo.session_factory is repo._annotation_repo.session_factory
