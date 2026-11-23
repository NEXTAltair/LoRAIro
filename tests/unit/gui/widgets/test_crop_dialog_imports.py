"""CropDialog / CropRectSelectorWidget の DB・サービス非依存を検査する (#1345)。

受け入れ条件「ダイアログのモジュールが DB・サービスを import しない」を 2 段で守る:

1. ソース上の直接 import (関数内の遅延 import も含む) を AST で検査する。
2. 実際にサブプロセスで import し、``sys.modules`` に新しく増えるモジュールを検査する。
   ``lorairo.gui.widgets`` パッケージの ``__init__`` が FilterSearchPanel /
   ProviderBatchJobWidget を eager import しており、そこで既に service 系が載る。
   ここで検査したいのは「crop_* モジュール自身が増やすか」なので、パッケージを先に
   import した状態を baseline として差分を見る。
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.gui]

FORBIDDEN_PREFIXES = (
    "lorairo.database",
    "lorairo.services",
    "lorairo.gui.services",
    "lorairo.gui.workers",
)

WIDGETS_PACKAGE = "lorairo.gui.widgets"
SRC_DIR = Path(__file__).resolve().parents[4] / "src"
TARGET_MODULES = (
    "crop_dialog",
    "crop_rect_selector",
    "crop_tag_list_widget",
)


def _resolve_relative(module: str | None, level: int, names: list[str]) -> list[str]:
    """相対 import を絶対モジュール名へ解決する。

    Args:
        module: ``from X import ...`` の X 部分 (``from . import y`` なら None)。
        level: 相対レベル (``.`` の個数)。0 なら絶対 import。
        names: import される名前。module が None のときはサブモジュール候補として扱う。

    Returns:
        絶対モジュール名のリスト。
    """
    parts = WIDGETS_PACKAGE.split(".")
    base = ".".join(parts[: len(parts) - (level - 1)]) if level > 1 else WIDGETS_PACKAGE
    if module:
        return [f"{base}.{module}"]
    return [f"{base}.{name}" for name in names]


def _imported_modules(path: Path) -> set[str]:
    """モジュールが直接 import している絶対モジュール名を集める。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    modules.add(node.module)
                continue
            modules.update(_resolve_relative(node.module, node.level, [alias.name for alias in node.names]))
    return modules


@pytest.mark.parametrize("module_name", TARGET_MODULES)
def test_source_has_no_db_or_service_import(module_name: str) -> None:
    """ソース上で DB / サービスモジュールを直接 import していない。"""
    path = SRC_DIR / "lorairo" / "gui" / "widgets" / f"{module_name}.py"
    forbidden = sorted(
        imported for imported in _imported_modules(path) if imported.startswith(FORBIDDEN_PREFIXES)
    )
    assert forbidden == [], f"{module_name} が DB/サービスを import している: {forbidden}"


_IMPORT_PROBE_SNIPPET = (
    "import json, sys\n"
    # パッケージ __init__ の副作用を baseline に含める
    "import lorairo.gui.widgets\n"
    "baseline = set(sys.modules)\n"
    "import lorairo.gui.widgets.crop_dialog\n"
    "import lorairo.gui.widgets.crop_rect_selector\n"
    "import lorairo.gui.widgets.crop_tag_list_widget\n"
    f"prefixes = {FORBIDDEN_PREFIXES!r}\n"
    "added = sorted(m for m in set(sys.modules) - baseline if m.startswith(prefixes))\n"
    "print(json.dumps(added))\n"
)

_import_probe: subprocess.Popen[str] | None = None
"""起動済みの import 検査サブプロセス (未起動なら None)。"""


def start_import_probe() -> None:
    """import 検査のサブプロセスを起動する (起動済みなら何もしない)。

    新しいインタプリタでの cold import に数秒かかるため、tests/unit/gui/conftest.py が
    収集直後にこれを呼び、他のテストと並行して走らせる。検査内容は
    ``test_import_adds_no_db_or_service_modules`` で結果を待つときと同じ。
    """
    global _import_probe
    if _import_probe is not None:
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env["QT_QPA_PLATFORM"] = "offscreen"
    _import_probe = subprocess.Popen(
        [sys.executable, "-c", _IMPORT_PROBE_SNIPPET],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def stop_import_probe() -> None:
    """結果を待たれずに残ったサブプロセスを終了させる (``-x`` で途中終了した場合など)。"""
    if _import_probe is not None and _import_probe.poll() is None:
        _import_probe.kill()
        _import_probe.communicate()


def test_import_adds_no_db_or_service_modules() -> None:
    """import 実行時にも DB / サービスモジュールを新たに読み込まない。"""
    start_import_probe()
    assert _import_probe is not None
    stdout, stderr = _import_probe.communicate(timeout=180)
    assert _import_probe.returncode == 0, f"import に失敗しました: {stderr}"
    added = json.loads(stdout.strip().splitlines()[-1])
    assert added == [], f"crop_* の import が DB/サービスを引き込んでいる: {added}"
