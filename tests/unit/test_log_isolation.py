"""pytest 実行中にアプリ本体 ``logs/lorairo.log`` / CLI ``logs/lorairo-cli.log`` へ
loguru file sink が書き込まないことを保証する回帰テスト (Issue #578 / #1176)。

loguru の ``logger`` はプロセスグローバルな singleton のため、ある test が
実 ``logs/lorairo.log`` 宛の file sink を追加すると、その後の全 test の loguru
ログが同ファイルへ追記され、実運用エラー調査のノイズになる。
``tests/conftest.py`` の session-autouse fixture ``_redirect_real_log_sink`` が
実 ``DEFAULT_LOG_PATH`` / ``DEFAULT_CLI_LOG_PATH`` 宛の file sink を session tmp へ
転送することで、これを防ぐ。
"""

from pathlib import Path

import pytest
from loguru import logger

from lorairo.utils.config import DEFAULT_CLI_LOG_PATH, DEFAULT_LOG_PATH
from lorairo.utils.log import build_gui_log_config, initialize_logging


@pytest.mark.unit
def test_initialize_logging_does_not_write_to_real_app_log() -> None:
    """実 config で initialize_logging を呼んでもアプリ本体ログが増えない。

    redirect fixture が無い場合、initialize_logging が実 ``logs/lorairo.log`` 宛の
    file sink を追加し、後続の ``logger.error`` でファイルが増加する (= 汚染)。
    fixture 有効時は tmp へ転送されるため実ファイルは不変。
    """
    real_log = Path(DEFAULT_LOG_PATH)
    size_before = real_log.stat().st_size if real_log.exists() else 0

    # build_gui_log_config は file_path に実 DEFAULT_LOG_PATH を設定する
    initialize_logging(build_gui_log_config({"log": {"level": "DEBUG"}}))
    logger.error("Issue #578 regression probe: must NOT reach the real app log")
    logger.complete()  # enqueue=True の file sink を flush

    size_after = real_log.stat().st_size if real_log.exists() else 0
    assert size_after == size_before, (
        f"アプリ本体ログ {real_log} に test ログが混入した (before={size_before}, after={size_after})"
    )


@pytest.mark.unit
def test_cli_invocation_does_not_write_to_real_cli_log() -> None:
    """CLI 実行 (callback 経由の initialize_logging) が本番 CLI ログを汚染しない (Issue #1176)。

    CLI e2e テストは CliRunner 経由で ``_configure`` callback を実行し、そこで
    ``initialize_logging`` が CLI ログ file sink を張る。conftest の
    ``LORAIRO_CLI_LOG_PATH`` env + ``guarded_add`` 転送が無いと、テストの
    WARNING/ERROR が実 ``logs/lorairo-cli.log`` に追記される (195 件/日の実害)。
    """
    from typer.testing import CliRunner

    from lorairo.cli.main import app

    real_cli_log = Path(DEFAULT_CLI_LOG_PATH)
    size_before = real_cli_log.stat().st_size if real_cli_log.exists() else 0

    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    logger.error("Issue #1176 regression probe: must NOT reach the real CLI log")
    logger.complete()  # enqueue=True の file sink を flush

    size_after = real_cli_log.stat().st_size if real_cli_log.exists() else 0
    assert size_after == size_before, (
        f"本番 CLI ログ {real_cli_log} に test ログが混入した (before={size_before}, after={size_after})"
    )


@pytest.mark.unit
def test_cli_log_path_env_override_is_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LORAIRO_CLI_LOG_PATH が CLI ログの書き込み先として使われる (Issue #1176)。"""
    from typer.testing import CliRunner

    from lorairo.cli.main import app

    override = tmp_path / "cli-override.log"
    monkeypatch.setenv("LORAIRO_CLI_LOG_PATH", str(override))

    result = CliRunner().invoke(app, ["--log-level", "DEBUG", "version"])
    assert result.exit_code == 0
    logger.debug("Issue #1176 env override probe")
    logger.complete()

    assert override.exists(), "LORAIRO_CLI_LOG_PATH が無視され override 先にログが作られなかった"
