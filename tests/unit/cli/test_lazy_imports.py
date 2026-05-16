"""CLI 起動時の eager import 抑制 test (Issue #264)。

Windows 古い CPU 環境で polars._cpu_check が ``unknown feature flag: 'sse3'`` で起動
失敗する問題を回避するため、``lorairo.database.db_repository`` は ``genai-tag-db-tools``
を **module-level で import しない** 設計になっている。本 test は CI で
regression (再 eager 化) を検知する。

実行方法は subprocess で fresh Python interpreter を起動して ``import lorairo.cli.main`` 後の
``sys.modules`` を確認する。pytest セッションには既に他 test 経由で genai-tag-db-tools が
ロード済の可能性があるため、subprocess による隔離が必須。
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.unit
@pytest.mark.cli
def test_cli_main_does_not_eagerly_import_genai_tag_db_tools() -> None:
    """Issue #264: ``import lorairo.cli.main`` で genai-tag-db-tools がロードされない。

    db_repository.py は ``from genai_tag_db_tools import ...`` を module-level に置かない
    (TYPE_CHECKING / function-level に移動済)。これにより polars eager import が回避でき、
    Windows 古い CPU 環境で ``models list`` / ``status`` が起動できる。
    """
    script = (
        "import sys; "
        "import lorairo.cli.main; "
        "assert 'genai_tag_db_tools' not in sys.modules, "
        "    'genai_tag_db_tools should not be eager-imported (Issue #264)'; "
        "assert 'genai_tag_db_tools.db.repository' not in sys.modules, "
        "    'genai_tag_db_tools.db.repository should not be eager-imported (Issue #264)'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"genai-tag-db-tools eager import detected.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.unit
@pytest.mark.cli
def test_db_repository_import_does_not_load_genai_tag_db_tools() -> None:
    """Issue #264: ``import lorairo.database.db_repository`` 単体でも genai-tag-db-tools 不要。

    db_repository module 自体の import は SQLAlchemy ORM の定義 / ImageRepository クラスの
    定義のみで、genai-tag-db-tools のシンボルは型 hint (TYPE_CHECKING) と関数 body 内 (function-level
    import) でしか参照されない。
    """
    script = (
        "import sys; "
        "import lorairo.database.db_repository; "
        "assert 'genai_tag_db_tools' not in sys.modules, "
        "    'db_repository module load should not trigger genai_tag_db_tools (Issue #264)'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"db_repository eager imports genai-tag-db-tools.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
