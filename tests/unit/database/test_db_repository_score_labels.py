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


class TestGetImageAnnotationsScoreLabels:
    """``get_image_annotations`` 経由で score_labels が読まれることを検証する (ADR 0028)。

    PR #286 レビューで指摘された silent バグ防止: 過去 ``get_image_annotations`` は
    tags/captions/scores/ratings のみ返却で score_labels を silent drop していた。
    本テストは ``_get_image_export_data`` 等の downstream が score_labels を取得
    できる経路を保証する。
    """

    @pytest.fixture
    def repository(self) -> ImageRepository:
        """テスト用 ImageRepository。"""
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def _setup_session_with_image(
        self, repository: ImageRepository, image: SimpleNamespace | None
    ) -> MagicMock:
        """session_factory を mock してテスト用 Image を返すように設定。"""
        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = image
        mock_session.execute.return_value = mock_result

        repository.session_factory = MagicMock(return_value=mock_session)
        return mock_session

    def test_get_image_annotations_includes_score_labels_key_when_empty(
        self, repository: ImageRepository
    ) -> None:
        """画像なしでも score_labels: [] が返値に含まれる (key 欠落で silent fail しない)。"""
        self._setup_session_with_image(repository, None)

        annotations = repository.get_image_annotations(image_id=100)

        assert "score_labels" in annotations
        assert annotations["score_labels"] == []

    def test_get_image_annotations_returns_score_labels_from_db(self, repository: ImageRepository) -> None:
        """DB に score_labels がある場合、{model, label, ...} 構造で返値に含まれる。"""
        sl = SimpleNamespace(
            id=1,
            image_id=100,
            model_id=42,
            label="very aesthetic",
            is_edited_manually=False,
            created_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
            model=SimpleNamespace(name="aesthetic_shadow_v1"),
        )
        image = SimpleNamespace(
            tags=[],
            captions=[],
            scores=[],
            ratings=[],
            score_labels=[sl],
        )
        self._setup_session_with_image(repository, image)

        annotations = repository.get_image_annotations(image_id=100)

        assert len(annotations["score_labels"]) == 1
        entry = annotations["score_labels"][0]
        assert entry["label"] == "very aesthetic"
        # ADR 0028: model 名と組で保持
        assert entry["model"] == "aesthetic_shadow_v1"
        assert entry["model_id"] == 42

    def test_get_image_annotations_multi_scorer_score_labels(self, repository: ImageRepository) -> None:
        """複数 scorer の score_labels が list 順序で全件返る (UC-A 多数決の前提)。"""
        labels = [
            SimpleNamespace(
                id=i,
                image_id=100,
                model_id=40 + i,
                label=label,
                is_edited_manually=False,
                created_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
                updated_at=datetime.datetime(2026, 5, 18, 10, 0, 0),
                model=SimpleNamespace(name=model_name),
            )
            for i, (model_name, label) in enumerate(
                [
                    ("aesthetic_shadow_v1", "very aesthetic"),
                    ("aesthetic_shadow_v2", "aesthetic"),
                    ("cafe_aesthetic", "very aesthetic"),
                ]
            )
        ]
        image = SimpleNamespace(tags=[], captions=[], scores=[], ratings=[], score_labels=labels)
        self._setup_session_with_image(repository, image)

        annotations = repository.get_image_annotations(image_id=100)

        assert len(annotations["score_labels"]) == 3
        models = [e["model"] for e in annotations["score_labels"]]
        assert models == ["aesthetic_shadow_v1", "aesthetic_shadow_v2", "cafe_aesthetic"]


