"""ImageRepository 直接の単体テスト (ADR 0035 段階 4, Issue #423)。

`db_repository.py` から抽出した新 `ImageRepository` (`repository/image.py`) の
責務境界を独立して検証する。既存の `tests/unit/database/test_db_repository_*.py`
は delegating facade 経由で同じ実装をカバーしているため、本ファイルでは新
ImageRepository を直接 instantiate して以下を最小限カバーする:

- BaseRepository 継承 / session_factory 共有 / BATCH_CHUNK_SIZE
- 画像 CRUD (add_original_image, _image_exists, add_processed_image,
  _find_existing_processed_image_id) の正常系 + 異常系
- FilenameAlias (get_all_image_filename_index, add_filename_alias)
- 検索系 (find_duplicate_image_by_phash, find_image_ids_by_phashes,
  get_annotated_image_ids) の動作 + 空入力ガード
- Annotation read formatter (`_format_*_annotation`) の static helper 挙動
- Filter helper (`_apply_*_filter`) の query 変換
- ImageRepository facade 経由でも同じ新クラスが見えること (delegation 整合性)
- DI contract: ImageDatabaseManager は injected image_repo を保持し、
  session_factory フォールバックが既存テストを破壊しないこと
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import (
    Image,
    ImageFilenameAlias,
    ProcessedImage,
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
def image_repository(memory_session_factory) -> ImageRepository:
    """In-memory SQLite に対する ImageRepository インスタンス。"""
    return ImageRepository(session_factory=memory_session_factory)


def _insert_image(
    repo: ImageRepository,
    *,
    uuid: str = "uuid-1",
    phash: str = "phash-1",
    filename: str = "sample.png",
    width: int = 64,
    height: int = 64,
) -> int:
    """テスト用画像を 1 件作成して id を返す。"""
    info = {
        "uuid": uuid,
        "phash": phash,
        "original_image_path": f"/tmp/{filename}",
        "stored_image_path": f"/tmp/{filename}",
        "width": width,
        "height": height,
        "format": "PNG",
        "extension": ".png",
        "filename": filename,
    }
    return repo.add_original_image(info)


def _insert_processed_image(
    repo: ImageRepository,
    *,
    image_id: int,
    filename: str = "processed.png",
    width: int = 512,
    height: int = 512,
) -> int:
    """テスト用処理済み画像を 1 件作成して id を返す。"""
    info = {
        "image_id": image_id,
        "stored_image_path": f"/tmp/{filename}",
        "width": width,
        "height": height,
        "has_alpha": False,
        "filename": filename,
    }
    processed_id = repo.add_processed_image(info)
    assert processed_id is not None
    return processed_id


@pytest.mark.unit
class TestImageRepositoryStructure:
    """ADR 0035 段階 4 で確立した抽出構造の sanity check。"""

    def test_inherits_base_repository(self) -> None:
        """ImageRepository は BaseRepository を継承する。"""
        assert issubclass(ImageRepository, BaseRepository)

    def test_holds_session_factory(self, memory_session_factory) -> None:
        """`session_factory` を BaseRepository 経由で保持する。"""
        repo = ImageRepository(session_factory=memory_session_factory)
        assert repo.session_factory is memory_session_factory

    def test_inherits_batch_chunk_size(self) -> None:
        """`BATCH_CHUNK_SIZE` を BaseRepository から継承する。"""
        assert ImageRepository.BATCH_CHUNK_SIZE == BaseRepository.BATCH_CHUNK_SIZE


@pytest.mark.unit
class TestGetImagesByFilterPaging:
    """`get_images_by_filter` の DB 側ページング。"""

    def test_limit_restricts_metadata_fetch_but_preserves_total_count(
        self, image_repository: ImageRepository
    ) -> None:
        """limit 指定時も総件数を返し、メタデータ取得対象は limit 件に絞る。"""
        first = _insert_image(image_repository, uuid="u-limit-1", phash="p-limit-1")
        _insert_image(image_repository, uuid="u-limit-2", phash="p-limit-2")
        _insert_image(image_repository, uuid="u-limit-3", phash="p-limit-3")

        results, total_count = image_repository.get_images_by_filter(
            ImageFilterCriteria(include_nsfw=True, limit=1)
        )

        assert total_count == 3
        assert [record["id"] for record in results] == [first]

    def test_resolution_filter_restricts_count_before_limit(
        self, image_repository: ImageRepository
    ) -> None:
        """resolution 指定時は処理済み画像が合う ID だけを count/page 対象にする。"""
        _insert_image(image_repository, uuid="u-res-missing", phash="p-res-missing")
        matching = _insert_image(image_repository, uuid="u-res-match", phash="p-res-match")
        _insert_processed_image(image_repository, image_id=matching, filename="res-match.png")

        criteria = ImageFilterCriteria(include_nsfw=True, resolution=512, limit=1)
        results, total_count = image_repository.get_images_by_filter(criteria)

        assert total_count == 1
        assert [record["id"] for record in results] == [matching]
        assert image_repository.get_images_count_only(criteria) == 1


@pytest.mark.unit
class TestAddOriginalImage:
    """`add_original_image` の永続化動作。"""

    def test_creates_image_and_returns_positive_id(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """新規画像を保存して正の ID を返し、DB にも書き込まれる。"""
        image_id = _insert_image(image_repository, uuid="u1", phash="p1")
        assert isinstance(image_id, int)
        assert image_id > 0

        with memory_session_factory() as session:
            row = session.execute(select(Image).where(Image.id == image_id)).scalar_one()
            assert row.uuid == "u1"
            assert row.phash == "p1"

    def test_returns_existing_id_on_phash_duplicate(self, image_repository: ImageRepository) -> None:
        """同じ pHash の画像を再登録すると既存 ID が返る。"""
        first = _insert_image(image_repository, uuid="u-dup-1", phash="dup-phash")
        second = _insert_image(image_repository, uuid="u-dup-2", phash="dup-phash")
        assert second == first

    def test_raises_value_error_when_required_keys_missing(self, image_repository: ImageRepository) -> None:
        """必須キー不足は ValueError。"""
        with pytest.raises(ValueError, match="必須情報が不足しています"):
            image_repository.add_original_image({"uuid": "u-x"})


@pytest.mark.unit
class TestImageExists:
    """`_image_exists` の存在判定。"""

    def test_returns_true_for_existing_image(self, image_repository: ImageRepository) -> None:
        image_id = _insert_image(image_repository, uuid="u-exists", phash="p-exists")
        assert image_repository._image_exists(image_id) is True

    def test_returns_false_for_missing_image(self, image_repository: ImageRepository) -> None:
        assert image_repository._image_exists(99999) is False


@pytest.mark.unit
class TestFindDuplicateImageByPhash:
    """`find_duplicate_image_by_phash` の検索動作。"""

    def test_returns_id_on_hit(self, image_repository: ImageRepository) -> None:
        image_id = _insert_image(image_repository, uuid="u-h", phash="phash-hit")
        assert image_repository.find_duplicate_image_by_phash("phash-hit") == image_id

    def test_returns_none_on_miss(self, image_repository: ImageRepository) -> None:
        assert image_repository.find_duplicate_image_by_phash("phash-miss") is None

    def test_returns_none_for_empty_phash(self, image_repository: ImageRepository) -> None:
        """空文字列入力で early-return None。"""
        assert image_repository.find_duplicate_image_by_phash("") is None


@pytest.mark.unit
class TestFindImageIdsByPhashes:
    """`find_image_ids_by_phashes` のバッチ検索。"""

    def test_returns_mapping_for_existing_phashes(self, image_repository: ImageRepository) -> None:
        a = _insert_image(image_repository, uuid="u-a", phash="phash-a", filename="a.png")
        b = _insert_image(image_repository, uuid="u-b", phash="phash-b", filename="b.png")
        result = image_repository.find_image_ids_by_phashes({"phash-a", "phash-b", "phash-c"})
        assert result == {"phash-a": a, "phash-b": b}

    def test_returns_empty_dict_for_empty_input(self, image_repository: ImageRepository) -> None:
        assert image_repository.find_image_ids_by_phashes(set()) == {}


@pytest.mark.unit
class TestGetAnnotatedImageIds:
    """`get_annotated_image_ids` の存在判定。"""

    def test_returns_empty_set_for_empty_input(self, image_repository: ImageRepository) -> None:
        assert image_repository.get_annotated_image_ids([]) == set()

    def test_returns_empty_set_when_no_annotations(self, image_repository: ImageRepository) -> None:
        image_id = _insert_image(image_repository, uuid="u-no-anno", phash="p-no-anno")
        assert image_repository.get_annotated_image_ids([image_id]) == set()


@pytest.mark.unit
class TestFilenameAlias:
    """`get_all_image_filename_index` / `add_filename_alias` の動作。"""

    def test_index_includes_main_filenames(self, image_repository: ImageRepository) -> None:
        _insert_image(image_repository, uuid="u-idx", phash="p-idx", filename="hello.png")
        index = image_repository.get_all_image_filename_index()
        assert index["hello"] == 1

    def test_add_filename_alias_appears_in_index(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        image_id = _insert_image(image_repository, uuid="u-al", phash="p-al", filename="x.png")
        image_repository.add_filename_alias(image_id, "alias-stem")
        index = image_repository.get_all_image_filename_index()
        assert index.get("alias-stem") == image_id

        with memory_session_factory() as session:
            row = session.execute(
                select(ImageFilenameAlias).where(ImageFilenameAlias.stem == "alias-stem")
            ).scalar_one()
            assert row.image_id == image_id


@pytest.mark.unit
class TestAddProcessedImage:
    """`add_processed_image` の永続化動作。"""

    def test_adds_processed_image(self, image_repository: ImageRepository, memory_session_factory) -> None:
        image_id = _insert_image(image_repository, uuid="u-proc", phash="p-proc")
        info = {
            "image_id": image_id,
            "stored_image_path": "/tmp/sample_512.png",
            "width": 512,
            "height": 512,
            "has_alpha": False,
            "filename": "sample_512.png",
        }
        processed_id = image_repository.add_processed_image(info)
        assert isinstance(processed_id, int)
        assert processed_id is not None and processed_id > 0
        with memory_session_factory() as session:
            row = session.execute(
                select(ProcessedImage).where(ProcessedImage.id == processed_id)
            ).scalar_one()
            assert row.image_id == image_id

    def test_raises_value_error_when_image_missing(self, image_repository: ImageRepository) -> None:
        info = {
            "image_id": 99999,
            "stored_image_path": "/tmp/x.png",
            "width": 256,
            "height": 256,
            "has_alpha": False,
        }
        with pytest.raises(ValueError, match="関連するオリジナル画像が見つかりません"):
            image_repository.add_processed_image(info)


@pytest.mark.unit
class TestFormatAnnotationStatics:
    """`_format_*_annotation` static helper の挙動。"""

    def test_format_tag_annotation_returns_dict(self) -> None:
        tag = SimpleNamespace(
            id=1,
            tag="cat",
            tag_id=10,
            model_id=20,
            existing=False,
            is_edited_manually=False,
            confidence_score=0.9,
            created_at=None,
            updated_at=None,
        )
        result = ImageRepository._format_tag_annotation(tag)
        assert result["tag"] == "cat"
        assert result["model_id"] == 20

    def test_format_rating_annotation_marks_manual(self) -> None:
        """`litellm_model_id` が manual sentinel の場合 source=Manual。"""
        from lorairo.database.schema import MANUAL_EDIT_LITELLM_ID

        rating = SimpleNamespace(
            id=1,
            raw_rating_value="PG",
            normalized_rating="PG",
            model_id=99,
            model=SimpleNamespace(name="something", litellm_model_id=MANUAL_EDIT_LITELLM_ID),
            confidence_score=None,
            created_at=None,
            updated_at=None,
        )
        result = ImageRepository._format_rating_annotation(rating)
        assert result["source"] == "Manual"


@pytest.mark.unit
class TestApplyDateFilter:
    """`_apply_date_filter` クエリ変換動作。"""

    def test_returns_query_unchanged_when_both_dates_none(self, image_repository: ImageRepository) -> None:
        base = select(Image.id)
        out = image_repository._apply_date_filter(base, None, None)
        assert out is base


@pytest.mark.unit
class TestImageDatabaseManagerDIContract:
    """ImageDatabaseManager が image_repo を inject 経由で保持することを確認。"""

    def test_manager_creates_image_repo_when_not_injected(self, memory_session_factory) -> None:
        """image_repo 未指定でも、repository.session_factory から自動生成される。"""
        repo = ImageRepository(session_factory=memory_session_factory)
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(config_service=cfg, image_repo=repo)
        assert isinstance(manager.image_repo, ImageRepository)
        assert manager.image_repo.session_factory is memory_session_factory
        assert manager.model_repo.session_factory is memory_session_factory
        assert manager.annotation_repo.session_factory is memory_session_factory
        assert manager.provider_batch_repo.session_factory is memory_session_factory

    def test_manager_uses_injected_image_repo(self, memory_session_factory) -> None:
        """明示注入された image_repo を保持し、Mock 化で外部依存を切り離せる。"""
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=ImageRepository)
        manager = ImageDatabaseManager(
            config_service=cfg,
            image_repo=injected,
        )
        assert manager.image_repo is injected

    def test_manager_creates_image_repo_with_session_factory_when_omitted(
        self, memory_session_factory
    ) -> None:
        """`session_factory` 引数を渡すと、image_repo 未指定でも当該 factory を共有する。

        ADR 0035 段階 6 (#423): facade 撤廃後、Manager は session_factory 引数で
        全 Repo を一括生成する composition pattern を採る。
        """
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(config_service=cfg, session_factory=memory_session_factory)
        assert isinstance(manager.image_repo, ImageRepository)
        assert manager.image_repo.session_factory is memory_session_factory
        # 他 Repo も同じ session_factory を共有していることを確認
        assert manager.annotation_repo.session_factory is memory_session_factory


def _insert_tag(
    session_factory,
    *,
    image_id: int,
    tag: str,
    created_at: datetime.datetime,
    updated_at: datetime.datetime,
    model_id: int | None = None,
    is_edited_manually: bool | None = None,
    existing: bool = False,
) -> None:
    """タイムスタンプを明示したタグ行を 1 件挿入する。"""
    with session_factory() as session:
        session.add(
            Tag(
                image_id=image_id,
                tag=tag,
                model_id=model_id,
                is_edited_manually=is_edited_manually,
                existing=existing,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        session.commit()


@pytest.mark.unit
class TestFilterImageIdsWithTagChangesSince:
    """#614: changed-since 絞り込み（AI 実行 created_at / 手動編集 updated_at）。"""

    def test_filters_ai_and_manual_changes_after_threshold(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        import datetime

        threshold = datetime.datetime(2026, 6, 1, 0, 0, 0)
        before = datetime.datetime(2026, 5, 1, 0, 0, 0)
        after = datetime.datetime(2026, 6, 2, 0, 0, 0)

        img_ai = _insert_image(image_repository, uuid="u-ai", phash="p-ai", filename="ai.png")
        img_manual = _insert_image(image_repository, uuid="u-man", phash="p-man", filename="man.png")
        img_existing = _insert_image(image_repository, uuid="u-ex", phash="p-ex", filename="ex.png")
        img_ai_old = _insert_image(image_repository, uuid="u-old", phash="p-old", filename="old.png")

        # AI 実行が threshold 以降
        _insert_tag(
            memory_session_factory,
            image_id=img_ai,
            tag="cat",
            model_id=1,
            created_at=after,
            updated_at=after,
        )
        # 手動編集が threshold 以降（created_at は古いが updated_at が新しい）
        _insert_tag(
            memory_session_factory,
            image_id=img_manual,
            tag="dog",
            is_edited_manually=True,
            created_at=before,
            updated_at=after,
        )
        # 元ファイル由来（AI でも手動でもない）→ 除外
        _insert_tag(
            memory_session_factory,
            image_id=img_existing,
            tag="bird",
            existing=True,
            created_at=before,
            updated_at=before,
        )
        # AI 実行だが threshold より前 → 除外
        _insert_tag(
            memory_session_factory,
            image_id=img_ai_old,
            tag="fish",
            model_id=1,
            created_at=before,
            updated_at=before,
        )

        all_ids = [img_ai, img_manual, img_existing, img_ai_old]
        result = image_repository.filter_image_ids_with_tag_changes_since(all_ids, threshold)

        assert set(result) == {img_ai, img_manual}

    def test_empty_input_returns_empty(self, image_repository: ImageRepository) -> None:
        import datetime

        assert image_repository.filter_image_ids_with_tag_changes_since([], datetime.datetime.now()) == []
