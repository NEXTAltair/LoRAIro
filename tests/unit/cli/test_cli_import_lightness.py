"""CLI import 軽量性のリグレッションテスト (Issue #540)。

`import lorairo.cli.main` (= `lorairo-cli --help` 相当の import) が
image-annotator-lib registry 初期化や litellm の重い import を引き起こさないことを
検証する。これらを module-import 時にロードすると `--help` が数秒かかる (#540)。

検証は **subprocess** 経由で行う。pytest セッションの conftest が
`image_annotator_lib` を `sys.modules` に inject (mock 化) しているため、
in-process では「ロード済み」と誤検出する。fresh interpreter で確認する必要がある。
"""

import os
import subprocess
import sys

import pytest

# 子プロセスは親と同じ sys.path を継承し、同一の lorairo / local package を解決する。
# (venv の editable install path が stale なケースでも親 path で確実に解決できる)
_CHILD_ENV = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join(sys.path),
    "LORAIRO_CLI_MODE": "true",
}


def _run_probe(probe: str) -> subprocess.CompletedProcess[str]:
    """fresh interpreter で probe スクリプトを実行する。"""
    return subprocess.run(
        [sys.executable, "-c", probe],
        env=_CHILD_ENV,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.unit
@pytest.mark.cli
def test_import_main_does_not_load_image_annotator_lib() -> None:
    """Test: `import lorairo.cli.main` で image_annotator_lib がロードされない。"""
    probe = (
        "import sys\n"
        "import lorairo.cli.main\n"
        "loaded = sorted(m for m in sys.modules if 'image_annotator_lib' in m)\n"
        "assert not loaded, f'unexpected eager import: {loaded}'\n"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"


@pytest.mark.unit
@pytest.mark.cli
def test_import_main_does_not_load_litellm() -> None:
    """Test: `import lorairo.cli.main` で litellm がロードされない。"""
    probe = (
        "import sys\n"
        "import lorairo.cli.main\n"
        "assert 'litellm' not in sys.modules, 'litellm eagerly imported'\n"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"


@pytest.mark.unit
@pytest.mark.cli
def test_app_object_available_without_heavy_imports() -> None:
    """Test: Typer `app` オブジェクトは重い import なしで利用可能。"""
    probe = (
        "import sys\n"
        "from lorairo.cli.main import app\n"
        "import typer\n"
        "assert isinstance(app, typer.Typer)\n"
        "assert 'image_annotator_lib' not in sys.modules\n"
    )
    result = _run_probe(probe)
    assert result.returncode == 0, f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
