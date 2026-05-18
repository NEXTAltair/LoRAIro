"""ImageRepository._save_score_labels / _format_score_labels のテスト (Issue #281, #284 / ADR 0027, 0028).

canonical scorer (aesthetic_shadow_v1/v2 等) の categorical label を保存する
``_save_score_labels`` メソッドの Upsert 動作と、formatting helper ``_format_score_labels``
(ADR 0028) の挙動を検証する。
"""

import datetime
from types import SimpleNamespace
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


class TestFormatScoreLabels:
    """``_format_score_labels`` の formatting 動作テスト (ADR 0028)。

    ADR 0028 で「常に {model, label} ペアで保持」「scalar shorthand 不採用」と決定済み。
    """

    @pytest.fixture
    def repository(self) -> ImageRepository:
        """テスト用 ImageRepository。"""
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def _make_score_label(
        self,
        sl_id: int,
        model_id: int,
        model_name: str,
        label: str,
        is_edited_manually: bool | None = False,
    ) -> SimpleNamespace:
        """ScoreLabel ORM ロード相当の SimpleNamespace を組み立てる。"""
        return SimpleNamespace(
            id=sl_id,
            image_id=100,
            model_id=model_id,
            label=label,
            is_edited_manually=is_edited_manually,
            created_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            model=SimpleNamespace(name=model_name),
        )

    def test_format_score_labels_empty(self, repository: ImageRepository) -> None:
        """score_labels 0 件で annotations["score_labels"] = [] となる。"""
        image = SimpleNamespace(score_labels=[])
        annotations: dict = {}

        repository._format_score_labels(image, annotations)

        assert annotations["score_labels"] == []

    def test_format_score_labels_single_model(self, repository: ImageRepository) -> None:
        """1 scorer の場合、{model, label, ...} 構造で 1 entry が組まれる。"""
        sl = self._make_score_label(1, 42, "aesthetic_shadow_v1", "very aesthetic")
        image = SimpleNamespace(score_labels=[sl])
        annotations: dict = {}

        repository._format_score_labels(image, annotations)

        assert len(annotations["score_labels"]) == 1
        entry = annotations["score_labels"][0]
        assert entry["label"] == "very aesthetic"
        assert entry["model"] == "aesthetic_shadow_v1"
        assert entry["model_id"] == 42
        assert entry["is_edited_manually"] is False
        # Scalar shorthand は ADR 0028 で不採用
        assert "score_label_value" not in annotations

    def test_format_score_labels_multi_models(self, repository: ImageRepository) -> None:
        """複数 scorer の場合、各 entry が並列に保持される (順序は image.score_labels 順)。"""
        labels = [
            self._make_score_label(1, 42, "aesthetic_shadow_v1", "very aesthetic"),
            self._make_score_label(2, 43, "aesthetic_shadow_v2", "aesthetic"),
            self._make_score_label(3, 44, "cafe_aesthetic", "very aesthetic"),
        ]
        image = SimpleNamespace(score_labels=labels)
        annotations: dict = {}

        repository._format_score_labels(image, annotations)

        assert len(annotations["score_labels"]) == 3
        models = [e["model"] for e in annotations["score_labels"]]
        assert models == ["aesthetic_shadow_v1", "aesthetic_shadow_v2", "cafe_aesthetic"]

    def test_format_score_labels_unknown_model(self, repository: ImageRepository) -> None:
        """model relationship が None の場合 'Unknown' を埋める (既存 helper と整合)。"""
        sl = SimpleNamespace(
            id=1,
            image_id=100,
            model_id=42,
            label="aesthetic",
            is_edited_manually=False,
            created_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            model=None,
        )
        image = SimpleNamespace(score_labels=[sl])
        annotations: dict = {}

        repository._format_score_labels(image, annotations)

        assert annotations["score_labels"][0]["model"] == "Unknown"

    def test_format_annotations_for_metadata_includes_score_labels(
        self, repository: ImageRepository
    ) -> None:
        """_format_annotations_for_metadata に score_labels が組み込まれる。"""
        sl = self._make_score_label(1, 42, "aesthetic_shadow_v1", "very aesthetic")
        image = SimpleNamespace(
            tags=[],
            captions=[],
            scores=[],
            ratings=[],
            score_labels=[sl],
        )

        annotations = repository._format_annotations_for_metadata(image)

        assert "score_labels" in annotations
        assert annotations["score_labels"][0]["label"] == "very aesthetic"
        assert annotations["score_labels"][0]["model"] == "aesthetic_shadow_v1"
