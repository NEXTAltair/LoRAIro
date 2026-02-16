"""FavoriteFiltersServiceの単体テスト"""

from unittest.mock import Mock, patch

import pytest

from lorairo.services.favorite_filters_service import FavoriteFiltersService


@pytest.mark.unit
class TestFavoriteFiltersService:
    """FavoriteFiltersServiceのテストクラス"""

    @pytest.fixture
    def service(self) -> FavoriteFiltersService:
        """FavoriteFiltersServiceインスタンスを提供（テスト用QSettings）"""
        # テスト用に一時的なQSettings使用
        service = FavoriteFiltersService(organization="LoRAIroTest", application="TestApp")
        # テスト開始時にクリア
        service.clear_all_filters()
        return service

    @pytest.fixture
    def sample_filter(self) -> dict[str, str | bool]:
        """サンプルフィルター条件"""
        return {
            "search_type": "tags",
            "keywords": ["character", "1girl"],
            "tag_logic": "and",
            "resolution_filter": "1024x1024",
            "date_filter_enabled": True,
        }

    def test_save_filter_success(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター保存成功"""
        result = service.save_filter("Test Filter", sample_filter)

        assert result is True
        assert service.filter_exists("Test Filter") is True

    def test_save_filter_empty_name(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """空のフィルター名でエラー"""
        with pytest.raises(ValueError, match="Filter name cannot be empty"):
            service.save_filter("", sample_filter)

        with pytest.raises(ValueError, match="Filter name cannot be empty"):
            service.save_filter("   ", sample_filter)

    def test_save_filter_overwrite(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター上書き保存"""
        # 初回保存
        service.save_filter("Test Filter", sample_filter)

        # 上書き保存
        updated_filter = sample_filter.copy()
        updated_filter["search_type"] = "caption"
        result = service.save_filter("Test Filter", updated_filter)

        assert result is True

        # 上書きされたことを確認
        loaded = service.load_filter("Test Filter")
        assert loaded is not None
        assert loaded["search_type"] == "caption"

    def test_save_filter_serialization_error(self, service: FavoriteFiltersService) -> None:
        """シリアライズ不可能なデータでエラー"""
        # JSONシリアライズ不可能なオブジェクト
        invalid_filter = {"func": lambda x: x}  # type: ignore[dict-item]

        result = service.save_filter("Invalid Filter", invalid_filter)
        assert result is False

    def test_load_filter_success(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター読み込み成功"""
        service.save_filter("Test Filter", sample_filter)

        loaded = service.load_filter("Test Filter")

        assert loaded is not None
        assert loaded["search_type"] == sample_filter["search_type"]
        assert loaded["keywords"] == sample_filter["keywords"]
        assert loaded["tag_logic"] == sample_filter["tag_logic"]

    def test_load_filter_not_found(self, service: FavoriteFiltersService) -> None:
        """存在しないフィルター読み込み"""
        loaded = service.load_filter("NonExistent")

        assert loaded is None

    def test_load_filter_empty_name(self, service: FavoriteFiltersService) -> None:
        """空のフィルター名で読み込み"""
        loaded = service.load_filter("")
        assert loaded is None

        loaded = service.load_filter("   ")
        assert loaded is None

    def test_load_filter_deserialization_error(self, service: FavoriteFiltersService) -> None:
        """デシリアライズエラーハンドリング"""
        # JSON ファイルに直接不正なJSONを書き込み
        service._filters_file.write_text("not a valid json", encoding="utf-8")

        loaded = service.load_filter("Broken Filter")
        assert loaded is None

    def test_list_filters_success(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター一覧取得成功"""
        # 複数保存
        service.save_filter("Filter A", sample_filter)
        service.save_filter("Filter C", sample_filter)
        service.save_filter("Filter B", sample_filter)

        filters = service.list_filters()

        assert len(filters) == 3
        # アルファベット順にソート
        assert filters == ["Filter A", "Filter B", "Filter C"]

    def test_list_filters_empty(self, service: FavoriteFiltersService) -> None:
        """フィルター一覧が空"""
        filters = service.list_filters()
        assert filters == []

    def test_delete_filter_success(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター削除成功"""
        service.save_filter("Test Filter", sample_filter)
        assert service.filter_exists("Test Filter") is True

        result = service.delete_filter("Test Filter")

        assert result is True
        assert service.filter_exists("Test Filter") is False

    def test_delete_filter_not_found(self, service: FavoriteFiltersService) -> None:
        """存在しないフィルター削除"""
        result = service.delete_filter("NonExistent")
        assert result is False

    def test_delete_filter_empty_name(self, service: FavoriteFiltersService) -> None:
        """空のフィルター名で削除"""
        result = service.delete_filter("")
        assert result is False

        result = service.delete_filter("   ")
        assert result is False

    def test_filter_exists_true(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """フィルター存在確認：存在する"""
        service.save_filter("Test Filter", sample_filter)

        assert service.filter_exists("Test Filter") is True

    def test_filter_exists_false(self, service: FavoriteFiltersService) -> None:
        """フィルター存在確認：存在しない"""
        assert service.filter_exists("NonExistent") is False

    def test_filter_exists_empty_name(self, service: FavoriteFiltersService) -> None:
        """フィルター存在確認：空の名前"""
        assert service.filter_exists("") is False
        assert service.filter_exists("   ") is False

    def test_clear_all_filters(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """全フィルタークリア"""
        # 複数保存
        service.save_filter("Filter 1", sample_filter)
        service.save_filter("Filter 2", sample_filter)
        service.save_filter("Filter 3", sample_filter)

        assert len(service.list_filters()) == 3

        result = service.clear_all_filters()

        assert result is True
        assert len(service.list_filters()) == 0

    def test_save_load_roundtrip(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """保存→読み込みのラウンドトリップテスト"""
        service.save_filter("Roundtrip Filter", sample_filter)

        loaded = service.load_filter("Roundtrip Filter")

        assert loaded is not None
        assert loaded == sample_filter

    def test_unicode_filter_name(
        self, service: FavoriteFiltersService, sample_filter: dict[str, str | bool]
    ) -> None:
        """日本語フィルター名の保存・読み込み"""
        japanese_name = "お気に入りフィルター１"

        result = service.save_filter(japanese_name, sample_filter)
        assert result is True

        loaded = service.load_filter(japanese_name)
        assert loaded is not None
        assert loaded == sample_filter

        assert japanese_name in service.list_filters()

    def test_special_characters_in_values(self, service: FavoriteFiltersService) -> None:
        """特殊文字を含む値の保存・読み込み"""
        special_filter = {
            "keywords": ["tag with spaces", "tag/with/slashes", 'tag"with"quotes'],
            "description": "Filter with 特殊文字 and symbols: !@#$%^&*()",
        }

        result = service.save_filter("Special Filter", special_filter)
        assert result is True

        loaded = service.load_filter("Special Filter")
        assert loaded is not None
        assert loaded == special_filter

    def test_service_persistence_across_instances(self, sample_filter: dict[str, str | bool]) -> None:
        """別インスタンスでの永続性確認"""
        # インスタンス1で保存
        service1 = FavoriteFiltersService(organization="LoRAIroTest", application="PersistenceTest")
        service1.clear_all_filters()
        service1.save_filter("Persistent Filter", sample_filter)

        # インスタンス2で読み込み
        service2 = FavoriteFiltersService(organization="LoRAIroTest", application="PersistenceTest")
        loaded = service2.load_filter("Persistent Filter")

        assert loaded is not None
        assert loaded == sample_filter

        # クリーンアップ
        service2.clear_all_filters()


@pytest.mark.unit
class TestFavoriteFiltersServiceEdgeCases:
    """FavoriteFiltersServiceのエッジケーステスト"""

    @pytest.fixture
    def service(self) -> FavoriteFiltersService:
        """FavoriteFiltersServiceインスタンスを提供（テスト用QSettings）"""
        service = FavoriteFiltersService(organization="LoRAIroTest", application="EdgeCaseTest")
        service.clear_all_filters()
        return service

    def test_save_empty_dict(self, service: FavoriteFiltersService) -> None:
        """空の辞書を保存"""
        result = service.save_filter("Empty Filter", {})
        assert result is True

        loaded = service.load_filter("Empty Filter")
        assert loaded == {}

    def test_save_nested_dict(self, service: FavoriteFiltersService) -> None:
        """ネストされた辞書を保存"""
        nested_filter = {
            "level1": {
                "level2": {
                    "level3": ["value1", "value2"],
                }
            }
        }

        result = service.save_filter("Nested Filter", nested_filter)
        assert result is True

        loaded = service.load_filter("Nested Filter")
        assert loaded == nested_filter

    def test_save_with_none_values(self, service: FavoriteFiltersService) -> None:
        """None値を含む辞書を保存"""
        filter_with_none = {
            "key1": "value1",
            "key2": None,
            "key3": 123,
        }

        result = service.save_filter("Filter With None", filter_with_none)
        assert result is True

        loaded = service.load_filter("Filter With None")
        assert loaded == filter_with_none

    def test_very_long_filter_name(self, service: FavoriteFiltersService) -> None:
        """非常に長いフィルター名"""
        long_name = "A" * 500

        result = service.save_filter(long_name, {"test": "value"})
        assert result is True

        loaded = service.load_filter(long_name)
        assert loaded is not None

    def test_large_filter_data(self, service: FavoriteFiltersService) -> None:
        """大量のデータを含むフィルター"""
        large_filter = {
            "tags": [f"tag_{i}" for i in range(1000)],
            "metadata": {f"key_{i}": f"value_{i}" for i in range(100)},
        }

        result = service.save_filter("Large Filter", large_filter)
        assert result is True

        loaded = service.load_filter("Large Filter")
        assert loaded == large_filter
