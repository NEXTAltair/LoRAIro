"""CLI import 軽量性のリグレッションテスト (Issue #540)。

`import lorairo.cli.main` (= `lorairo-cli --help` 相当の import) が
image-annotator-lib registry 初期化や litellm の重い import を引き起こさないことを
検証する。これらを module-import 時にロードすると `--help` が数秒かかる (#540)。

検証は **subprocess** 経由で行う。pytest セッションの conftest が
`image_annotator_lib` を `sys.modules` に inject (mock 化) しているため、
in-process では「ロード済み」と誤検出する。fresh interpreter で確認する必要がある。
"""

import json
import os
import subprocess
import sys
from typing import Any

import pytest

# 子プロセスは親と同じ sys.path を継承し、同一の lorairo / local package を解決する。
# (venv の editable install path が stale なケースでも親 path で確実に解決できる)
_CHILD_ENV = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join(sys.path),
    "LORAIRO_CLI_MODE": "true",
}


# 4 つの観測を 1 回の fresh interpreter で採る (cold import は 1 回 5 秒前後かかる)。
# 観測順は import 直後 (probe 1〜3) → CliRunner 実行後 (probe 4) で、元の個別 probe と同じ状態を見る。
_PROBE = """
import json
import sys

import lorairo.cli.main

def loaded(*needles):
    return sorted(m for m in sys.modules if any(needle in m for needle in needles))

after_import = {
    "image_annotator_lib": loaded("image_annotator_lib"),
    "litellm": "litellm" in sys.modules,
}

import typer
from lorairo.cli.main import app

app_is_typer = isinstance(app, typer.Typer)
after_app = loaded("image_annotator_lib")

from typer.testing import CliRunner

runner = CliRunner()
help_exit = runner.invoke(app, ["images", "crop-detect", "--help"]).exit_code
describe_exit = runner.invoke(app, ["--json", "describe", "images crop-detect"]).exit_code
print(json.dumps({
    "after_import": after_import,
    "app_is_typer": app_is_typer,
    "after_app": after_app,
    "help_exit": help_exit,
    "describe_exit": describe_exit,
    "after_invoke": loaded("image_annotator_lib", "onnxruntime"),
}))
"""


@pytest.fixture(scope="module")
def probe() -> dict[str, Any]:
    """fresh interpreter で import 状態を観測し、最終行の JSON を返す。"""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=_CHILD_ENV,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    observed: dict[str, Any] = json.loads(result.stdout.splitlines()[-1])
    return observed


@pytest.mark.unit
@pytest.mark.cli
def test_import_main_does_not_load_image_annotator_lib(probe: dict[str, Any]) -> None:
    """Test: `import lorairo.cli.main` で image_annotator_lib がロードされない。"""
    loaded = probe["after_import"]["image_annotator_lib"]
    assert not loaded, f"unexpected eager import: {loaded}"


@pytest.mark.unit
@pytest.mark.cli
def test_import_main_does_not_load_litellm(probe: dict[str, Any]) -> None:
    """Test: `import lorairo.cli.main` で litellm がロードされない。"""
    assert probe["after_import"]["litellm"] is False, "litellm eagerly imported"


@pytest.mark.unit
@pytest.mark.cli
def test_app_object_available_without_heavy_imports(probe: dict[str, Any]) -> None:
    """Test: Typer `app` オブジェクトは重い import なしで利用可能。"""
    assert probe["app_is_typer"] is True
    assert probe["after_app"] == []


@pytest.mark.unit
@pytest.mark.cli
def test_crop_detect_help_and_describe_do_not_load_detector_runtime(probe: dict[str, Any]) -> None:
    """Test: `images crop-detect --help` と describe は検出器 (lib / onnxruntime) を読まない (ADR 0110)。"""
    assert probe["help_exit"] == 0
    assert probe["describe_exit"] == 0
    loaded = probe["after_invoke"]
    assert not loaded, f"unexpected eager import: {loaded}"
