"""Phase 4 Search facets の ImageRepository フィルタテスト。

_apply_reviewed_at_filter / _apply_error_state_filter / _apply_model_filter の
クエリビルダー単体テストおよび get_recently_used_model_ids のテスト。
"""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.image import ImageRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def _create_image(session_factory, reviewed_at=None):
    """テスト用 Image を1件作成して id を返す。"""
    from lorairo.database.schema import Image

    with session_factory() as session:
        img = Image(
            uuid=str(uuid.uuid4()),
            phash=f"aa{uuid.uuid4().hex[:10]}",
            original_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            stored_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            width=100,
            height=100,
            format="PNG",
            extension="png",
            reviewed_at=reviewed_at,
        )
        session.add(img)
        session.commit()
        return img.id


def _create_error_record(session_factory, image_id: int, resolved_at=None):
    """テスト用 ErrorRecord を1件作成する。"""
    from lorairo.database.schema import ErrorRecord

    with session_factory() as session:
        record = ErrorRecord(
            image_id=image_id,
            operation_type="annotation",
            error_type="APIError",
            error_message="test error",
            resolved_at=resolved_at,
        )
        session.add(record)
        session.commit()
        return record.id


def _create_model_with_tag(session_factory, litellm_model_id: str, image_id: int):
    """テスト用 Model と Tag を作成して model.id を返す。"""
    from lorairo.database.schema import Model, Tag

    with session_factory() as session:
        model = Model(
            name=f"model_{uuid.uuid4().hex[:6]}",
            litellm_model_id=litellm_model_id,
        )
        session.add(model)
        session.flush()
        tag = Tag(
            image_id=image_id,
            model_id=model.id,
            tag="test_tag",
        )
        session.add(tag)
        session.commit()
        return model.id


# ---------------------------------------------------------------------------
# _apply_reviewed_at_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyReviewedAtFilter:
    """_apply_reviewed_at_filter() メソッドのクエリビルダーテスト。"""

    @pytest.fixture
    def repository(self):
        from unittest.mock import Mock

        return ImageRepository(session_factory=Mock())

    def test_unreviewed_filter_modifies_query(self, repository):
        """ "unreviewed" 指定でクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_reviewed_at_filter(base_query, "unreviewed")
        assert result is not None
        assert result != base_query

    def test_reviewed_filter_modifies_query(self, repository):
        """ "reviewed" 指定でクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_reviewed_at_filter(base_query, "reviewed")
        assert result is not None
        assert result != base_query

    def test_none_filter_does_not_modify_query(self, repository):
        """None 指定でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_reviewed_at_filter(base_query, None)
        assert result == base_query

    def test_unknown_value_does_not_modify_query(self, repository):
        """未知の値でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_reviewed_at_filter(base_query, "invalid_value")
        assert result == base_query


@pytest.mark.unit
class TestApplyReviewedAtFilterIntegration:
    """_apply_reviewed_at_filter() の DB 実行テスト。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    def test_unreviewed_filter_excludes_reviewed_images(self, repository, session_factory):
        """ "unreviewed" で reviewed_at IS NULL の画像のみ返る。"""
        import datetime

        from lorairo.database.schema import Image

        id_unreviewed = _create_image(session_factory, reviewed_at=None)
        id_reviewed = _create_image(
            session_factory,
            reviewed_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_reviewed_at_filter(base_query, "unreviewed")
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_unreviewed in result_ids
        assert id_reviewed not in result_ids

    def test_reviewed_filter_excludes_unreviewed_images(self, repository, session_factory):
        """ "reviewed" で reviewed_at IS NOT NULL の画像のみ返る。"""
        import datetime

        from lorairo.database.schema import Image

        id_unreviewed = _create_image(session_factory, reviewed_at=None)
        id_reviewed = _create_image(
            session_factory,
            reviewed_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_reviewed_at_filter(base_query, "reviewed")
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_reviewed in result_ids
        assert id_unreviewed not in result_ids

    def test_none_filter_returns_all(self, repository, session_factory):
        """None 指定で全件返る。"""
        import datetime

        from lorairo.database.schema import Image

        id_unreviewed = _create_image(session_factory, reviewed_at=None)
        id_reviewed = _create_image(
            session_factory,
            reviewed_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_reviewed_at_filter(base_query, None)
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_unreviewed in result_ids
        assert id_reviewed in result_ids


# ---------------------------------------------------------------------------
# _apply_error_state_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyErrorStateFilter:
    """_apply_error_state_filter() メソッドのクエリビルダーテスト。"""

    @pytest.fixture
    def repository(self):
        from unittest.mock import Mock

        return ImageRepository(session_factory=Mock())

    def test_has_error_filter_modifies_query(self, repository):
        """ "has_error" 指定でクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_error_state_filter(base_query, "has_error")
        assert result is not None
        assert result != base_query

    def test_no_error_filter_modifies_query(self, repository):
        """ "no_error" 指定でクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_error_state_filter(base_query, "no_error")
        assert result is not None
        assert result != base_query

    def test_none_filter_does_not_modify_query(self, repository):
        """None 指定でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_error_state_filter(base_query, None)
        assert result == base_query

    def test_unknown_value_does_not_modify_query(self, repository):
        """未知の値でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_error_state_filter(base_query, "unknown_state")
        assert result == base_query


@pytest.mark.unit
class TestApplyErrorStateFilterIntegration:
    """_apply_error_state_filter() の DB 実行テスト。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    def test_has_error_returns_only_images_with_unresolved_errors(self, repository, session_factory):
        """ "has_error" で未解決エラーを持つ画像のみ返る。"""
        from lorairo.database.schema import Image

        id_with_error = _create_image(session_factory)
        id_no_error = _create_image(session_factory)
        _create_error_record(session_factory, id_with_error, resolved_at=None)

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_error_state_filter(base_query, "has_error")
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_with_error in result_ids
        assert id_no_error not in result_ids

    def test_no_error_excludes_images_with_unresolved_errors(self, repository, session_factory):
        """ "no_error" で未解決エラーを持つ画像が除外される。"""
        from lorairo.database.schema import Image

        id_with_error = _create_image(session_factory)
        id_no_error = _create_image(session_factory)
        _create_error_record(session_factory, id_with_error, resolved_at=None)

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_error_state_filter(base_query, "no_error")
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_no_error in result_ids
        assert id_with_error not in result_ids

    def test_resolved_error_counted_as_no_error(self, repository, session_factory):
        """解決済み（resolved_at IS NOT NULL）のエラーは "has_error" に数えない。"""
        import datetime

        from lorairo.database.schema import Image

        id_with_resolved_error = _create_image(session_factory)
        _create_error_record(
            session_factory,
            id_with_resolved_error,
            resolved_at=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )

        base_query = select(Image.id)
        with session_factory() as session:
            # 解決済みエラーのみの画像は "has_error" に該当しない
            filtered = repository._apply_error_state_filter(base_query, "has_error")
            result_ids = list(session.execute(filtered).scalars().all())
        assert id_with_resolved_error not in result_ids

        with session_factory() as session:
            # "no_error" には該当する
            filtered = repository._apply_error_state_filter(base_query, "no_error")
            result_ids = list(session.execute(filtered).scalars().all())
        assert id_with_resolved_error in result_ids


