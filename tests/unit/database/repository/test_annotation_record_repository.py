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

import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.annotation_record import AnnotationRepository, AnnotationSaveItem
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
    """In-memory SQLite に対する AnnotationRepository インスタンス。

    ユニットテストを hermetic にするため、外部 tag_db (MergedTagReader) は既定で
    無効化する (実 HF tag DB に依存させない)。canonical 解決や lazy init を検証する
    テストは個別に `merged_reader` / `_merged_reader_initialized` を設定する。
    """
    repo = AnnotationRepository(session_factory=memory_session_factory)
    repo.merged_reader = None
    repo._merged_reader_initialized = True
    return repo


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
        """外部 tag_db reader は必要になるまで初期化されない。"""
        repo = AnnotationRepository(session_factory=memory_session_factory)
        assert repo.merged_reader is None
        assert repo._merged_reader_initialized is False
        # tag_register_service は遅延初期化なので None
        assert repo.tag_register_service is None

    def test_initialize_tag_register_service_returns_none_when_reader_unavailable(
        self, annotation_repository: AnnotationRepository
    ) -> None:
        """`merged_reader` が None なら `_initialize_tag_register_service` も None を返す。"""
        annotation_repository.merged_reader = None
        annotation_repository._merged_reader_initialized = True
        result = annotation_repository._initialize_tag_register_service()
        assert result is None

    def test_tag_resolution_initializes_external_tag_db_lazily(
        self, annotation_repository: AnnotationRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tag_id 解決が必要になった時点で外部 tag DB reader を初期化する。"""
        # fixture は reader を無効化済みなので lazy init を再アームする
        annotation_repository._merged_reader_initialized = False
        ensure_spy = Mock()
        merged_reader = Mock()
        merged_reader.search_tags_bulk.return_value = {"new tag": {"tag_id": 123, "deprecated": False}}
        monkeypatch.setattr(
            "lorairo.database.repository.annotation_record.ensure_tag_db_initialized", ensure_spy
        )
        monkeypatch.setattr(
            "lorairo.database.repository.annotation_record.get_default_reader",
            Mock(return_value=merged_reader),
        )

        result = annotation_repository.batch_resolve_tag_ids({"new tag"})

        ensure_spy.assert_called_once()
        merged_reader.search_tags_bulk.assert_called_once()
        assert result == {"new tag": 123}

    def test_public_get_merged_reader_initializes_external_tag_db_lazily(
        self, annotation_repository: AnnotationRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GUI 統合用の公開 accessor が外部 tag DB reader を初期化する。"""
        # fixture は reader を無効化済みなので lazy init を再アームする
        annotation_repository._merged_reader_initialized = False
        ensure_spy = Mock()
        merged_reader = Mock()
        monkeypatch.setattr(
            "lorairo.database.repository.annotation_record.ensure_tag_db_initialized", ensure_spy
        )
        monkeypatch.setattr(
            "lorairo.database.repository.annotation_record.get_default_reader",
            Mock(return_value=merged_reader),
        )

        result = annotation_repository.get_merged_reader()

        ensure_spy.assert_called_once()
        assert result is merged_reader
        assert annotation_repository.merged_reader is merged_reader
        assert annotation_repository._merged_reader_initialized is True


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

    def test_save_annotations_batch_commits_once_for_multiple_images(
        self,
        memory_session_factory,
    ) -> None:
        """複数画像の annotation を1 transactionで保存する。"""
        image_ids: list[int] = []
        with memory_session_factory() as session:
            for index in range(2):
                image = Image(
                    uuid=f"batch-anno-test-uuid-{index}",
                    phash=f"batch-anno-test-phash-{index}",
                    original_image_path=f"/tmp/batch-anno-{index}.png",
                    stored_image_path=f"/tmp/batch-anno-{index}.png",
                    width=64,
                    height=64,
                    format="PNG",
                    extension=".png",
                    filename=f"batch-anno-{index}.png",
                )
                session.add(image)
                session.flush()
                image_ids.append(image.id)
            session.commit()

        commit_count = 0

        def counting_session_factory():
            nonlocal commit_count
            session = memory_session_factory()
            original_commit = session.commit

            def commit() -> None:
                nonlocal commit_count
                commit_count += 1
                original_commit()

            session.commit = commit  # type: ignore[method-assign]
            return session

        repository = AnnotationRepository(session_factory=counting_session_factory)
        saved = repository.save_annotations_batch(
            [
                AnnotationSaveItem(
                    image_id=image_ids[0],
                    annotations={"tags": [{"tag": "cat", "model_id": None, "tag_id": None}]},
                ),
                AnnotationSaveItem(
                    image_id=image_ids[1],
                    annotations={"tags": [{"tag": "dog", "model_id": None, "tag_id": None}]},
                ),
            ]
        )

        assert saved == 2
        assert commit_count == 1
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id.in_(image_ids))).scalars().all()
            assert {row.tag for row in rows} == {"cat", "dog"}

    def test_save_annotations_batch_commits_per_chunk_releasing_lock(
        self,
        memory_session_factory,
    ) -> None:
        """#1158: chunk_size 指定時は chunk ごとに commit し、間で書き込みロックを解放する。

        provider-batch import が巨大単一トランザクションで >30s ロックを保持し並行 writer を
        ``database is locked`` にする回帰を防ぐ。commit 回数 = ロック解放回数なので、4 画像を
        chunk_size=2 で保存すると 2 回 commit されること (= 途中でロックが解放されること) を
        real DB で検証する。
        """
        image_ids: list[int] = []
        with memory_session_factory() as session:
            for index in range(4):
                image = Image(
                    uuid=f"chunk-anno-uuid-{index}",
                    phash=f"chunk-anno-phash-{index}",
                    original_image_path=f"/tmp/chunk-anno-{index}.png",
                    stored_image_path=f"/tmp/chunk-anno-{index}.png",
                    width=64,
                    height=64,
                    format="PNG",
                    extension=".png",
                    filename=f"chunk-anno-{index}.png",
                )
                session.add(image)
                session.flush()
                image_ids.append(image.id)
            session.commit()

        commit_count = 0

        def counting_session_factory():
            nonlocal commit_count
            session = memory_session_factory()
            original_commit = session.commit

            def commit() -> None:
                nonlocal commit_count
                commit_count += 1
                original_commit()

            session.commit = commit  # type: ignore[method-assign]
            return session

        repository = AnnotationRepository(session_factory=counting_session_factory)
        saved = repository.save_annotations_batch(
            [
                AnnotationSaveItem(
                    image_id=image_id,
                    annotations={"tags": [{"tag": f"t{image_id}", "model_id": None, "tag_id": None}]},
                )
                for image_id in image_ids
            ],
            chunk_size=2,
        )

        assert saved == 4
        # 4 画像 / chunk_size 2 = 2 コミット (単一巨大トランザクションではない)
        assert commit_count == 2
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id.in_(image_ids))).scalars().all()
            assert {row.tag for row in rows} == {f"t{i}" for i in image_ids}

    def test_save_annotations_batch_rolls_back_chunk_on_failure(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """chunk内の失敗時は同じ transaction の書き込みを rollback する。"""
        with pytest.raises(ValueError, match="指定された画像ID 99999 は存在しません"):
            annotation_repository.save_annotations_batch(
                [
                    AnnotationSaveItem(
                        image_id=image_id,
                        annotations={"tags": [{"tag": "cat", "model_id": None, "tag_id": None}]},
                    ),
                    AnnotationSaveItem(
                        image_id=99999,
                        annotations={"tags": [{"tag": "dog", "model_id": None, "tag_id": None}]},
                    ),
                ]
            )
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert rows == []

    def test_save_annotations_batch_flushes_duplicate_image_id_within_chunk(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """同一chunk内の同じ image_id は先行itemを参照して upsert する。"""
        annotation_repository.save_annotations_batch(
            [
                AnnotationSaveItem(
                    image_id=image_id,
                    annotations={"tags": [{"tag": "cat", "model_id": None, "tag_id": None}]},
                ),
                AnnotationSaveItem(
                    image_id=image_id,
                    annotations={"tags": [{"tag": "cat", "model_id": None, "tag_id": None}]},
                ),
            ]
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

    def test_save_tags_does_not_revive_rejected_row(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        rejected_at = datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC)
        with memory_session_factory() as session:
            session.add(
                Tag(
                    image_id=image_id,
                    model_id=None,
                    tag="blue_hair",
                    rejected_at=rejected_at,
                    existing=False,
                )
            )
            session.commit()

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [{"tag": "blue_hair", "model_id": None, "tag_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].rejected_at is not None

    def test_save_tags_normalizes_raw_tag_to_clean_format(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """raw なタグを保存しても DB には clean_format 整形済みが入る (ADR 0068)。"""
        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={
                "tags": [
                    {"tag": "_touhou", "model_id": None, "tag_id": None},
                    {"tag": "blue_hair_", "model_id": None, "tag_id": None},
                    {"tag": "alternate_costume", "model_id": None, "tag_id": None},
                ]
            },
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            saved = {row.tag for row in rows}
        # clean_format は `_`→空白・先頭末尾記号整理 (preferred 解決・lower 化はしない)
        assert saved == {"touhou", "blue hair", "alternate costume"}

    def test_save_tags_skips_tag_empty_after_clean_format(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """整形後に空文字になるタグはスキップする。"""
        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={
                "tags": [
                    {"tag": "___", "model_id": None, "tag_id": None},
                    {"tag": "valid_tag", "model_id": None, "tag_id": None},
                ]
            },
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            saved = {row.tag for row in rows}
        assert saved == {"valid tag"}

    def test_save_tags_dedupes_tags_colliding_after_clean_format(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """整形で同一になるタグ (`blue_hair` と `blue hair`) は Upsert で 1 行に吸収する。"""
        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={
                "tags": [
                    {"tag": "blue_hair", "model_id": None, "tag_id": None},
                    {"tag": "blue hair", "model_id": None, "tag_id": None},
                ]
            },
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tag == "blue hair"

    def test_save_tags_matches_existing_raw_row_by_normalized_key(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """既存 raw 行 (`blue_hair`) は整形後キーで突合し、整形済み値へ揃える。"""
        with memory_session_factory() as session:
            session.add(Tag(image_id=image_id, model_id=None, tag="blue_hair", existing=False))
            session.commit()

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [{"tag": "blue hair", "model_id": None, "tag_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tag == "blue hair"

    @staticmethod
    def _reader_with_canonical(mapping: dict[str, dict]) -> Mock:
        """search_tags_bulk が指定マッピングを返す mock reader を生成する。

        mapping は clean_format 済みタグ → row dict ({"tag", "tag_id", "deprecated"})。
        """
        reader = Mock()
        reader.search_tags_bulk.side_effect = lambda tags, **_: {
            tag: mapping[tag] for tag in tags if tag in mapping
        }
        return reader

    def test_save_tags_bakes_danbooru_canonical_for_ai_tags(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """ADR 0068 改訂: 非手動タグは保存時に danbooru preferred と preferred tag_id へ焼き込む。"""
        annotation_repository.merged_reader = self._reader_with_canonical(
            {"gray hair": {"tag": "grey hair", "tag_id": 42, "deprecated": False}}
        )

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [{"tag": "gray_hair", "model_id": None, "tag_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tag == "grey hair"
        assert rows[0].tag_id == 42

    def test_save_tags_preserves_manual_edited_tag(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """ADR 0068 改訂: 手動編集タグは canonical 化せず clean_format 表記を維持する。"""
        annotation_repository.merged_reader = self._reader_with_canonical(
            {"gray hair": {"tag": "grey hair", "tag_id": 42, "deprecated": False}}
        )

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={
                "tags": [{"tag": "gray_hair", "model_id": None, "tag_id": None, "is_edited_manually": True}]
            },
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        # 手動編集は canonical 化されず clean_format のまま
        assert rows[0].tag == "gray hair"

    def test_save_tags_keeps_clean_format_when_canonical_unresolved(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """canonical が解決できない非手動タグは clean_format のまま保存する。"""
        annotation_repository.merged_reader = self._reader_with_canonical({})

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [{"tag": "unknown_tag", "model_id": None, "tag_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tag == "unknown tag"

    def test_save_tags_excludes_deprecated_canonical(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        """deprecated な解決結果は採用せず clean_format を維持する。"""
        annotation_repository.merged_reader = self._reader_with_canonical(
            {"old tag": {"tag": "new tag", "tag_id": 9, "deprecated": True}}
        )

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [{"tag": "old_tag", "model_id": None, "tag_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        assert len(rows) == 1
        assert rows[0].tag == "old tag"

    def test_save_captions_does_not_revive_rejected_row(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        rejected_at = datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC)
        with memory_session_factory() as session:
            session.add(
                Caption(
                    image_id=image_id,
                    model_id=None,
                    caption="wrong caption",
                    rejected_at=rejected_at,
                    existing=False,
                )
            )
            session.commit()

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"captions": [{"caption": "wrong caption", "model_id": None}]},
        )

        with memory_session_factory() as session:
            rows = session.execute(select(Caption).where(Caption.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].rejected_at is not None


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

    def test_remove_tag_soft_rejects_without_physical_delete(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        memory_session_factory,
    ) -> None:
        annotation_repository.add_tag_to_images_batch([image_id], "blue_sky", model_id=None)

        ok, results = annotation_repository.remove_tag_from_images_batch([image_id], "blue_sky")

        assert ok is True
        assert results == [(image_id, "changed")]
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].tag == "blue_sky"
            assert rows[0].rejected_at is not None


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
class TestImageDatabaseManagerDIContract:
    """ImageDatabaseManager が annotation_repo を inject 経由で保持することを確認。"""

    def test_manager_creates_annotation_repo_when_session_factory_provided(
        self, memory_session_factory
    ) -> None:
        """`session_factory` 引数を渡すと annotation_repo が自動生成される。

        ADR 0035 段階 6 (#423): facade 撤廃後、`session_factory` を Manager に
        渡すと全 Repo がそれを共有して構築される。
        """
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(config_service=cfg, session_factory=memory_session_factory)
        assert isinstance(manager.annotation_repo, AnnotationRepository)
        assert manager.annotation_repo.session_factory is memory_session_factory

    def test_manager_uses_injected_annotation_repo(self) -> None:
        """明示注入された annotation_repo を保持し、Mock 化で外部依存を切り離せる。"""
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=AnnotationRepository)
        manager = ImageDatabaseManager(
            config_service=cfg,
            annotation_repo=injected,
        )
        assert manager.annotation_repo is injected


@pytest.mark.unit
class TestRejectReasonWritePaths:
    """soft-reject 各経路が reject_reason を正しく DB へ記録するか検証する (Issue #1003)。"""

    def _add_tag(self, memory_session_factory, image_id: int, tag: str) -> None:
        with memory_session_factory() as session:
            session.add(Tag(image_id=image_id, tag=tag, existing=False))
            session.commit()

    def _reject_reason(self, memory_session_factory, image_id: int, tag: str) -> str | None:
        with memory_session_factory() as session:
            return session.execute(
                select(Tag.reject_reason).where(Tag.image_id == image_id, Tag.tag == tag)
            ).scalar_one()

    def test_remove_batch_default_reason_incorrect(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        """remove_tag_from_images_batch は既定で reject_reason='incorrect' を記録する。"""
        self._add_tag(memory_session_factory, image_id, "bad_tag")
        ok, _ = annotation_repository.remove_tag_from_images_batch([image_id], "bad_tag")
        assert ok is True
        assert self._reject_reason(memory_session_factory, image_id, "bad_tag") == "incorrect"

    def test_remove_batch_not_needed_reason(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        """reason='not_needed' を渡すと無効化として記録される (chip 単クリック経路)。"""
        self._add_tag(memory_session_factory, image_id, "keep_tag")
        ok, _ = annotation_repository.remove_tag_from_images_batch(
            [image_id], "keep_tag", reason="not_needed"
        )
        assert ok is True
        assert self._reject_reason(memory_session_factory, image_id, "keep_tag") == "not_needed"

    def test_replace_batch_sets_replaced(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        """replace_tag_for_images_batch は置換元へ reject_reason='replaced' を記録する。"""
        self._add_tag(memory_session_factory, image_id, "old_tag")
        ok, _ = annotation_repository.replace_tag_for_images_batch([image_id], "old_tag", "new_tag")
        assert ok is True
        assert self._reject_reason(memory_session_factory, image_id, "old_tag") == "replaced"

    def test_restore_batch_clears_reason(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        """restore_tag_for_images_batch は rejected_at と reject_reason を NULL へ戻す。"""
        self._add_tag(memory_session_factory, image_id, "back_tag")
        annotation_repository.remove_tag_from_images_batch([image_id], "back_tag", reason="incorrect")
        ok, _ = annotation_repository.restore_tag_for_images_batch([image_id], "back_tag")
        assert ok is True
        assert self._reject_reason(memory_session_factory, image_id, "back_tag") is None
        with memory_session_factory() as session:
            rejected_at = session.execute(
                select(Tag.rejected_at).where(Tag.image_id == image_id, Tag.tag == "back_tag")
            ).scalar_one()
        assert rejected_at is None

    def test_get_rejected_tags_includes_reason(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        """get_rejected_tags は reject_reason を含んで返す (表示種別の再構築用)。"""
        self._add_tag(memory_session_factory, image_id, "shown_tag")
        annotation_repository.remove_tag_from_images_batch([image_id], "shown_tag", reason="not_needed")
        rejected = annotation_repository.get_rejected_tags(image_id)
        assert rejected == [
            {
                "tag": "shown_tag",
                "tag_id": None,
                "is_edited_manually": None,
                "reject_reason": "not_needed",
            }
        ]


class TestTagResaveUpsert:
    """#1065: 同一 (image, model, tag) の再付与は新規行を作らず upsert する。"""

    def _tag_payload(self, model_id: int) -> dict:
        return {"tag": "cat", "model_id": model_id, "tag_id": None, "existing": False}

    def test_resave_same_tag_same_model_does_not_add_row(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        for _ in range(3):
            annotation_repository.save_annotations(
                image_id=image_id,
                annotations={"tags": [self._tag_payload(manual_edit_model_id)]},
            )

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1

    def test_resave_bumps_updated_at(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        """再付与は「最終付与日時」として updated_at を必ず更新する (他カラム無変更でも)。"""
        from sqlalchemy import text

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [self._tag_payload(manual_edit_model_id)]},
        )
        with memory_session_factory() as session:
            session.execute(text("UPDATE tags SET updated_at = '2020-01-01 00:00:00'"))
            session.commit()

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [self._tag_payload(manual_edit_model_id)]},
        )

        with memory_session_factory() as session:
            row = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().one()
            assert str(row.updated_at) != "2020-01-01 00:00:00"

    def test_resave_preserves_soft_reject(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        """soft-reject 済みタグへの再付与は reject を維持する (ユーザー確認済みポリシー)。"""
        from sqlalchemy import text

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [self._tag_payload(manual_edit_model_id)]},
        )
        with memory_session_factory() as session:
            session.execute(
                text("UPDATE tags SET rejected_at = '2026-06-10 00:00:00', reject_reason = 'not_needed'")
            )
            session.commit()

        annotation_repository.save_annotations(
            image_id=image_id,
            annotations={"tags": [self._tag_payload(manual_edit_model_id)]},
        )

        with memory_session_factory() as session:
            row = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().one()
            assert row.rejected_at is not None
            assert row.reject_reason == "not_needed"

    def test_resave_canonical_tag_with_parentheses_is_idempotent(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        """括弧を含むタグの再付与でも clean_format の冪等性が保たれ行が増えない
        (db-schema-reviewer P2: 冪等性が崩れると UNIQUE 制約でクラッシュに変わる)。"""
        payload = {
            "tag": "hair ornament (band)",
            "model_id": manual_edit_model_id,
            "tag_id": None,
            "existing": False,
        }
        for _ in range(3):
            annotation_repository.save_annotations(image_id=image_id, annotations={"tags": [payload]})

        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1


class TestManualReAddRevivesSoftReject:
    """#1065 P1 (db-schema-reviewer 指摘): soft-reject 済みタグの手動再追加は
    UNIQUE 制約下で IntegrityError にならず、同じ行を revive する。"""

    def test_re_add_after_soft_reject_revives_row(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        from sqlalchemy import text

        # 追加 → soft-reject
        annotation_repository.add_tag_to_images_batch(
            image_ids=[image_id], tag="cat", model_id=manual_edit_model_id
        )
        with memory_session_factory() as session:
            session.execute(
                text("UPDATE tags SET rejected_at = '2026-06-10 00:00:00', reject_reason = 'not_needed'")
            )
            session.commit()

        # 同じタグを再追加: クラッシュせず revive される
        success, added = annotation_repository.add_tag_to_images_batch(
            image_ids=[image_id], tag="cat", model_id=manual_edit_model_id
        )

        assert success is True
        assert added == 1
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].rejected_at is None
            assert rows[0].reject_reason is None
            assert rows[0].is_edited_manually is True

    def test_re_add_does_not_revive_other_model_rejects(
        self,
        annotation_repository: AnnotationRepository,
        image_id: int,
        manual_edit_model_id: int,
        memory_session_factory,
    ) -> None:
        """別モデル由来の soft-reject 行は維持したまま、手動行を新規追加できる。"""
        from sqlalchemy import text

        from lorairo.database.schema import Model

        with memory_session_factory() as session:
            other = Model(name="wd-other", provider="test", litellm_model_id="test/wd-other")
            session.add(other)
            session.flush()
            other_id = other.id
            session.execute(
                text(
                    "INSERT INTO tags (image_id, model_id, tag, existing, rejected_at, reject_reason)"
                    f" VALUES ({image_id}, {other_id}, 'cat', 0, '2026-06-10 00:00:00', 'not_needed')"
                )
            )
            session.commit()

        success, added = annotation_repository.add_tag_to_images_batch(
            image_ids=[image_id], tag="cat", model_id=manual_edit_model_id
        )

        assert success is True
        assert added == 1
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
            by_model = {row.model_id: row for row in rows}
            assert len(rows) == 2
            # AI モデル行の reject はユーザー判断として維持 (Issue #1065 ポリシー)
            assert by_model[other_id].rejected_at is not None
            # 手動行は active
            assert by_model[manual_edit_model_id].rejected_at is None


@pytest.mark.unit
class TestMixedCaseStoredTagWritePaths:
    """大小混在で保存されたタグに対する remove/replace/restore の追従 (#1288)。

    保存値は canonical 解決結果や未解決タグの verbatim 保存によって大小混在しうる。
    計画側は小文字化して判定するため、更新側の完全一致比較を揃えないと
    「成功を報告するが 0 行しか更新しない」状態になる (Codex P2)。
    """

    def _add_tag(self, session_factory, image_id: int, tag: str) -> None:
        with session_factory() as session:
            session.add(Tag(image_id=image_id, tag=tag, tag_id=None, is_edited_manually=True))
            session.commit()

    def _tag_row(self, session_factory, image_id: int) -> Tag:
        with session_factory() as session:
            return session.execute(select(Tag).where(Tag.image_id == image_id)).scalar_one()

    def test_remove_soft_rejects_mixed_case_stored_tag(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        self._add_tag(memory_session_factory, image_id, "Mixed Case")

        ok, per_item = annotation_repository.remove_tag_from_images_batch([image_id], "Mixed Case")

        assert (ok, per_item) == (True, [(image_id, "changed")])
        assert self._tag_row(memory_session_factory, image_id).rejected_at is not None

    def test_restore_revives_mixed_case_stored_tag(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        self._add_tag(memory_session_factory, image_id, "Mixed Case")
        annotation_repository.remove_tag_from_images_batch([image_id], "Mixed Case")

        ok, per_item = annotation_repository.restore_tag_for_images_batch([image_id], "Mixed Case")

        assert (ok, per_item) == (True, [(image_id, "changed")])
        assert self._tag_row(memory_session_factory, image_id).rejected_at is None

    def test_replace_soft_rejects_mixed_case_source_tag(
        self, annotation_repository, memory_session_factory, image_id
    ) -> None:
        self._add_tag(memory_session_factory, image_id, "Mixed Case")

        ok, per_item = annotation_repository.replace_tag_for_images_batch(
            [image_id], "Mixed Case", "other tag"
        )

        assert (ok, per_item) == (True, [(image_id, "changed")])
        with memory_session_factory() as session:
            rows = session.execute(select(Tag).where(Tag.image_id == image_id)).scalars().all()
        by_tag = {row.tag: row for row in rows}
        assert by_tag["Mixed Case"].rejected_at is not None
        assert by_tag["other tag"].rejected_at is None
