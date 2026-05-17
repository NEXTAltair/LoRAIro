"""ImageRepository._save_score_labels のテスト (Issue #281 / ADR 0027).

canonical scorer (aesthetic_shadow_v1/v2 等) の categorical label を保存する
``_save_score_labels`` メソッドの Upsert 動作を検証する。
"""

from unittest.mock import MagicMock, Mock

import pytest

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import ScoreLabel


class TestSaveScoreLabels:
    """``_save_score_labels`` の Upsert 動作テスト。"""

    @pytest.fixture
    def repository(self) -> ImageRepository:
        """テスト用 ImageRepository。"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """モックセッション。"""
        session = MagicMock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return session

    def test_insert_new_score_label(self, repository: ImageRepository, mock_session: MagicMock) -> None:
        """既存レコードがなければ INSERT される。"""
        # 既存 score_label レコードなし
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        data = [{"model_id": 42, "label": "very aesthetic", "is_edited_manually": False}]
        repository._save_score_labels(mock_session, image_id=100, score_labels_data=data)

        # session.add が 1 回呼ばれる (INSERT)
        assert mock_session.add.call_count == 1
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, ScoreLabel)
        assert added.image_id == 100
        assert added.model_id == 42
        assert added.label == "very aesthetic"
        assert added.is_edited_manually is False

    def test_update_existing_score_label(
        self, repository: ImageRepository, mock_session: MagicMock
    ) -> None:
        """同一 model_id の既存レコードがあれば UPDATE される。"""
        existing = ScoreLabel(
            id=7,
            image_id=100,
            model_id=42,
            label="displeasing",
            is_edited_manually=False,
        )
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = mock_execute_result

        # 再アノテーションで label が "displeasing" → "very aesthetic" に変化
        data = [{"model_id": 42, "label": "very aesthetic", "is_edited_manually": False}]
        repository._save_score_labels(mock_session, image_id=100, score_labels_data=data)

        # session.add は呼ばれない (UPDATE)
        mock_session.add.assert_not_called()
        # 既存レコードが更新される
        assert existing.label == "very aesthetic"
        assert existing.is_edited_manually is False

    def test_mixed_insert_and_update(self, repository: ImageRepository, mock_session: MagicMock) -> None:
        """異なる model_id では INSERT + UPDATE が混在する。"""
        # model_id=42 は既存、model_id=43 は新規
        existing = ScoreLabel(
            id=7,
            image_id=100,
            model_id=42,
            label="aesthetic",
            is_edited_manually=False,
        )
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [existing]
        mock_session.execute.return_value = mock_execute_result

        data = [
            {"model_id": 42, "label": "very aesthetic", "is_edited_manually": False},
            {"model_id": 43, "label": "aesthetic", "is_edited_manually": False},
        ]
        repository._save_score_labels(mock_session, image_id=100, score_labels_data=data)

        # 既存 (model_id=42) は UPDATE、新規 (model_id=43) は INSERT (1 add)
        assert mock_session.add.call_count == 1
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, ScoreLabel)
        assert added.model_id == 43
        assert added.label == "aesthetic"
        assert existing.label == "very aesthetic"  # UPDATE 確認

    def test_empty_data_no_op(self, repository: ImageRepository, mock_session: MagicMock) -> None:
        """空 list を渡しても session.add は呼ばれない。"""
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        repository._save_score_labels(mock_session, image_id=100, score_labels_data=[])

        mock_session.add.assert_not_called()

    def test_is_edited_manually_passthrough(
        self, repository: ImageRepository, mock_session: MagicMock
    ) -> None:
        """is_edited_manually=True が DB に伝播する。"""
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute_result

        data = [{"model_id": 42, "label": "manual override", "is_edited_manually": True}]
        repository._save_score_labels(mock_session, image_id=100, score_labels_data=data)

        added = mock_session.add.call_args[0][0]
        assert added.is_edited_manually is True
