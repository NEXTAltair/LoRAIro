"""TagManagement統合テスト

ServiceContainer → TagManagementService → genai-tag-db-tools の連携を検証
"""

import pytest

from lorairo.services.service_container import ServiceContainer


@pytest.mark.integration
class TestTagManagementIntegration:
    """TagManagement統合テストクラス"""

    @pytest.fixture
    def service_container(self) -> ServiceContainer:
        """ServiceContainer インスタンスを提供"""
        container = ServiceContainer()
        yield container
        # Cleanup
        container.reset_container()

    def test_service_container_provides_tag_management_service(
        self, service_container: ServiceContainer
    ) -> None:
        """ServiceContainer が TagManagementService を提供すること"""
        service = service_container.tag_management_service

        assert service is not None
        assert service.LORAIRO_FORMAT_ID == 1000
        assert service.reader is not None
        assert service.repository is not None

    def test_tag_management_service_get_all_type_names(self, service_container: ServiceContainer) -> None:
        """get_all_available_types() が型名リストを返すこと"""
        service = service_container.tag_management_service

        types = service.get_all_available_types()

        assert isinstance(types, list)
        assert len(types) > 0
        # 基本的な型が含まれること
        assert "unknown" in types

    def test_tag_management_service_get_format_specific_types(
        self, service_container: ServiceContainer
    ) -> None:
        """get_format_specific_types() が format固有型名を返すこと"""
        service = service_container.tag_management_service

        # LoRAIro format (1000) の型名取得
        types = service.get_format_specific_types()

        assert isinstance(types, list)
        # format_id=1000 が未登録の場合は空リスト、登録済みの場合は型名リスト
        # テスト環境では空の可能性もあるため、型のみ検証
        assert all(isinstance(t, str) for t in types)

    def test_tag_management_service_get_unknown_tags(self, service_container: ServiceContainer) -> None:
        """get_unknown_tags() が unknown type タグリストを返すこと"""
        service = service_container.tag_management_service

        # unknown type タグ取得
        tags = service.get_unknown_tags()

        assert isinstance(tags, list)
        # テスト環境では unknown type タグが存在しない可能性もある
        # 空リストまたはタグリストのいずれか
        for tag in tags:
            assert tag.type_name == "unknown"
            assert tag.tag_id is not None
            assert tag.tag is not None

    def test_tag_management_service_update_tag_types_empty(
        self, service_container: ServiceContainer
    ) -> None:
        """update_tag_types() が空リストを処理できること"""
        service = service_container.tag_management_service

        # 空リストで更新（エラーにならないこと）
        service.update_tag_types([])

        # 正常終了すること（例外が発生しない）

    def test_service_summary_includes_tag_management_service(
        self, service_container: ServiceContainer
    ) -> None:
        """ServiceContainer サマリーに tag_management_service が含まれること"""
        # tag_management_service を初期化
        _ = service_container.tag_management_service

        summary = service_container.get_service_summary()

        assert "initialized_services" in summary
        assert "tag_management_service" in summary["initialized_services"]
        assert summary["initialized_services"]["tag_management_service"] is True

    def test_tag_management_service_singleton_behavior(self, service_container: ServiceContainer) -> None:
        """TagManagementService がシングルトンとして動作すること"""
        service1 = service_container.tag_management_service
        service2 = service_container.tag_management_service

        # 同じインスタンスであること
        assert service1 is service2
