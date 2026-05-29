"""GUI ランチャー (``lorairo``) の help 出力に関する unit テスト。

Issue #541: GUI ランチャーの help がバッチ/アノテーション/データセット操作に
言及していないため、``lorairo-cli`` への誘導が表示されることを検証する。
"""

import pytest

from lorairo.main import _build_gui_log_config, _build_parser
from lorairo.utils.config import DEFAULT_CLI_LOG_PATH, DEFAULT_LOG_PATH


@pytest.mark.unit
def test_help_text_guides_to_lorairo_cli() -> None:
    """help テキストに ``lorairo-cli`` への誘導が含まれることを検証する。"""
    help_text = _build_parser().format_help()
    assert "lorairo-cli" in help_text


@pytest.mark.unit
def test_help_text_retains_existing_options() -> None:
    """既存の ``--debug`` / ``--version`` の記述が help に残ることを検証する。"""
    help_text = _build_parser().format_help()
    assert "--debug" in help_text
    assert "--version" in help_text


@pytest.mark.unit
def test_gui_log_config_uses_application_log_file() -> None:
    """Issue #546: GUI 起動時は CLI 専用ログではなくアプリ本体ログを使う。"""
    config = {
        "log": {
            "level": "WARNING",
            "file_path": str(DEFAULT_CLI_LOG_PATH),
            "rotation": "10 MB",
            "levels": {"lorairo": "DEBUG"},
        }
    }

    log_config = _build_gui_log_config(config)

    assert log_config["file_path"] == str(DEFAULT_LOG_PATH)
    assert log_config["level"] == "WARNING"
    assert log_config["rotation"] == "10 MB"
    assert log_config["levels"] == {"lorairo": "DEBUG"}


@pytest.mark.unit
def test_gui_log_config_does_not_mutate_loaded_config() -> None:
    """Issue #546: GUI 用のログパス補正で読み込み済み config を変更しない。"""
    config = {"log": {"file_path": str(DEFAULT_CLI_LOG_PATH), "level": "INFO"}}

    log_config = _build_gui_log_config(config)

    assert log_config["file_path"] == str(DEFAULT_LOG_PATH)
    assert config["log"]["file_path"] == str(DEFAULT_CLI_LOG_PATH)
