"""ServiceContainer での signal_manager 自動切り替えテスト"""

import os
import pytest

from lorairo.services.service_container import ServiceContainer
from lorairo.services.noop_signal_manager import NoOpSignalManager
from lorairo.services.signal_manager_service import SignalManagerService


@pytest.mark.unit
class TestServiceContainerSignalManager:
    """ServiceContainer での signal_manager 管理テスト"""

    def teardown_method(self) -> None:
        """テスト後のクリーンアップ"""
        container = ServiceContainer()
        container.reset_container()
        # 環境変数をクリア
        os.environ.pop("LORAIRO_CLI_MODE", None)

    def test_signal_manager_gui_mode_default(self) -> None:
        """デフォルト（GUI モード）での signal_manager 取得"""
        # 環境変数が設定されていない場合は GUI モード
        os.environ.pop("LORAIRO_CLI_MODE", None)

        container = ServiceContainer()
        signal_manager = container.signal_manager

        # GUI モードでは SignalManagerService が返される
        assert isinstance(signal_manager, SignalManagerService)
        assert not isinstance(signal_manager, NoOpSignalManager)

    def test_signal_manager_cli_mode_true(self) -> None:
        """CLI モード（環境変数 true）での signal_manager 取得"""
        os.environ["LORAIRO_CLI_MODE"] = "true"

        # 新しいコンテナを作成
        ServiceContainer().reset_container()
        container = ServiceContainer()

        signal_manager = container.signal_manager

        # CLI モードでは NoOpSignalManager が返される
        assert isinstance(signal_manager, NoOpSignalManager)
        assert not isinstance(signal_manager, SignalManagerService)

    def test_signal_manager_cli_mode_1(self) -> None:
        """CLI モード（環境変数 1）での signal_manager 取得"""
        os.environ["LORAIRO_CLI_MODE"] = "1"

        # 新しいコンテナを作成
        ServiceContainer().reset_container()
        container = ServiceContainer()

        signal_manager = container.signal_manager

        # CLI モードでは NoOpSignalManager が返される
        assert isinstance(signal_manager, NoOpSignalManager)

    def test_signal_manager_lazy_initialization(self) -> None:
        """signal_manager の遅延初期化確認"""
        container = ServiceContainer()

        # 初期状態では _signal_manager は None
        assert container._signal_manager is None

        # 最初のアクセスで初期化
        signal_manager1 = container.signal_manager
        assert container._signal_manager is not None

        # 2回目のアクセスで同じインスタンスが返される
        signal_manager2 = container.signal_manager
        assert signal_manager1 is signal_manager2

    def test_signal_manager_in_service_summary(self) -> None:
        """get_service_summary に signal_manager が含まれるか確認"""
        container = ServiceContainer()
        summary = container.get_service_summary()

        assert "initialized_services" in summary
        assert "signal_manager" in summary["initialized_services"]

        # signal_manager にアクセスして初期化
        _ = container.signal_manager

        # 再度サマリーを取得
        summary = container.get_service_summary()
        assert summary["initialized_services"]["signal_manager"] is True

    def test_signal_manager_reset(self) -> None:
        """reset_container で signal_manager がリセットされるか確認"""
        container = ServiceContainer()

        # signal_manager を初期化
        signal_manager1 = container.signal_manager
        assert container._signal_manager is not None

        # reset_container を実行
        container.reset_container()

        # リセット後は別のコンテナとなる（シングルトン特性）
        container2 = ServiceContainer()
        signal_manager2 = container2.signal_manager

        # 異なるインスタンスとなるはず
        assert signal_manager1 is not signal_manager2

    def test_signal_manager_environment_detection(self) -> None:
        """環境変数による正しいモード検出"""
        test_cases = [
            ("", SignalManagerService),  # 未設定
            ("0", SignalManagerService),  # false相当
            ("false", SignalManagerService),  # false
            ("true", NoOpSignalManager),  # true
            ("1", NoOpSignalManager),  # 1
            ("TRUE", NoOpSignalManager),  # 大文字
            ("True", NoOpSignalManager),  # 混合大小文字
        ]

        for env_value, expected_type in test_cases:
            # コンテナをリセット
            ServiceContainer().reset_container()

            # 環境変数を設定
            if env_value:
                os.environ["LORAIRO_CLI_MODE"] = env_value
            else:
                os.environ.pop("LORAIRO_CLI_MODE", None)

            # 新しいコンテナを作成
            container = ServiceContainer()
            signal_manager = container.signal_manager

            assert isinstance(signal_manager, expected_type), (
                f"env_value='{env_value}': expected {expected_type.__name__}, "
                f"got {type(signal_manager).__name__}"
            )

    def test_service_summary_includes_environment(self) -> None:
        """service_summary に environment 情報が含まれるか確認"""
        os.environ.pop("LORAIRO_CLI_MODE", None)

        container = ServiceContainer()
        summary = container.get_service_summary()

        assert "environment" in summary
        assert summary["environment"] in ("GUI", "CLI")

        # GUI モードの確認
        assert summary["environment"] == "GUI"
