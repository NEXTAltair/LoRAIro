"""ServiceContainer の refinement ignore 保存先ルーティングテスト (#978)。

ignore 保存先を、呼び出し側 (タブ/詳細ペインに注入された db_manager) の session factory に
追従させる ``create_refinement_service`` の挙動と、MainWindow 経路 (db_manager=container.db_manager)
がアクティブ DB と一致する不変条件を検証する。DB I/O を伴わないオブジェクト同一性のみを確認する。
"""

from __future__ import annotations

import pytest

from lorairo.services.service_container import ServiceContainer

pytestmark = pytest.mark.unit


def test_create_refinement_service_binds_given_session_factory() -> None:
    """create_refinement_service は渡された session factory を ignore repo に束ねる (#978)。"""
    container = ServiceContainer()
    sentinel_factory = object()  # RefinementIgnoreRepository は callable 性を要求せず保持のみ

    service = container.create_refinement_service(sentinel_factory)  # type: ignore[arg-type]

    assert service._ignore_repo.session_factory is sentinel_factory  # type: ignore[attr-defined]


def test_refinement_service_property_uses_active_image_repository_factory() -> None:
    """refinement_service プロパティはアクティブ DB (image_repository) の factory を使う (#931)。"""
    container = ServiceContainer()

    service = container.refinement_service

    assert (
        service._ignore_repo.session_factory  # type: ignore[attr-defined]
        is container.image_repository.session_factory
    )


def test_main_window_path_db_manager_matches_active_db() -> None:
    """MainWindow 経路 (db_manager=container.db_manager) は active DB と同じ factory を指す (#978 回帰)。

    MainWindow はタブへ ``db_manager=service_container.db_manager`` を注入する。タブが
    ``db_manager.image_repo.session_factory`` で ignore を保存しても、それが container の
    アクティブ DB (refinement_service プロパティが使う factory) と一致することを保証する。
    """
    container = ServiceContainer()

    assert container.db_manager.image_repo.session_factory is container.image_repository.session_factory
