"""DB Manager アノテーションフィルタリング機能のテスト"""

import pytest
from datetime import UTC, datetime, timedelta

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository


@pytest.fixture
def manager() -> ImageDatabaseManager:
    """ImageDatabaseManager インスタンスを提供するフィクスチャ"""
    from lorairo.services.configuration_service import ConfigurationService

    repository = ImageRepository()
    config_service = ConfigurationService()
    return ImageDatabaseManager(repository, config_service)


class TestParseAnnotationTimestamp:
    """_parse_annotation_timestamp メソッドのテストクラス"""

    def test_parse_datetime_object_with_utc(self, manager: ImageDatabaseManager) -> None:
        """UTC タイムゾーン付き datetime オブジェクトをパースする"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        result = manager._parse_annotation_timestamp(base_time)
        assert result is not None
        assert result == base_time
        assert result.tzinfo == UTC

    def test_parse_datetime_object_naive(self, manager: ImageDatabaseManager) -> None:
        """naive datetime オブジェクトを UTC として扱う"""
        now_naive = datetime(2026, 2, 13, 12, 0, 0)
        result = manager._parse_annotation_timestamp(now_naive)
        assert result is not None
        assert result.tzinfo == UTC
        # タイムゾーン情報以外は同じ
        assert result.replace(tzinfo=None) == now_naive

    def test_parse_iso_format_string_with_z(self, manager: ImageDatabaseManager) -> None:
        """ISO 形式文字列（Z サフィックス付き）をパースする"""
        iso_string = "2026-02-13T12:30:45Z"
        result = manager._parse_annotation_timestamp(iso_string)
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 13
        assert result.tzinfo == UTC

    def test_parse_iso_format_string_with_timezone(self, manager: ImageDatabaseManager) -> None:
        """ISO 形式文字列（+00:00 タイムゾーン付き）をパースする"""
        iso_string = "2026-02-13T12:30:45+00:00"
        result = manager._parse_annotation_timestamp(iso_string)
        assert result is not None
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_parse_invalid_string(self, manager: ImageDatabaseManager) -> None:
        """不正な形式の文字列は None を返す"""
        invalid_string = "not a timestamp"
        result = manager._parse_annotation_timestamp(invalid_string)
        assert result is None

    def test_parse_non_string_non_datetime(self, manager: ImageDatabaseManager) -> None:
        """datetime でも str でもない値は None を返す"""
        result = manager._parse_annotation_timestamp(12345)  # type: ignore
        assert result is None

    def test_parse_malformed_iso_string(self, manager: ImageDatabaseManager) -> None:
        """不正な ISO 形式の文字列は None を返す"""
        malformed = "2026-13-45T25:70:90Z"
        result = manager._parse_annotation_timestamp(malformed)
        assert result is None


class TestFindLatestAnnotationTimestamp:
    """_find_latest_annotation_timestamp メソッドのテストクラス"""

    def test_find_latest_with_mixed_timestamps(self, manager: ImageDatabaseManager) -> None:
        """複数のアノテーションから最新のタイムスタンプを取得"""
        # 固定タイムスタンプを使用
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        one_hour_ago = base_time - timedelta(hours=1)
        two_hours_ago = base_time - timedelta(hours=2)

        annotations = {
            "tags": [
                {"updated_at": one_hour_ago},
                {"updated_at": two_hours_ago},
            ],
            "captions": [
                {"updated_at": base_time},
            ],
            "scores": [],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is not None
        assert result == base_time

    def test_find_latest_with_string_timestamps(self, manager: ImageDatabaseManager) -> None:
        """文字列フォーマットのタイムスタンプから最新を取得"""
        annotations = {
            "tags": [
                {"updated_at": "2026-02-13T10:00:00Z"},
            ],
            "captions": [
                {"updated_at": "2026-02-13T12:00:00Z"},
            ],
            "scores": [
                {"updated_at": "2026-02-13T11:00:00Z"},
            ],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is not None
        assert result.hour == 12

    def test_find_latest_with_no_valid_timestamps(self, manager: ImageDatabaseManager) -> None:
        """有効なタイムスタンプが無い場合は None を返す"""
        annotations = {
            "tags": [{"some_field": "value"}],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is None

    def test_find_latest_with_all_empty(self, manager: ImageDatabaseManager) -> None:
        """全てのアノテーションが空の場合は None を返す"""
        annotations = {
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is None

    def test_find_latest_with_invalid_timestamps(self, manager: ImageDatabaseManager) -> None:
        """不正なタイムスタンプは無視して有効なもののみを使用"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        annotations = {
            "tags": [
                {"updated_at": "invalid"},
                {"updated_at": base_time},
            ],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is not None
        assert result == base_time

    def test_find_latest_single_annotation(self, manager: ImageDatabaseManager) -> None:
        """単一のアノテーションタイムスタンプを正しく処理"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        annotations = {
            "tags": [{"updated_at": base_time}],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager._find_latest_annotation_timestamp(annotations)
        assert result is not None
        assert result == base_time


class TestFilterRecentAnnotations:
    """filter_recent_annotations メソッドのテストクラス"""

    def test_filter_within_threshold(self, manager: ImageDatabaseManager) -> None:
        """閾値内のアノテーションがフィルタリングされる"""
        # 固定タイムスタンプを使用して時刻計算の不確定性を排除
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time - timedelta(minutes=1)
        old = base_time - timedelta(minutes=10)

        annotations = {
            "tags": [
                {"tag": "tag1", "updated_at": recent},
                {"tag": "tag2", "updated_at": old},
            ],
            "captions": [{"text": "caption", "updated_at": recent}],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        # 1分前のタグと caption が含まれるはず
        assert len(result["tags"]) == 1
        assert result["tags"][0]["tag"] == "tag1"
        assert len(result["captions"]) == 1

    def test_filter_outside_threshold(self, manager: ImageDatabaseManager) -> None:
        """閾値外のアノテーションは除外される"""
        # 固定タイムスタンプを使用
        # 最新=今、古い=20分前 → 閾値=15分前 → 20分前は除外されるはず
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time  # 最新
        very_old = base_time - timedelta(minutes=20)

        annotations = {
            "tags": [
                {"tag": "recent_tag", "updated_at": recent},
                {"tag": "old_tag", "updated_at": very_old},
            ],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        # recent は含まれるはず
        assert len(result["tags"]) == 1
        assert result["tags"][0]["tag"] == "recent_tag"

    def test_filter_empty_annotations(self, manager: ImageDatabaseManager) -> None:
        """空のアノテーション辞書を処理"""
        annotations = {
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations)

        assert result == annotations

    def test_filter_no_valid_timestamps(self, manager: ImageDatabaseManager) -> None:
        """有効なタイムスタンプが無い場合は空の辞書を返す"""
        annotations = {
            "tags": [{"tag": "tag1"}],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations)

        assert len(result["tags"]) == 0

    def test_filter_mixed_valid_invalid_timestamps(self, manager: ImageDatabaseManager) -> None:
        """有効と無効のタイムスタンプが混在する場合"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time - timedelta(minutes=1)

        annotations = {
            "tags": [
                {"tag": "tag1", "updated_at": recent},
                {"tag": "tag2"},  # updated_at なし
            ],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        # 有効なタイムスタンプのみがフィルタリングされるはず
        assert len(result["tags"]) == 1
        assert result["tags"][0]["tag"] == "tag1"

    def test_filter_different_thresholds(self, manager: ImageDatabaseManager) -> None:
        """異なる閾値でフィルタリングが正しく機能"""
        # 固定タイムスタンプを使用
        # 最新=今(12:00), 古い=20分前(11:40)
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time
        old = base_time - timedelta(minutes=20)

        annotations = {
            "tags": [
                {"tag": "recent_tag", "updated_at": recent},
                {"tag": "old_tag", "updated_at": old},
            ],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        # 5分閾値: 最新(12:00)を基準に12:00-5分=11:55
        # recent(12:00) >= 11:55: YES, old(11:40) >= 11:55: NO → 1件
        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)
        assert len(result["tags"]) == 1
        assert result["tags"][0]["tag"] == "recent_tag"

        # 20分閾値: 最新(12:00)を基準に12:00-20分=11:40
        # recent(12:00) >= 11:40: YES, old(11:40) >= 11:40: YES → 2件
        result = manager.filter_recent_annotations(annotations, minutes_threshold=20)
        assert len(result["tags"]) == 2

    def test_filter_all_annotation_types(self, manager: ImageDatabaseManager) -> None:
        """全てのアノテーションタイプがフィルタリングされる"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time - timedelta(minutes=1)

        annotations = {
            "tags": [{"tag": "tag1", "updated_at": recent}],
            "captions": [{"text": "caption1", "updated_at": recent}],
            "scores": [{"score": 0.8, "updated_at": recent}],
            "ratings": [{"rating": 5, "updated_at": recent}],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        assert len(result["tags"]) == 1
        assert len(result["captions"]) == 1
        assert len(result["scores"]) == 1
        assert len(result["ratings"]) == 1

    def test_filter_string_timestamps(self, manager: ImageDatabaseManager) -> None:
        """文字列フォーマットのタイムスタンプでフィルタリング"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent_iso = base_time.isoformat()

        annotations = {
            "tags": [{"tag": "tag1", "updated_at": recent_iso}],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        assert len(result["tags"]) == 1

    def test_filter_preserves_annotation_data(self, manager: ImageDatabaseManager) -> None:
        """フィルタリング後、アノテーションデータが保持される"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        recent = base_time - timedelta(minutes=1)

        tag_data = {
            "tag": "test_tag",
            "model_id": 1,
            "confidence_score": 0.95,
            "updated_at": recent,
        }

        annotations = {
            "tags": [tag_data],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations)

        assert result["tags"][0] == tag_data

    def test_filter_boundary_condition_at_threshold(self, manager: ImageDatabaseManager) -> None:
        """閾値と同じ時刻のアノテーションが含まれる"""
        base_time = datetime(2026, 2, 13, 12, 0, 0, tzinfo=UTC)
        exactly_at_threshold = base_time - timedelta(minutes=5)

        annotations = {
            "tags": [{"tag": "tag1", "updated_at": exactly_at_threshold}],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        result = manager.filter_recent_annotations(annotations, minutes_threshold=5)

        # 閾値と同じ時刻は >= で判定されるため含まれるはず
        assert len(result["tags"]) == 1
