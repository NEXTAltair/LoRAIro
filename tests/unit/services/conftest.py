"""services ユニットテスト共通設定。

ServiceContainer シングルトンのテスト間分離を保証する autouse fixture。
LORAIRO_CLI_MODE 環境変数や遅延初期化済みサービス状態が他テストから
漏洩しないよう、function-scope で事前・事後に reset する。
"""

import pytest

from lorairo.services.service_container import ServiceContainer


@pytest.fixture(autouse=True)
def reset_service_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """各 services テストの前後で ServiceContainer を完全リセット。

    事前リセット: 他テストで汚染された singleton/env をクリア。
    事後リセット: 次の services テストにも他ディレクトリにも状態を残さない。

    Layer 1 の修正 (cli/__init__.py の import-time 副作用除去) で
    大部分の汚染は解消されるが、明示的に env を操作するテストに
    対する防御層として機能する。
    """
    monkeypatch.delenv("LORAIRO_CLI_MODE", raising=False)
    ServiceContainer.reset_for_testing()
    yield
    ServiceContainer.reset_for_testing()