# ---------------------------------------------------------------------------
# _apply_model_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyModelFilter:
    """_apply_model_filter() メソッドのクエリビルダーテスト。"""

    @pytest.fixture
    def repository(self):
        from unittest.mock import Mock

        return ImageRepository(session_factory=Mock())

    def test_model_filter_with_ids_modifies_query(self, repository):
        """model_filter 指定でクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_model_filter(base_query, ["gpt-4o"])
        assert result is not None
        assert result != base_query

    def test_none_model_filter_does_not_modify_query(self, repository):
        """None 指定でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_model_filter(base_query, None)
        assert result == base_query

    def test_empty_list_does_not_modify_query(self, repository):
        """空リスト指定でクエリが変更されない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_model_filter(base_query, [])
        assert result == base_query


@pytest.mark.unit
class TestApplyModelFilterIntegration:
    """_apply_model_filter() の DB 実行テスト。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    def test_model_filter_returns_only_images_with_annotation_from_model(self, repository, session_factory):
        """指定モデルのアノテーションを持つ画像のみ返る。"""
        from lorairo.database.schema import Image

        id_with_model = _create_image(session_factory)
        id_without_model = _create_image(session_factory)
        _create_model_with_tag(session_factory, "gpt-4o", id_with_model)

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_model_filter(base_query, ["gpt-4o"])
            result_ids = list(session.execute(filtered).scalars().all())

        assert id_with_model in result_ids
        assert id_without_model not in result_ids

    def test_model_filter_unknown_model_returns_empty(self, repository, session_factory):
        """存在しないモデルを指定した場合、結果は空になる。"""
        from lorairo.database.schema import Image

        _create_image(session_factory)

        base_query = select(Image.id)
        with session_factory() as session:
            filtered = repository._apply_model_filter(base_query, ["nonexistent-model"])
            result_ids = list(session.execute(filtered).scalars().all())

        assert result_ids == []


# ---------------------------------------------------------------------------
# get_recently_used_model_ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetRecentlyUsedModelIds:
    """get_recently_used_model_ids() メソッドのテスト。"""

    @pytest.fixture
    def session_factory(self):
        return _make_session_factory()

    @pytest.fixture
    def repository(self, session_factory):
        return ImageRepository(session_factory=session_factory)

    def test_returns_empty_when_no_annotations(self, repository):
        """アノテーションが1件もない場合、空リストを返す。"""
        result = repository.get_recently_used_model_ids()
        assert result == []

    def test_returns_model_ids_with_annotations(self, repository, session_factory):
        """アノテーション実績があるモデルの litellm_model_id を返す。"""
        image_id = _create_image(session_factory)
        _create_model_with_tag(session_factory, "gpt-4o", image_id)

        result = repository.get_recently_used_model_ids()
        assert "gpt-4o" in result

    def test_does_not_return_models_without_annotations(self, repository, session_factory):
        """アノテーションなしのモデルは返さない。"""
        from lorairo.database.schema import Model

        with session_factory() as session:
            model = Model(
                name="unused_model",
                litellm_model_id="unused-model/v1",
            )
            session.add(model)
            session.commit()

        result = repository.get_recently_used_model_ids()
        assert "unused-model/v1" not in result

    def test_limit_parameter_is_respected(self, repository, session_factory):
        """limit パラメータで件数が制限される。"""
        image_id = _create_image(session_factory)
        for i in range(5):
            _create_model_with_tag(session_factory, f"model-{i}", image_id)

        result = repository.get_recently_used_model_ids(limit=3)
        assert len(result) <= 3
