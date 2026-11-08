"""`lorairo-cli dataset` の統合テスト (Issue #1420)。

Typer の CliRunner で、プロジェクト作成 → 取り込み → 書き出しを同一プロセスで通す。
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner, Result

from lorairo.cli.main import app
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer

pytestmark = [pytest.mark.integration, pytest.mark.cli]

PROJECT = "kohya-cli"
# CRLF・重み付き・大文字・アンダースコア・複数行を含む学習テキスト
TEXT_A = b"Trig_A, (tag:1.2), long_sleeves\r\nsecond line, Smile\r\n"
TEXT_B = b"trig_b, blue eyes"


def _save_noise_image(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    image = Image.new("RGB", (64, 64))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(64 * 64)])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner) -> Path:
    """隔離したプロジェクトディレクトリに空のプロジェクトを作る。"""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    ServiceContainer.reset_for_testing()
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=projects_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)
    result = cli_runner.invoke(app, ["project", "create", PROJECT])
    assert result.exit_code == 0, result.stdout
    return next(path for path in projects_dir.iterdir() if path.name.startswith(PROJECT))


@pytest.fixture
def kohya_root(tmp_path: Path) -> Path:
    root = tmp_path / "kohya"
    _save_noise_image(root / "10_a" / "a1.png", seed=1)
    (root / "10_a" / "a1.txt").write_bytes(TEXT_A)
    _save_noise_image(root / "5_b" / "b1.png", seed=2)
    (root / "5_b" / "b1.txt").write_bytes(TEXT_B)
    _save_noise_image(root / "sample001" / "s.png", seed=3)
    _save_noise_image(root / "3_skipme" / "k.png", seed=4)
    return root


def _import(runner: CliRunner, root: Path, *extra: str, version: str = "v1") -> int:
    result = runner.invoke(
        app,
        [
            "--json",
            "dataset",
            "import",
            str(root),
            "-p",
            PROJECT,
            "--dataset",
            "ds",
            "--version",
            version,
            *extra,
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    last = json.loads(result.stdout.strip().splitlines()[-1])
    version_id: int = last["version_id"]
    return version_id


def _tag_count(project_dir: Path) -> int:
    with sqlite3.connect(project_dir / "image_database.db") as conn:
        count: int = conn.execute("SELECT count(*) FROM tags").fetchone()[0]
    return count


def test_cli_import_then_export_roundtrip(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path, tmp_path: Path
) -> None:
    """取り込み → 書き出しで元の .txt とバイト単位で一致する。"""
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")

    out_dir = tmp_path / "out"
    result = cli_runner.invoke(app, ["dataset", "export", str(version_id), str(out_dir), "-p", PROJECT])
    assert result.exit_code == 0, result.stdout + result.stderr

    assert (out_dir / "10_a" / "a1.txt").read_bytes() == TEXT_A
    assert (out_dir / "5_b" / "b1.txt").read_bytes() == TEXT_B
    assert (out_dir / "10_a" / "a1.png").is_file()
    assert not (out_dir / "sample001").exists()
    assert not (out_dir / "3_skipme").exists()
    assert _tag_count(project_dir) == 0


def test_roundtrip_two_versions_with_parent(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path, tmp_path: Path
) -> None:
    """--parent-version を付けた 2 版目も往復でき、親版が show に出る。"""
    version1 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", version="v1")
    version2 = _import(
        cli_runner,
        kohya_root,
        "--exclude-dir",
        "3_skipme",
        "--parent-version",
        str(version1),
        version="v2",
    )
    assert version2 != version1

    show = cli_runner.invoke(app, ["dataset", "show", str(version2), "-p", PROJECT])
    assert show.exit_code == 0, show.stdout + show.stderr
    assert f"parent_version_id: {version1}" in show.stdout

    out_dir = tmp_path / "out2"
    result = cli_runner.invoke(app, ["dataset", "export", str(version2), str(out_dir), "-p", PROJECT])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out_dir / "10_a" / "a1.txt").read_bytes() == TEXT_A


def test_cli_exclude_dir_adds_to_default_exclusions(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """--exclude-dir は既定の除外 (sample*) に加えて、指定フォルダも取り込まない。"""
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")
    show = cli_runner.invoke(app, ["dataset", "show", str(version_id), "-p", PROJECT])
    assert show.exit_code == 0, show.stdout + show.stderr
    assert "10_a" in show.stdout
    assert "5_b" in show.stdout
    assert "3_skipme" not in show.stdout
    assert "sample001" not in show.stdout


def test_cli_show_prints_folders(cli_runner: CliRunner, project_dir: Path, kohya_root: Path) -> None:
    """show はフォルダ名・繰り返し回数・画像数・トリガーワードを出す。"""
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")
    show = cli_runner.invoke(app, ["dataset", "show", str(version_id), "-p", PROJECT])
    assert show.exit_code == 0, show.stdout + show.stderr
    assert "10_a  repeats=10  images=1  trigger=-" in show.stdout
    assert "5_b  repeats=5  images=1  trigger=-" in show.stdout
    assert "total: 2 folder(s), 2 image(s)" in show.stdout


def test_cli_import_missing_dir_exits_nonzero(
    cli_runner: CliRunner, project_dir: Path, tmp_path: Path
) -> None:
    """存在しない DIR は非ゼロ終了し、スタックトレースを出さない。"""
    result = cli_runner.invoke(
        app,
        ["dataset", "import", str(tmp_path / "nope"), "-p", PROJECT, "--dataset", "ds", "--version", "v1"],
    )
    assert result.exit_code != 0
    assert "Traceback" not in result.stdout + result.stderr


def _invoke_import(runner: CliRunner, root: Path, *extra: str, json_mode: bool = True) -> Result:
    args = ["--json"] if json_mode else []
    return runner.invoke(
        app,
        [
            *args,
            "dataset",
            "import",
            str(root),
            "-p",
            PROJECT,
            "--dataset",
            "ds",
            "--version",
            "v1",
            *extra,
        ],
    )


def _version_count(project_dir: Path) -> int:
    with sqlite3.connect(project_dir / "image_database.db") as conn:
        # 引数の検証で止まると DB の初期化 (migration) 前に終わるため、表が無ければ 0 とする
        exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='dataset_versions'"
        ).fetchone()[0]
        if not exists:
            return 0
        count: int = conn.execute("SELECT count(*) FROM dataset_versions").fetchone()[0]
    return count


def test_cli_dry_run_shows_plan_with_candidates_and_imports_nothing(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """--dry-run はフォルダごとの画像数・学習テキストの無い画像数・候補を出し、版を作らない (#1452)。"""
    _save_noise_image(kohya_root / "10_a" / "no_text.png", seed=9)

    result = _invoke_import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", "--dry-run")

    assert result.exit_code == 0, result.stdout + result.stderr
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    items = {line["dir_name"]: line for line in lines if line["kind"] == "item"}
    assert items["10_a"]["images"] == 2
    assert items["10_a"]["images_without_text"] == 1
    assert items["10_a"]["trigger_candidate"] == "Trig_A"
    assert items["10_a"]["trigger_word"] is None
    assert items["3_skipme"]["include"] is False
    summary = lines[-1]
    assert summary["dry_run"] is True
    assert summary["folders"] == 2
    assert summary["images_without_text"] == 1
    assert _version_count(project_dir) == 0


def test_cli_dry_run_rich_output_shows_candidate(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    result = _invoke_import(cli_runner, kohya_root, "--dry-run", json_mode=False)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert (
        "+ 10_a  repeats=10  trigger=-  images=1  without_text=0  candidate=Trig_A (100%)" in result.stdout
    )
    assert "nothing imported" in result.stdout
    assert _version_count(project_dir) == 0


def test_cli_trigger_option_stores_trigger_word(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", "--trigger", "10_a=Trig_A")

    show = cli_runner.invoke(app, ["dataset", "show", str(version_id), "-p", PROJECT])
    assert show.exit_code == 0, show.stdout + show.stderr
    assert "10_a  repeats=10  images=1  trigger=Trig_A" in show.stdout
    # 指定しなかったフォルダは候補があっても確定しない
    assert "5_b  repeats=5  images=1  trigger=-" in show.stdout


@pytest.mark.parametrize("value", ["10_a", "=word", "10_a=", "nope_dir=word"])
def test_cli_invalid_trigger_option_exits_nonzero_and_imports_nothing(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path, value: str
) -> None:
    result = _invoke_import(cli_runner, kohya_root, "--trigger", value)

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout + result.stderr
    assert _version_count(project_dir) == 0


def test_cli_import_without_kohya_folder_fails_and_creates_no_version(
    cli_runner: CliRunner, project_dir: Path, tmp_path: Path
) -> None:
    """取り込めるフォルダが 0 個なら、空の版を作らずに非ゼロ終了し、train_data_dir を示す。"""
    root = tmp_path / "project_root"
    _save_noise_image(root / "img_v02" / "x.png", seed=7)
    (root / "config.json").write_text(json.dumps({"train_data_dir": "D:/train/img_v02"}), encoding="utf-8")

    result = _invoke_import(cli_runner, root)

    assert result.exit_code != 0
    assert "D:/train/img_v02" in result.stdout + result.stderr
    assert _version_count(project_dir) == 0