class TestGetImageAnnotationsQualitySummary:
    """``get_image_annotations`` が ADR 0029 の ``quality_summary`` を含む。"""

    @pytest.fixture
    def repository(self) -> ImageRepository:
        mock_session_factory = MagicMock()
        return ImageRepository(session_factory=mock_session_factory)

    def _setup_session_with_image(
        self, repository: ImageRepository, image: SimpleNamespace | None
    ) -> MagicMock:
        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = image
        mock_session.execute.return_value = mock_result
        repository.session_factory = MagicMock(return_value=mock_session)
        return mock_session

    def test_quality_summary_no_score_when_empty(self, repository: ImageRepository) -> None:
        """画像なしでも ``quality_summary`` キーが空 dict で返る。"""
        self._setup_session_with_image(repository, None)

        annotations = repository.get_image_annotations(image_id=100)

        assert "quality_summary" in annotations
        assert annotations["quality_summary"] == {}

    def test_quality_summary_no_score_when_image_has_no_annotations(
        self, repository: ImageRepository
    ) -> None:
        """画像はあるが score 系が空の場合、quality_summary.tier == 'no score'。"""
        image = SimpleNamespace(tags=[], captions=[], scores=[], ratings=[], score_labels=[])
        self._setup_session_with_image(repository, image)

        annotations = repository.get_image_annotations(image_id=100)

        assert annotations["quality_summary"]["tier"] == "no score"
        assert annotations["quality_summary"]["no_score"] is True

    def test_quality_summary_with_score_labels(self, repository: ImageRepository) -> None:
        """score_labels あり -> mapped tier が返る。"""
        sl = SimpleNamespace(
            id=1,
            image_id=100,
            model_id=42,
            label="aesthetic",
            is_edited_manually=False,
            created_at=datetime.datetime(2026, 5, 19, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 19, 10, 0, 0),
            model=SimpleNamespace(name="aesthetic_shadow_v2"),
        )
        image = SimpleNamespace(tags=[], captions=[], scores=[], ratings=[], score_labels=[sl])
        self._setup_session_with_image(repository, image)

        annotations = repository.get_image_annotations(image_id=100)

        assert annotations["quality_summary"]["tier"] == "best quality"
        assert annotations["quality_summary"]["known_count"] == 1
        assert annotations["quality_summary"]["is_unanimous"] is True

    def test_quality_summary_includes_manual_score(self, repository: ImageRepository) -> None:
        """manual score (is_edited_manually=True) が tier に反映される。"""
        score = SimpleNamespace(
            id=1,
            score=9.5,
            model_id=99,
            is_edited_manually=True,
            created_at=datetime.datetime(2026, 5, 19, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 19, 10, 0, 0),
        )
        image = SimpleNamespace(tags=[], captions=[], scores=[score], ratings=[], score_labels=[])
        self._setup_session_with_image(repository, image)

        annotations = repository.get_image_annotations(image_id=100)

        assert annotations["quality_summary"]["tier"] == "masterpiece"
        assert annotations["quality_summary"]["known_count"] == 1


class TestFormatRatings:
    """Issue #334: model 別 rating record の formatting 動作テスト。"""

    @pytest.fixture
    def repository(self) -> ImageRepository:
        mock_session_factory = Mock()
        return ImageRepository(session_factory=mock_session_factory)

    def _make_rating(
        self,
        rating_id: int,
        model_id: int,
        model_name: str,
        raw_rating_value: str,
        normalized_rating: str,
        confidence_score: float | None,
        litellm_model_id: str = "wd-vit-tagger-v3",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=rating_id,
            image_id=100,
            model_id=model_id,
            raw_rating_value=raw_rating_value,
            normalized_rating=normalized_rating,
            confidence_score=confidence_score,
            created_at=datetime.datetime(2026, 5, 21, 10, rating_id, 0),
            updated_at=datetime.datetime(2026, 5, 21, 10, rating_id, 0),
            model=SimpleNamespace(name=model_name, litellm_model_id=litellm_model_id),
        )

    def test_format_ratings_multi_models(self, repository: ImageRepository) -> None:
        ratings = [
            self._make_rating(1, 42, "wd-vit-tagger-v3", "questionable", "R", 0.91),
            self._make_rating(2, 43, "z3d-e621-convnext", "safe", "PG", 0.84),
        ]
        image = SimpleNamespace(ratings=ratings)
        annotations: dict = {}

        repository._format_ratings(image, annotations)

        assert len(annotations["ratings"]) == 2
        assert annotations["ratings"][0]["model"] == "wd-vit-tagger-v3"
        assert annotations["ratings"][0]["model_name"] == "wd-vit-tagger-v3"
        assert annotations["ratings"][0]["raw_rating_value"] == "questionable"
        assert annotations["ratings"][0]["normalized_rating"] == "R"
        assert annotations["ratings"][0]["confidence_score"] == 0.91
        assert annotations["ratings"][0]["source"] == "AI"
        assert annotations["rating_value"] == "PG"

    def test_format_ratings_manual_edit_source(self, repository: ImageRepository) -> None:
        rating = self._make_rating(
            1,
            1,
            "MANUAL_EDIT",
            "PG",
            "PG",
            None,
            litellm_model_id="__manual_edit__",
        )
        image = SimpleNamespace(ratings=[rating])
        annotations: dict = {}

        repository._format_ratings(image, annotations)

        assert annotations["ratings"][0]["source"] == "Manual"

    def test_format_rating_annotation_unknown_model(self, repository: ImageRepository) -> None:
        rating = SimpleNamespace(
            id=1,
            image_id=100,
            model_id=99,
            raw_rating_value="explicit",
            normalized_rating="X",
            confidence_score=0.88,
            created_at=datetime.datetime(2026, 5, 21, 10, 0, 0),
            updated_at=datetime.datetime(2026, 5, 21, 10, 0, 0),
            model=None,
        )

        entry = repository._format_rating_annotation(rating)

        assert entry["model"] == "Unknown"
        assert entry["model_name"] == "Unknown"
        assert entry["source"] == "AI"
