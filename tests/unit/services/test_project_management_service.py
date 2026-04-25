"""ProjectManagementService ユニットテスト — 旧ディレクトリ移行案内ログ (シナリオH)。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.services.project_management_service import ProjectManagementService


@pytest.mark.unit
def test_old_projects_dir_detected_logs_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 ~/.lorairo/projects/ が存在する場合に INFO ログを出力する。"""
    # 旧ディレクトリを作成
    old_dir = tmp_path / ".lorairo" / "projects"
    old_dir.mkdir(parents=True)

    # Path.home() を差し替え
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # get_config をモック
    def mock_get_config() -> MagicMock:
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {"database_base_dir": str(tmp_path / "lorairo_data")}
        return mock_cfg

    monkeypatch.setattr("lorairo.services.project_management_service.get_config", mock_get_config)

    with patch("lorairo.services.project_management_service.logger") as mock_logger:
        ProjectManagementService()

    assert mock_logger.info.call_count == 1
    call_args = mock_logger.info.call_args[0][0]
    assert "旧プロジェクトディレクトリが検出されました" in call_args


@pytest.mark.unit
def test_no_old_projects_dir_no_info_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 ~/.lorairo/projects/ が存在しない場合に INFO ログを出力しない。"""
    # .lorairo/projects は作らない

    # Path.home() を差し替え
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # get_config をモック
    def mock_get_config() -> MagicMock:
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {"database_base_dir": str(tmp_path / "lorairo_data")}
        return mock_cfg

    monkeypatch.setattr("lorairo.services.project_management_service.get_config", mock_get_config)

    with patch("lorairo.services.project_management_service.logger") as mock_logger:
        ProjectManagementService()

    mock_logger.info.assert_not_called()
