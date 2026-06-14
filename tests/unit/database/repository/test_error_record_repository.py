"""ErrorRecordRepository 直接の単体テスト (ADR 0035 段階 3, Issue #423)。

`db_repository.py` から抽出した `ErrorRecordRepository` の責務境界を独立して検証する。
既存の `tests/unit/database/test_db_repository_error_records.py` は
`ImageRepository` の delegating facade 経由で同じ実装をカバーしているため、本ファイルでは
ErrorRecordRepository を直接 instantiate して以下を最小限カバーする:

- BaseRepository 継承 / session_factory 共有
- `save_error_record` の正常系 + SQLAlchemyError 伝播 (PR #476: Repository 側で raise、
  二次エラー防止 sentinel `-1` は Manager 層の責務)
- `get_error_count_unresolved` / `get_error_image_ids` / `get_error_records` の動作
- `mark_error_resolved` / `mark_errors_resolved_batch` の動作 + 空入力ガード
- ImageRepository facade 経由でも同じ ErrorRecordRepository クラスが見えること
- DI contract: ImageDatabaseManager は injected error_record_repo 経由で呼ぶ
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import ErrorRecord
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def error_record_repository(memory_session_factory) -> ErrorRecordRepository:
    """In-memory SQLite に対する ErrorRecordRepository インスタンス。"""
    return ErrorRecordRepository(session_factory=memory_session_factory)


def _insert_error(
    repo: ErrorRecordRepository,
    *,
    operation_type: str = "annotation",
    error_type: str = "APIError",
    error_message: str = "test",
    image_id: int | None = None,
) -> int:
    """テスト用エラーを 1 件作成して id を返す。"""
    return repo.save_error_record(
        operation_type=operation_type,
        error_type=error_type,
        error_message=error_message,
        image_id=image_id,
    )


@pytest.mark.unit
class TestErrorRecordRepositoryStructure:
    """ADR 0035 段階 3 で確立した抽出構造の sanity check。"""

    def test_inherits_base_repository(self) -> None:
        """ErrorRecordRepository は BaseRepository を継承する。"""
        assert issubclass(ErrorRecordRepository, BaseRepository)

    def test_holds_session_factory(self, memory_session_factory) -> None:
        """`session_factory` を BaseRepository 経由で保持する。"""
        repo = ErrorRecordRepository(session_factory=memory_session_factory)
        assert repo.session_factory is memory_session_factory


@pytest.mark.unit
class TestSaveErrorRecord:
    """`save_error_record` の永続化動作。"""

    def test_creates_record_and_returns_positive_id(
        self, error_record_repository: ErrorRecordRepository, memory_session_factory
    ) -> None:
        """新規エラーレコードを保存して正の ID を返し、DB にも書き込まれる。"""
        error_id = error_record_repository.save_error_record(
            operation_type="annotation",
            error_type="APIError",
            error_message="timeout",
            image_id=100,
            stack_trace="trace lines",
            file_path="/path/to/file.jpg",
            model_name="gpt-4",
        )
        assert isinstance(error_id, int)
        assert error_id > 0

        with memory_session_factory() as session:
            record = session.execute(select(ErrorRecord).where(ErrorRecord.id == error_id)).scalar_one()
            assert record.operation_type == "annotation"
            assert record.error_type == "APIError"
            assert record.error_message == "timeout"
            assert record.image_id == 100
            assert record.stack_trace == "trace lines"
            assert record.file_path == "/path/to/file.jpg"
            assert record.model_name == "gpt-4"
            assert record.resolved_at is None

    def test_minimal_fields_persisted(
        self, error_record_repository: ErrorRecordRepository, memory_session_factory
    ) -> None:
        """必須 3 フィールドのみでも保存できる (Optional 引数は None で永続化される)。"""
        error_id = error_record_repository.save_error_record(
            operation_type="registration",
            error_type="FileNotFoundError",
            error_message="missing file",
        )
        with memory_session_factory() as session:
            record = session.execute(select(ErrorRecord).where(ErrorRecord.id == error_id)).scalar_one()
            assert record.image_id is None
            assert record.stack_trace is None
            assert record.file_path is None
            assert record.model_name is None

    def test_raises_sqlalchemy_error(self, error_record_repository: ErrorRecordRepository) -> None:
        """予期しない SQLAlchemyError は呼び出し元へ伝播し rollback される。

        PR #476 教訓: Repository 層では `except Exception` で握り潰さない。
        二次エラー防止 (sentinel `-1` return) は Manager 層 (`ImageDatabaseManager`)
        の責務として維持する。
        """
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.add.side_effect = SQLAlchemyError("simulated failure")
        mock_session.rollback = Mock()

        with patch.object(error_record_repository, "session_factory", return_value=mock_session):
            with pytest.raises(SQLAlchemyError, match="simulated failure"):
                error_record_repository.save_error_record(
                    operation_type="annotation",
                    error_type="APIError",
                    error_message="boom",
                )
        mock_session.rollback.assert_called()


@pytest.mark.unit
class TestGetErrorCountUnresolved:
    """`get_error_count_unresolved` の集計動作。"""

    def test_counts_only_unresolved(
        self, error_record_repository: ErrorRecordRepository, memory_session_factory
    ) -> None:
        """resolved_at IS NULL のみカウントする。"""
        eid1 = _insert_error(error_record_repository)
        _insert_error(error_record_repository)
        _insert_error(error_record_repository)

        # eid1 を解決済みにマークする
        error_record_repository.mark_error_resolved(eid1)

        assert error_record_repository.get_error_count_unresolved() == 2

    def test_filters_by_operation_type(self, error_record_repository: ErrorRecordRepository) -> None:
        """operation_type 指定で対応分のみカウントする。"""
        _insert_error(error_record_repository, operation_type="annotation")
        _insert_error(error_record_repository, operation_type="annotation")
        _insert_error(error_record_repository, operation_type="registration")

        assert error_record_repository.get_error_count_unresolved(operation_type="annotation") == 2
        assert error_record_repository.get_error_count_unresolved(operation_type="registration") == 1

    def test_returns_zero_when_empty(self, error_record_repository: ErrorRecordRepository) -> None:
        """エラーレコードが無いとき 0 を返す (silent return ではなく正常系)。"""
        assert error_record_repository.get_error_count_unresolved() == 0


@pytest.mark.unit
class TestGetErrorImageIds:
    """`get_error_image_ids` の動作 (重複除去 / フィルタ)。"""

    def test_returns_distinct_image_ids(self, error_record_repository: ErrorRecordRepository) -> None:
        """同じ image_id に対して複数エラーがあっても 1 件に集約される。"""
        _insert_error(error_record_repository, image_id=10)
        _insert_error(error_record_repository, image_id=10)
        _insert_error(error_record_repository, image_id=20)
        _insert_error(error_record_repository, image_id=None)  # None は除外される

        ids = error_record_repository.get_error_image_ids()
        assert set(ids) == {10, 20}

    def test_filters_by_error_types(self, error_record_repository: ErrorRecordRepository) -> None:
        """error_types フィルタで特定の error_type のみを抽出する。"""
        _insert_error(error_record_repository, image_id=1, error_type="SAFETY_REFUSAL")
        _insert_error(error_record_repository, image_id=2, error_type="APIError")

        ids = error_record_repository.get_error_image_ids(error_types=["SAFETY_REFUSAL"])
        assert ids == [1]

    def test_resolved_filter(self, error_record_repository: ErrorRecordRepository) -> None:
        """resolved=True で解決済みのみ、False で未解決のみを返す。"""
        eid1 = _insert_error(error_record_repository, image_id=100)
        _insert_error(error_record_repository, image_id=200)
        error_record_repository.mark_error_resolved(eid1)

        unresolved = error_record_repository.get_error_image_ids(resolved=False)
        resolved = error_record_repository.get_error_image_ids(resolved=True)

        assert unresolved == [200]
        assert resolved == [100]


@pytest.mark.unit
class TestGetErrorRecords:
    """`get_error_records` のページネーション / ソート動作。"""

    def test_returns_records_in_desc_order(self, error_record_repository: ErrorRecordRepository) -> None:
        """created_at の降順で返る (新しいものが先頭)。"""
        eid1 = _insert_error(error_record_repository, error_message="first")
        eid2 = _insert_error(error_record_repository, error_message="second")
        eid3 = _insert_error(error_record_repository, error_message="third")

        records = error_record_repository.get_error_records()
        # eid3, eid2, eid1 の順 (desc by created_at) — id は単調増加なので id 降順と一致
        ids = [r.id for r in records]
        assert ids == sorted([eid1, eid2, eid3], reverse=True)

    def test_limit_and_offset(self, error_record_repository: ErrorRecordRepository) -> None:
        """limit / offset がページングに反映される。"""
        for i in range(5):
            _insert_error(error_record_repository, error_message=f"msg-{i}")

        page = error_record_repository.get_error_records(limit=2, offset=1)
        assert len(page) == 2

    def test_resolved_none_returns_all(self, error_record_repository: ErrorRecordRepository) -> None:
        """resolved=None で解決済み / 未解決を区別せず全件返す。"""
        eid1 = _insert_error(error_record_repository)
        _insert_error(error_record_repository)
        error_record_repository.mark_error_resolved(eid1)

        all_records = error_record_repository.get_error_records(resolved=None)
        assert len(all_records) == 2


@pytest.mark.unit
class TestGetErrorRecord:
    """`get_error_record` の単件取得動作。"""

    def test_returns_record_by_id(self, error_record_repository: ErrorRecordRepository) -> None:
        """ID 指定で該当する 1 件を返す。"""
        eid = error_record_repository.save_error_record(
            operation_type="annotation",
            error_type="APIError",
            error_message="timeout",
            image_id=42,
            stack_trace="trace lines",
            file_path="/path/to/file.jpg",
            model_name="gpt-4",
        )

        record = error_record_repository.get_error_record(eid)

        assert record is not None
        assert record.id == eid
        assert record.operation_type == "annotation"
        assert record.error_type == "APIError"
        assert record.error_message == "timeout"
        assert record.image_id == 42
        assert record.stack_trace == "trace lines"
        assert record.file_path == "/path/to/file.jpg"
        assert record.model_name == "gpt-4"

    def test_returns_none_for_unknown_id(self, error_record_repository: ErrorRecordRepository) -> None:
        """存在しない ID では None を返す (正常系)。"""
        assert error_record_repository.get_error_record(99999) is None


@pytest.mark.unit
class TestMarkErrorResolved:
    """`mark_error_resolved` の単件解決動作。"""

    def test_sets_resolved_at(
        self, error_record_repository: ErrorRecordRepository, memory_session_factory
    ) -> None:
        """resolved_at が現在時刻に更新される。"""
        eid = _insert_error(error_record_repository)
        before = datetime.now(UTC)
        error_record_repository.mark_error_resolved(eid)

        with memory_session_factory() as session:
            record = session.execute(select(ErrorRecord).where(ErrorRecord.id == eid)).scalar_one()
            assert record.resolved_at is not None
            # SQLite TIMESTAMP は読み出し時に naive datetime になる場合があるので
            # tz-aware に正規化して比較する。
            resolved_at = record.resolved_at
            if resolved_at.tzinfo is None:
                resolved_at = resolved_at.replace(tzinfo=UTC)
            assert resolved_at >= before

    def test_unknown_id_does_not_raise(self, error_record_repository: ErrorRecordRepository) -> None:
        """存在しない ID では warning ログのみで raise しない (正常系)。"""
        # 例外が出ないことを確認 (logger.warning は副作用なし)
        error_record_repository.mark_error_resolved(99999)


@pytest.mark.unit
class TestMarkErrorsResolvedBatch:
    """`mark_errors_resolved_batch` の一括解決動作。"""

    def test_returns_false_zero_for_empty_input(
        self, error_record_repository: ErrorRecordRepository
    ) -> None:
        """空リスト入力では (False, 0) を返す (DB アクセスしない)。"""
        success, count = error_record_repository.mark_errors_resolved_batch([])
        assert success is False
        assert count == 0

    def test_marks_all_in_batch(
        self, error_record_repository: ErrorRecordRepository, memory_session_factory
    ) -> None:
        """対象 ID 全件に resolved_at がセットされる。"""
        ids = [_insert_error(error_record_repository) for _ in range(3)]
        success, count = error_record_repository.mark_errors_resolved_batch(ids)

        assert success is True
        assert count == 3
        with memory_session_factory() as session:
            for eid in ids:
                record = session.execute(select(ErrorRecord).where(ErrorRecord.id == eid)).scalar_one()
                assert record.resolved_at is not None

    def test_partial_existing_ids(self, error_record_repository: ErrorRecordRepository) -> None:
        """存在しない ID が混ざっていても、存在するものだけ更新する (count に反映)。"""
        existing = _insert_error(error_record_repository)
        success, count = error_record_repository.mark_errors_resolved_batch([existing, 99999])
        assert success is True
        assert count == 1


@pytest.mark.unit
class TestImageDatabaseManagerDIContract:
    """ImageDatabaseManager が injected `error_record_repo` 経由で呼ぶ (DI contract)。

    PR #477 review 教訓: クラス経由 static 呼び出しではなく、インスタンス経由で呼ぶことで
    テストが mock 注入で動作を制御できる。
    """

    def test_save_error_record_uses_injected_error_record_repo(self) -> None:
        """`save_error_record` Manager Facade は self.error_record_repo.save_error_record を呼ぶ。"""
        mock_config_service = Mock(spec=ConfigurationService)
        mock_error_record_repo = Mock(spec=ErrorRecordRepository)
        mock_error_record_repo.save_error_record.return_value = 42

        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            error_record_repo=mock_error_record_repo,
        )

        result = manager.save_error_record(
            operation_type="annotation",
            error_type="APIError",
            error_message="timeout",
            image_id=7,
        )

        assert result == 42
        # injected mock 経由で呼ばれることを assert (DI contract)
        mock_error_record_repo.save_error_record.assert_called_once_with(
            operation_type="annotation",
            error_type="APIError",
            error_message="timeout",
            image_id=7,
            stack_trace=None,
            file_path=None,
            model_name=None,
        )

    def test_save_error_record_returns_minus_one_on_exception(self) -> None:
        """二次エラー防止 (PR #476): Repository 例外を Manager で sentinel `-1` に畳む。"""
        mock_config_service = Mock(spec=ConfigurationService)
        mock_error_record_repo = Mock(spec=ErrorRecordRepository)
        mock_error_record_repo.save_error_record.side_effect = Exception("DB down")

        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            error_record_repo=mock_error_record_repo,
        )

        result = manager.save_error_record(
            operation_type="registration",
            error_type="FileNotFoundError",
            error_message="file missing",
        )

        assert result == -1

    def test_mark_errors_resolved_batch_uses_injected_repo(self) -> None:
        """Manager の mark_errors_resolved_batch は self.error_record_repo を呼ぶ。"""
        mock_config_service = Mock(spec=ConfigurationService)
        mock_error_record_repo = Mock(spec=ErrorRecordRepository)
        mock_error_record_repo.mark_errors_resolved_batch.return_value = (True, 3)

        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            error_record_repo=mock_error_record_repo,
        )

        result = manager.mark_errors_resolved_batch([1, 2, 3])

        assert result == (True, 3)
        mock_error_record_repo.mark_errors_resolved_batch.assert_called_once_with([1, 2, 3])

    def test_auto_constructs_error_record_repo_with_session_factory(self, memory_session_factory) -> None:
        """`session_factory` 引数で error_record_repo が自動生成される。

        ADR 0035 段階 6 (#423): facade 撤廃後、session_factory を Manager に渡すと
        全 Repo がそれを共有して構築される。
        """
        mock_config_service = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            session_factory=memory_session_factory,
        )
        assert isinstance(manager.error_record_repo, ErrorRecordRepository)
        assert manager.error_record_repo.session_factory is memory_session_factory
