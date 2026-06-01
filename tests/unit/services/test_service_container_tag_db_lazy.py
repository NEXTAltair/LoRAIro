"""ServiceContainer の tag DB 遅延初期化テスト。"""

from unittest.mock import MagicMock

import pytest

from lorairo.services.service_container import ServiceContainer


@pytest.mark.unit
def test_container_init_does_not_initialize_tag_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """ServiceContainer 生成だけでは genai-tag-db-tools 初期化を走らせない。"""
    ensure_spy = MagicMock()
    monkeypatch.setattr("lorairo.services.service_container.ensure_tag_db_initialized", ensure_spy)

    ServiceContainer()

    ensure_spy.assert_not_called()


@pytest.mark.unit
def test_tag_management_service_initializes_tag_db_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """タグ管理サービス取得時だけ tag DB を初期化する。"""
    ensure_spy = MagicMock()
    service_cls = MagicMock()
    service_instance = MagicMock()
    service_cls.return_value = service_instance
    monkeypatch.setattr("lorairo.services.service_container.ensure_tag_db_initialized", ensure_spy)
    monkeypatch.setattr("lorairo.services.tag_management_service.TagManagementService", service_cls)

    container = ServiceContainer()
    first = container.tag_management_service
    second = container.tag_management_service

    assert first is service_instance
    assert second is service_instance
    ensure_spy.assert_called_once()


@pytest.mark.unit
def test_db_manager_creation_does_not_initialize_tag_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB manager 生成だけでは read-only CLI のために tag DB 初期化を走らせない。"""
    ensure_spy = MagicMock()
    monkeypatch.setattr("lorairo.services.service_container.ensure_tag_db_initialized", ensure_spy)

    container = ServiceContainer()
    _ = container.db_manager

    ensure_spy.assert_not_called()
