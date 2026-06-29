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
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import (
    Caption,
    Image,
    ImageFilenameAlias,
    ProcessedImage,
    Rating,
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
    has_alpha: bool = False,
    is_grayscale_like: bool = False,
) -> int:
    """テスト用画像を 1 件作成して id を返す (was_inserted は捨てる)。"""
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
        "has_alpha": has_alpha,
        "is_grayscale_like": is_grayscale_like,
    }
    image_id, _was_inserted = repo.add_original_image(info)
    return image_id


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
class TestPhashCandidateClassification:
    """`find_phash_candidates` + `classify_phash_candidate` の重複/別版/新規分類 (ADR 0061)。"""

    def test_find_candidates_returns_attrs(self, image_repository: ImageRepository) -> None:
        """同一 pHash の候補を分類用属性付きで返す。"""
        image_id = _insert_image(
            image_repository, uuid="u-c1", phash="p-cand", width=800, height=600, has_alpha=True
        )
        candidates = image_repository.find_phash_candidates("p-cand")
        assert len(candidates) == 1
        assert candidates[0]["id"] == image_id
        assert candidates[0]["width"] == 800
        assert candidates[0]["height"] == 600
        assert candidates[0]["has_alpha"] is True

    def test_find_candidates_returns_all_rows_for_same_phash(
        self, image_repository: ImageRepository
    ) -> None:
        """同一 pHash の別版が複数あれば全件返す (limit(1) しない)。"""
        first = _insert_image(image_repository, uuid="u-m1", phash="p-multi", is_grayscale_like=False)
        # 属性が異なれば別版として新規行になる (classification-aware guard)
        second = _insert_image(image_repository, uuid="u-m2", phash="p-multi", is_grayscale_like=True)
        candidates = image_repository.find_phash_candidates("p-multi")
        assert {c["id"] for c in candidates} == {first, second}

    def test_find_candidates_empty_for_missing(self, image_repository: ImageRepository) -> None:
        assert image_repository.find_phash_candidates("p-none") == []

    def test_find_candidates_empty_for_blank_phash(self, image_repository: ImageRepository) -> None:
        assert image_repository.find_phash_candidates("") == []

    def test_classify_new_when_no_candidates(self) -> None:
        """候補が無ければ NEW。"""
        from lorairo.database.repository.image import PhashClassification

        result = ImageRepository.classify_phash_candidate({"width": 1, "height": 1}, [])
        assert result == (PhashClassification.NEW, None)

    def test_classify_duplicate_when_all_attrs_match(self) -> None:
        """全分類属性が一致する候補があれば DUPLICATE + 既存 ID。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        candidates = [{"id": 42, **new_attrs}]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.DUPLICATE,
            42,
        )

    def test_classify_variant_when_grayscale_differs(self) -> None:
        """is_grayscale_like だけ異なる候補のみなら VARIANT。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        candidates = [
            {"id": 42, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": True}
        ]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.VARIANT,
            None,
        )

    def test_classify_variant_when_size_differs(self) -> None:
        """解像度違いは VARIANT。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 1024, "height": 768, "has_alpha": False, "is_grayscale_like": False}
        candidates = [
            {"id": 7, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        ]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.VARIANT,
            None,
        )

    def test_classify_variant_when_alpha_differs(self) -> None:
        """アルファ有無の違いは VARIANT。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 800, "height": 600, "has_alpha": True, "is_grayscale_like": False}
        candidates = [
            {"id": 9, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        ]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.VARIANT,
            None,
        )

    def test_classify_duplicate_when_one_of_many_matches(self) -> None:
        """複数候補のうち 1 件でも全属性一致すれば DUPLICATE。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        candidates = [
            {"id": 1, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": True},
            {"id": 2, **new_attrs},
        ]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.DUPLICATE,
            2,
        )

    def test_classify_duplicate_when_candidate_grayscale_is_null(self) -> None:
        """候補の is_grayscale_like が NULL (未判定) なら一致扱いで DUPLICATE (ADR 0061 §6)。

        #631 以前に登録された行は is_grayscale_like=NULL のまま残る。完全な再
        インポートを別版に誤分類して重複スキップを失わせないため、NULL は不明として
        一致扱いにする。
        """
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": False}
        # 既存行は grayscale 判定が未実施 (NULL)
        candidates = [{"id": 3, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": None}]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.DUPLICATE,
            3,
        )

    def test_classify_variant_even_if_grayscale_null_when_size_differs(self) -> None:
        """NULL は grayscale 軸のみ寛容にし、サイズ等の明確な差は別版のまま。"""
        from lorairo.database.repository.image import PhashClassification

        new_attrs = {"width": 1024, "height": 768, "has_alpha": False, "is_grayscale_like": False}
        candidates = [{"id": 4, "width": 800, "height": 600, "has_alpha": False, "is_grayscale_like": None}]
        assert ImageRepository.classify_phash_candidate(new_attrs, candidates) == (
            PhashClassification.VARIANT,
            None,
        )


@pytest.mark.unit
class TestAddOriginalImageVariant:
    """`add_original_image` の classification-aware 別版登録 / dedup (ADR 0061)。"""

    def test_inserts_new_row_for_same_phash_variant(self, image_repository: ImageRepository) -> None:
        """同一 pHash でも属性差があれば別版として新規行を作る。"""
        first = _insert_image(image_repository, uuid="u-v1", phash="p-var", is_grayscale_like=False)
        second = _insert_image(image_repository, uuid="u-v2", phash="p-var", is_grayscale_like=True)
        assert second != first
        assert len(image_repository.find_phash_candidates("p-var")) == 2

    def test_returns_was_inserted_flag(self, image_repository: ImageRepository) -> None:
        """新規挿入時 was_inserted=True、重複確定時 was_inserted=False を返す。"""
        info_a = {
            "uuid": "u-w1",
            "phash": "p-wi",
            "original_image_path": "/tmp/a.png",
            "stored_image_path": "/tmp/a.png",
            "width": 64,
            "height": 64,
            "format": "PNG",
            "extension": ".png",
            "has_alpha": False,
            "is_grayscale_like": False,
        }
        first_id, was_inserted_a = image_repository.add_original_image(info_a)
        assert was_inserted_a is True
        # 全属性一致の再登録 → 重複確定、挿入されない
        info_b = {**info_a, "uuid": "u-w2"}
        second_id, was_inserted_b = image_repository.add_original_image(info_b)
        assert was_inserted_b is False
        assert second_id == first_id

    def test_dedup_identical_variants_in_sequence(self, image_repository: ImageRepository) -> None:
        """同一属性の別版を 2 連続登録すると 2 回目は重複確定で既存 ID を返す。

        並行レースで両者が VARIANT 分類されても、挿入直前ガードが先行行を候補として
        拾い直すため、同一属性は 1 行に収束する (PR #647 review P2)。
        """
        # 先行のカラー版
        _insert_image(image_repository, uuid="u-i0", phash="p-id", is_grayscale_like=False)
        # グレー別版を 2 回登録
        gray1 = _insert_image(image_repository, uuid="u-i1", phash="p-id", is_grayscale_like=True)
        gray2 = _insert_image(image_repository, uuid="u-i2", phash="p-id", is_grayscale_like=True)
        assert gray2 == gray1
        # カラー 1 + グレー 1 = 2 行
        assert len(image_repository.find_phash_candidates("p-id")) == 2

    def test_internal_guard_returns_existing_on_true_duplicate(
        self, image_repository: ImageRepository
    ) -> None:
        """全属性一致なら内部ガードは既存 ID を返す (重複確定)。"""
        first = _insert_image(image_repository, uuid="u-d1", phash="p-dupe", is_grayscale_like=False)
        second = _insert_image(image_repository, uuid="u-d2", phash="p-dupe", is_grayscale_like=False)
        assert second == first
        assert len(image_repository.find_phash_candidates("p-dupe")) == 1


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
class TestFindImageIdsByPhashesMulti:
    """`find_image_ids_by_phashes_multi` の fan-out バッチ検索 (#633)。"""

    def test_returns_all_image_ids_for_shared_phash(self, image_repository: ImageRepository) -> None:
        """同一 pHash の別版 (複数行) を全て取りこぼさず返す。"""
        # 同一 pHash・属性差で別版を 2 行作る (#630 が別版行を許容)
        v1 = _insert_image(image_repository, uuid="u-v1", phash="p-shared", filename="v1.png", width=64)
        v2 = _insert_image(image_repository, uuid="u-v2", phash="p-shared", filename="v2.png", width=128)
        single = _insert_image(image_repository, uuid="u-s", phash="p-single", filename="s.png")

        result = image_repository.find_image_ids_by_phashes_multi({"p-shared", "p-single"})

        assert result["p-shared"] == sorted([v1, v2])
        assert result["p-single"] == [single]

    def test_omits_missing_phashes(self, image_repository: ImageRepository) -> None:
        a = _insert_image(image_repository, uuid="u-m", phash="p-present", filename="m.png")
        result = image_repository.find_image_ids_by_phashes_multi({"p-present", "p-absent"})
        assert result == {"p-present": [a]}

    def test_returns_empty_dict_for_empty_input(self, image_repository: ImageRepository) -> None:
        assert image_repository.find_image_ids_by_phashes_multi(set()) == {}


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
            rejected_at=None,
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


@pytest.mark.unit
class TestGetImageAnnotationsSoftReject:
    """Tag/Caption soft-reject の採用ビューを検証する。"""

    def test_excludes_rejected_tags_and_captions_by_default(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        image_id = _insert_image(
            image_repository,
            uuid="soft-reject-default",
            phash="soft-reject-default",
            filename="soft-reject-default.png",
        )
        rejected_at = datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC)
        with memory_session_factory() as session:
            session.add_all(
                [
                    Tag(image_id=image_id, tag="black_hair", rejected_at=None),
                    Tag(image_id=image_id, tag="blue_hair", rejected_at=rejected_at),
                    Caption(image_id=image_id, caption="adopted caption", rejected_at=None),
                    Caption(image_id=image_id, caption="rejected caption", rejected_at=rejected_at),
                ]
            )
            session.commit()

        annotations = image_repository.get_image_annotations(image_id)

        assert [tag["tag"] for tag in annotations["tags"]] == ["black_hair"]
        assert [caption["caption"] for caption in annotations["captions"]] == ["adopted caption"]

    def test_can_include_rejected_tags_and_captions_explicitly(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        image_id = _insert_image(
            image_repository,
            uuid="soft-reject-history",
            phash="soft-reject-history",
            filename="soft-reject-history.png",
        )
        rejected_at = datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC)
        with memory_session_factory() as session:
            session.add_all(
                [
                    Tag(image_id=image_id, tag="black_hair", rejected_at=None),
                    Tag(image_id=image_id, tag="blue_hair", rejected_at=rejected_at),
                    Caption(image_id=image_id, caption="adopted caption", rejected_at=None),
                    Caption(image_id=image_id, caption="rejected caption", rejected_at=rejected_at),
                ]
            )
            session.commit()

        annotations = image_repository.get_image_annotations(image_id, include_rejected=True)

        assert {tag["tag"] for tag in annotations["tags"]} == {"black_hair", "blue_hair"}
        assert {caption["caption"] for caption in annotations["captions"]} == {
            "adopted caption",
            "rejected caption",
        }

    def test_get_annotated_image_ids_ignores_rejected_only_annotations(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        image_id = _insert_image(
            image_repository,
            uuid="soft-reject-annotated",
            phash="soft-reject-annotated",
            filename="soft-reject-annotated.png",
        )
        with memory_session_factory() as session:
            session.add(
                Tag(
                    image_id=image_id,
                    tag="blue_hair",
                    rejected_at=datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC),
                )
            )
            session.commit()

        assert image_repository.get_annotated_image_ids([image_id]) == set()


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
        img_ai_rerun = _insert_image(image_repository, uuid="u-re", phash="p-re", filename="re.png")

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
        # AI 再実行: 既存行を update（created_at は古いが updated_at が新しい）→ 含む (Codex #621)
        _insert_tag(
            memory_session_factory,
            image_id=img_ai_rerun,
            tag="cat",
            model_id=1,
            created_at=before,
            updated_at=after,
        )

        all_ids = [img_ai, img_manual, img_existing, img_ai_old, img_ai_rerun]
        result = image_repository.filter_image_ids_with_tag_changes_since(all_ids, threshold)

        assert set(result) == {img_ai, img_manual, img_ai_rerun}

    def test_empty_input_returns_empty(self, image_repository: ImageRepository) -> None:
        import datetime

        assert image_repository.filter_image_ids_with_tag_changes_since([], datetime.datetime.now()) == []


@pytest.mark.unit
class TestImageFilterCriteriaExactSet:
    """ADR 0055: image_ids 指定時は他フィルタを bypass する exact-set selector。"""

    def test_image_ids_bypass_tag_filter_and_drop_missing(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        img_cat = _insert_image(image_repository, uuid="u-c", phash="p-c", filename="c.png")
        img_plain = _insert_image(image_repository, uuid="u-p", phash="p-p", filename="p.png")
        _insert_tag(
            memory_session_factory,
            image_id=img_cat,
            tag="cat",
            model_id=1,
            created_at=datetime.datetime(2026, 1, 1),
            updated_at=datetime.datetime(2026, 1, 1),
        )

        # 通常フィルタ (tags=["cat"]) は cat タグ画像のみ
        normal, _ = image_repository.get_images_by_filter(ImageFilterCriteria(tags=["cat"]))
        assert {m["id"] for m in normal} == {img_cat}

        # image_ids 指定時は tags フィルタを bypass し両方返す。存在しない ID は除外。
        exact, count = image_repository.get_images_by_filter(
            ImageFilterCriteria(image_ids=[img_cat, img_plain, 999999], tags=["cat"])
        )
        ids = {m["id"] for m in exact}
        assert ids == {img_cat, img_plain}
        assert count == 2

    def test_tag_filter_ignores_rejected_tags(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        img_adopted = _insert_image(image_repository, uuid="u-adopt", phash="p-adopt", filename="a.png")
        img_rejected = _insert_image(image_repository, uuid="u-reject", phash="p-reject", filename="r.png")
        with memory_session_factory() as session:
            session.add_all(
                [
                    Tag(image_id=img_adopted, tag="cat", rejected_at=None),
                    Tag(
                        image_id=img_rejected,
                        tag="cat",
                        rejected_at=datetime.datetime(2026, 6, 11, tzinfo=datetime.UTC),
                    ),
                ]
            )
            session.commit()

        rows, count = image_repository.get_images_by_filter(ImageFilterCriteria(tags=["cat"]))

        assert {row["id"] for row in rows} == {img_adopted}
        assert count == 1

    def test_image_ids_bypass_nsfw_exclusion(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """明示ステージングした NSFW 画像が include_nsfw=False でも落ちない (Codex/ADR 0055)。"""
        img_nsfw = _insert_image(image_repository, uuid="u-n", phash="p-n", filename="n.png")
        with memory_session_factory() as session:
            session.add(
                Rating(
                    image_id=img_nsfw,
                    model_id=1,
                    raw_rating_value="X",
                    normalized_rating="X",
                )
            )
            session.commit()

        # 通常フィルタ (include_nsfw=False) は NSFW 画像を除外する (control)
        normal, _ = image_repository.get_images_by_filter(ImageFilterCriteria(include_nsfw=False))
        assert img_nsfw not in {m["id"] for m in normal}

        # image_ids exact-set は include_nsfw=False でも NSFW 画像を返す
        exact, count = image_repository.get_images_by_filter(
            ImageFilterCriteria(image_ids=[img_nsfw], include_nsfw=False)
        )
        assert {m["id"] for m in exact} == {img_nsfw}
        assert count == 1

    def test_image_ids_in_to_dict(self) -> None:
        assert ImageFilterCriteria(image_ids=[1, 2]).to_dict()["image_ids"] == [1, 2]

    def test_count_only_honors_image_ids(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """get_images_count_only も image_ids exact-set を尊重する (Codex #623)。"""
        img_cat = _insert_image(image_repository, uuid="u-c2", phash="p-c2", filename="c2.png")
        img_plain = _insert_image(image_repository, uuid="u-p2", phash="p-p2", filename="p2.png")
        _insert_tag(
            memory_session_factory,
            image_id=img_cat,
            tag="cat",
            model_id=1,
            created_at=datetime.datetime(2026, 1, 1),
            updated_at=datetime.datetime(2026, 1, 1),
        )
        # tags フィルタは無視され、指定した存在 ID の件数を返す
        count = image_repository.get_images_count_only(
            ImageFilterCriteria(image_ids=[img_cat, img_plain, 999999], tags=["cat"])
        )
        assert count == 2

    def test_image_ids_respect_limit_and_offset(self, image_repository: ImageRepository) -> None:
        """exact-set でも limit / offset のページングが効く (Codex #623)。"""
        ids = [
            _insert_image(image_repository, uuid=f"u-{n}", phash=f"p-{n}", filename=f"{n}.png")
            for n in range(5)
        ]
        rows, total = image_repository.get_images_by_filter(
            ImageFilterCriteria(image_ids=ids, limit=2, offset=1)
        )
        assert total == 5  # 総件数はページング前
        assert len(rows) == 2  # limit 適用
        assert [m["id"] for m in rows] == ids[1:3]  # offset=1 から 2 件

    def test_image_ids_apply_resolution_before_paging(self, image_repository: ImageRepository) -> None:
        """resolution 指定時は解像度フィルタをページングより前に適用する (Codex #623)。"""
        img_missing = _insert_image(image_repository, uuid="u-rm", phash="p-rm", filename="rm.png")
        img_has = _insert_image(image_repository, uuid="u-rh", phash="p-rh", filename="rh.png")
        _insert_processed_image(image_repository, image_id=img_has, filename="rh-512.png")

        # img_missing は 512px の処理済み版なし。limit=1 でも空ページにならず has を返す。
        rows, total = image_repository.get_images_by_filter(
            ImageFilterCriteria(image_ids=[img_missing, img_has], resolution=512, limit=1)
        )
        assert total == 1  # 解像度該当は has のみ
        assert [m["id"] for m in rows] == [img_has]

    def test_image_ids_preserve_caller_order(self, image_repository: ImageRepository) -> None:
        """呼び出し元の明示順 (ステージング順) を保持する (Codex #623)。"""
        first = _insert_image(image_repository, uuid="u-o1", phash="p-o1", filename="o1.png")
        second = _insert_image(image_repository, uuid="u-o2", phash="p-o2", filename="o2.png")
        third = _insert_image(image_repository, uuid="u-o3", phash="p-o3", filename="o3.png")
        # DB id 昇順ではなく caller の順 [third, first, second] を維持する
        rows, _ = image_repository.get_images_by_filter(
            ImageFilterCriteria(image_ids=[third, first, second])
        )
        assert [m["id"] for m in rows] == [third, first, second]

    def test_count_only_matches_filter_total_with_resolution(
        self, image_repository: ImageRepository
    ) -> None:
        """count_only も resolution 該当のみを数え、get_images_by_filter と一致する (Codex #623)。"""
        img_missing = _insert_image(image_repository, uuid="u-cm", phash="p-cm", filename="cm.png")
        img_has = _insert_image(image_repository, uuid="u-ch", phash="p-ch", filename="ch.png")
        _insert_processed_image(image_repository, image_id=img_has, filename="ch-512.png")

        criteria = ImageFilterCriteria(image_ids=[img_missing, img_has], resolution=512)
        _, total = image_repository.get_images_by_filter(criteria)
        assert image_repository.get_images_count_only(criteria) == total == 1

    def test_image_ids_over_limit_raises(self, image_repository: ImageRepository) -> None:
        """EXACT_SET_MAX_IDS 超過は曖昧な SQLite 例外でなく ValueError で弾く (ADR 0056)。"""
        too_many = list(range(1, image_repository.EXACT_SET_MAX_IDS + 2))  # 501 unique
        with pytest.raises(ValueError, match="exact-set"):
            image_repository.get_images_by_filter(ImageFilterCriteria(image_ids=too_many))

    def test_image_ids_at_limit_does_not_raise(self, image_repository: ImageRepository) -> None:
        """境界: ちょうど上限の件数は raise しない (存在しないので空集合, ADR 0056)。"""
        at_limit = list(range(1, image_repository.EXACT_SET_MAX_IDS + 1))  # 500 unique
        rows, total = image_repository.get_images_by_filter(ImageFilterCriteria(image_ids=at_limit))
        assert rows == []
        assert total == 0

    def test_count_only_inherits_exact_set_guard(self, image_repository: ImageRepository) -> None:
        """count_only も共有 helper 経由で同じガードを継承する (ADR 0056)。"""
        too_many = list(range(1, image_repository.EXACT_SET_MAX_IDS + 2))
        with pytest.raises(ValueError, match="exact-set"):
            image_repository.get_images_count_only(ImageFilterCriteria(image_ids=too_many))


class TestGetImagesByIdsChunking:
    """get_images_by_ids は非有界な error 復旧集合を chunk 分割する (ADR 0056改訂 / Codex #625)。"""

    def test_chunks_over_bind_limit_returns_all(
        self, image_repository: ImageRepository, monkeypatch
    ) -> None:
        """BATCH_CHUNK_SIZE をまたぐ id list を reject せず全件返す。"""
        ids = [
            _insert_image(image_repository, uuid=f"u-bi{n}", phash=f"p-bi{n}", filename=f"bi{n}.png")
            for n in range(5)
        ]
        # chunk 境界を小さくして分割経路を踏ませる (5 ids → 3 chunks)。
        # instance 属性で ClassVar を shadow するため他テストに影響しない。
        monkeypatch.setattr(image_repository, "BATCH_CHUNK_SIZE", 2)
        rows = image_repository.get_images_by_ids(ids)
        assert {m["id"] for m in rows} == set(ids)


@pytest.mark.unit
class TestSetImageReviewed:
    """set_image_reviewed (Wireframes v11 Frame 5 accept 永続化) のテスト。"""

    def test_accept_sets_reviewed_at(self, image_repository: ImageRepository) -> None:
        """accept で reviewed_at に値が入り、metadata に反映される。"""
        image_id = _insert_image(image_repository, uuid="rev-1", phash="rev-ph-1")
        assert image_repository.set_image_reviewed(image_id, reviewed=True) is True
        metadata = image_repository.get_image_metadata(image_id)
        assert metadata is not None
        assert metadata["reviewed_at"] is not None

    def test_undo_clears_reviewed_at(self, image_repository: ImageRepository) -> None:
        """undo で reviewed_at が NULL に戻る。"""
        image_id = _insert_image(image_repository, uuid="rev-2", phash="rev-ph-2")
        image_repository.set_image_reviewed(image_id, reviewed=True)
        assert image_repository.set_image_reviewed(image_id, reviewed=False) is True
        metadata = image_repository.get_image_metadata(image_id)
        assert metadata is not None
        assert metadata["reviewed_at"] is None

    def test_missing_image_returns_false(self, image_repository: ImageRepository) -> None:
        """未登録 image_id では False を返す。"""
        assert image_repository.set_image_reviewed(99999, reviewed=True) is False


@pytest.mark.unit
class TestLazyAnnotationLoading:
    """Issue #965: 検索フェーズのアノテーション省略 + 遅延取得。"""

    def test_filter_includes_annotations_by_default(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """include_annotations 未指定 (=True) では従来通りアノテーションを含む。"""
        image_id = _insert_image(image_repository, uuid="anno-on", phash="anno-on")
        with memory_session_factory() as session:
            session.add(Tag(image_id=image_id, tag="cat", rejected_at=None))
            session.commit()

        results, _ = image_repository.get_images_by_filter(ImageFilterCriteria(include_nsfw=True))

        assert len(results) == 1
        assert results[0]["tags_text"] == "cat"
        assert [t["tag"] for t in results[0]["tags"]] == ["cat"]

    def test_filter_excludes_annotations_when_disabled(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """include_annotations=False では id/カラムのみで、アノテーションキーを含まない。"""
        image_id = _insert_image(image_repository, uuid="anno-off", phash="anno-off")
        with memory_session_factory() as session:
            session.add(Tag(image_id=image_id, tag="cat", rejected_at=None))
            session.commit()

        results, total = image_repository.get_images_by_filter(
            ImageFilterCriteria(include_nsfw=True, include_annotations=False)
        )

        assert total == 1
        assert len(results) == 1
        record = results[0]
        # サムネ/プレビューに必要な最小カラムは残る
        assert record["id"] == image_id
        assert record["stored_image_path"]
        # アノテーション関連キーは一切含まれない
        for key in ("tags", "tags_text", "captions", "caption_text", "scores", "quality_summary"):
            assert key not in record

    def test_get_image_annotation_metadata_returns_formatted_annotations(
        self, image_repository: ImageRepository, memory_session_factory
    ) -> None:
        """単一画像のアノテーションを表示用フォーマットで遅延取得できる。"""
        image_id = _insert_image(image_repository, uuid="lazy-1", phash="lazy-1")
        with memory_session_factory() as session:
            session.add_all(
                [
                    Tag(image_id=image_id, tag="cat", rejected_at=None),
                    Caption(image_id=image_id, caption="a cat", rejected_at=None),
                ]
            )
            session.commit()

        annotations = image_repository.get_image_annotation_metadata(image_id)

        assert annotations is not None
        assert annotations["tags_text"] == "cat"
        assert annotations["caption_text"] == "a cat"
        assert "quality_summary" in annotations

    def test_get_image_annotation_metadata_missing_image_returns_none(
        self, image_repository: ImageRepository
    ) -> None:
        """未登録 image_id では None を返す。"""
        assert image_repository.get_image_annotation_metadata(99999) is None
