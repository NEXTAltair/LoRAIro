"""pytest 実行中にアプリ本体 ``logs/lorairo.log`` へ loguru file sink が
書き込まないことを保証する回帰テスト (Issue #578)。

loguru の ``logger`` はプロセスグローバルな singleton のため、ある test が
実 ``logs/lorairo.log`` 宛の file sink を追加すると、その後の全 test の loguru
ログが同ファイルへ追記され、実運用エラー調査のノイズになる。
``tests/conftest.py`` の session-autouse fixture ``_redirect_real_log_sink`` が
実 ``DEFAULT_LOG_PATH`` 宛の file sink を session tmp へ転送することで、これを防ぐ。
"""

from pathlib import Path

import pytest
from loguru import logger

from lorairo.utils.config import DEFAULT_LOG_PATH
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
