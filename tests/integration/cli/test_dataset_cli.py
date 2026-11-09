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


def _invoke_diff(runner: CliRunner, base: int, target: int, *, json_mode: bool = True) -> Result:
    args = ["--json"] if json_mode else []
    return runner.invoke(app, [*args, "dataset", "diff", str(base), str(target), "-p", PROJECT])


def test_cli_diff_reimport_with_parent_reports_changes(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """外部で編集したフォルダを --parent-version で取り込み直し、diff で差分を出す (#1455 案 D)。"""
    version1 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", version="v1")
    # 外部での編集: 画像の追加・学習テキストの修正・画像の差し替え・フォルダの削除
    _save_noise_image(kohya_root / "10_a" / "a2.png", seed=11)
    (kohya_root / "10_a" / "a2.txt").write_text("Trig_A, new tag", encoding="utf-8")
    (kohya_root / "10_a" / "a1.txt").write_bytes(b"Trig_A, (tag:1.2), long_sleeves, Smile, extra")
    _save_noise_image(kohya_root / "10_a" / "a1.png", seed=12)
    version2 = _import(
        cli_runner,
        kohya_root,
        "--exclude-dir",
        "3_skipme",
        "--exclude-dir",
        "5_b",
        "--parent-version",
        str(version1),
        version="v2",
    )

    result = _invoke_diff(cli_runner, version1, version2)

    assert result.exit_code == 0, result.stdout + result.stderr
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    items = [line for line in lines if line["kind"] == "item"]
    folders = {item["dir_name"]: item for item in items if item["scope"] == "folder"}
    images = {item["file_stem"]: item for item in items if item["scope"] == "image"}
    assert folders["5_b"]["status"] == "removed"
    assert folders["10_a"]["status"] == "changed"
    assert folders["10_a"]["target_image_count"] == 2
    assert images["a2"]["status"] == "added"
    assert images["a1"]["status"] == "replaced"
    (text,) = images["a1"]["texts"]
    # 改行は区切りではないため、元の "long_sleeves\r\nsecond line" は 1 要素
    assert text["added_elements"] == ["long_sleeves", "extra"]
    assert text["removed_elements"] == ["long_sleeves\r\nsecond line"]
    summary = lines[-1]
    assert summary["kind"] == "result"
    assert summary["has_changes"] is True
    assert summary["folders_removed"] == 1
    assert summary["images_added"] == 1
    assert summary["images_replaced"] == 1
    # 比較は書き込みをしない (画像直下のタグも増えない)
    assert _tag_count(project_dir) == 0


def test_cli_diff_same_content_has_no_changes(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    version1 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", version="v1")
    version2 = _import(
        cli_runner, kohya_root, "--exclude-dir", "3_skipme", "--parent-version", str(version1), version="v2"
    )

    result = _invoke_diff(cli_runner, version1, version2, json_mode=False)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert "no changes" in result.stdout


def test_cli_diff_rich_output_shows_element_changes(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    version1 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", version="v1")
    (kohya_root / "5_b" / "b1.txt").write_bytes(b"trig_b, [bracket], blue eyes")
    version2 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme", version="v2")

    result = _invoke_diff(cli_runner, version1, version2, json_mode=False)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert "~ 5_b/  images=1->1" in result.stdout
    assert "~ b1  (changed)" in result.stdout
    assert "~ .txt  +[[bracket]]" in result.stdout


def test_cli_diff_missing_version_exits_nonzero(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    version1 = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")

    result = _invoke_diff(cli_runner, version1, 9999)

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout + result.stderr


def _invoke_copy_tags(runner: CliRunner, version_id: int, *extra: str) -> dict[str, object]:
    result = runner.invoke(app, ["--json", "dataset", "copy-tags", str(version_id), "-p", PROJECT, *extra])
    assert result.exit_code == 0, result.stdout + result.stderr
    summary: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])
    return summary


def _kohya_tags(project_dir: Path) -> list[str]:
    with sqlite3.connect(project_dir / "image_database.db") as conn:
        rows = conn.execute(
            "SELECT t.tag FROM tags t JOIN models m ON t.model_id = m.id "
            "WHERE m.litellm_model_id = '__kohya_dataset__' ORDER BY t.tag"
        ).fetchall()
    return [row[0] for row in rows]


def test_cli_copy_tags_copies_selected_folder_as_kohya_dataset(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """copy-tags は選んだフォルダの学習テキストを KOHYA_DATASET の Tag として写す (#1454)。"""
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")

    dry = _invoke_copy_tags(cli_runner, version_id, "--folder", "5_b", "--dry-run")
    assert dry["dry_run"] is True
    assert dry["tags_added"] == 2
    assert _tag_count(project_dir) == 0

    summary = _invoke_copy_tags(cli_runner, version_id, "--folder", "5_b")
    assert (summary["folders"], summary["images"], summary["tags_added"]) == (1, 1, 2)
    assert _kohya_tags(project_dir) == ["blue eyes", "trig_b"]

    again = _invoke_copy_tags(cli_runner, version_id)
    # 5_b の 2 件は飛ばし、10_a の要素を足す (表記はそのまま)
    assert (again["tags_added"], again["tags_skipped"]) == (4, 2)
    assert "(tag:1.2)" in _kohya_tags(project_dir)


def test_cli_copy_tags_unknown_folder_exits_nonzero(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")

    result = cli_runner.invoke(
        app, ["dataset", "copy-tags", str(version_id), "-p", PROJECT, "--folder", "nope"]
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.stdout + result.stderr
    assert _tag_count(project_dir) == 0


def test_cli_revoke_tags_deletes_only_kohya_dataset_and_supports_dry_run_and_all(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """revoke-tags / copy-tags --revoke は KOHYA_DATASET の行だけを削除し、他モデルのタグは残す (#1490)。"""
    version_id = _import(cli_runner, kohya_root, "--exclude-dir", "3_skipme")
    _invoke_copy_tags(cli_runner, version_id)

    # 手動タグを 1 件追加しておく
    with sqlite3.connect(project_dir / "image_database.db") as conn:
        conn.execute(
            "INSERT INTO models (name, provider, litellm_model_id, requires_api_key, created_at, updated_at) "
            "VALUES ('MANUAL_EDIT', 'user', '__manual_edit__', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        manual_model_id = conn.execute(
            "SELECT id FROM models WHERE litellm_model_id = '__manual_edit__'"
        ).fetchone()[0]
        first_image_id = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO tags (image_id, model_id, tag, existing, is_edited_manually, created_at, updated_at) "
            "VALUES (?, ?, 'manual_keep', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (first_image_id, manual_model_id),
        )
        conn.commit()

    # 1. dry-run: 件数だけ返し、削除しない
    dry_res = cli_runner.invoke(
        app, ["--json", "dataset", "revoke-tags", str(version_id), "-p", PROJECT, "--dry-run"]
    )
    assert dry_res.exit_code == 0, dry_res.stdout + dry_res.stderr
    dry_payload = json.loads(dry_res.stdout.strip().splitlines()[-1])
    assert dry_payload["dry_run"] is True
    assert dry_payload["tags_removed"] == 6
    assert len(_kohya_tags(project_dir)) == 6

    # 2. フォルダ指定での取り消し (5_b の 2 件だけ削除)
    folder_res = cli_runner.invoke(
        app,
        ["--json", "dataset", "revoke-tags", str(version_id), "-p", PROJECT, "--folder", "5_b"],
    )
    assert folder_res.exit_code == 0, folder_res.stdout + folder_res.stderr
    folder_payload = json.loads(folder_res.stdout.strip().splitlines()[-1])
    assert folder_payload["tags_removed"] == 2
    assert len(_kohya_tags(project_dir)) == 4

    # 3. プロジェクト全体の取り消し (`copy-tags --revoke` で VERSION_ID 省略)
    all_res = cli_runner.invoke(app, ["--json", "dataset", "copy-tags", "--revoke", "-p", PROJECT])
    assert all_res.exit_code == 0, all_res.stdout + all_res.stderr
    all_payload = json.loads(all_res.stdout.strip().splitlines()[-1])
    assert all_payload["version_id"] is None
    assert all_payload["tags_removed"] == 4
    assert _kohya_tags(project_dir) == []
    # 手動タグは残っていること
    assert _tag_count(project_dir) == 1


def _first_image_id(project_dir: Path) -> int:
    with sqlite3.connect(project_dir / "image_database.db") as conn:
        image_id: int = conn.execute("SELECT id FROM images ORDER BY id LIMIT 1").fetchone()[0]
    return image_id


def test_cli_usage_returns_versions_folders_and_texts_for_image(
    cli_runner: CliRunner, project_dir: Path, kohya_root: Path
) -> None:
    """同じ画像を複数フォルダ・複数版に入れたとき、dataset usage で一覧を引ける (#1461)。"""
    # a1.png と同じ画像を 5_b にも別名で置き、フォルダごとに別の学習テキストを持たせる
    (kohya_root / "5_b" / "a1_in_b.png").write_bytes((kohya_root / "10_a" / "a1.png").read_bytes())
    (kohya_root / "5_b" / "a1_in_b.txt").write_text("trig_b, shared image in b", encoding="utf-8")
    v1 = _import(
        cli_runner, kohya_root, "--exclude-dir", "3_skipme", "--trigger", "10_a=Trig_A", version="v1"
    )

    (kohya_root / "10_a" / "a1.txt").write_text("Trig_A, updated in v2", encoding="utf-8")
    v2 = _import(
        cli_runner,
        kohya_root,
        "--exclude-dir",
        "3_skipme",
        "--exclude-dir",
        "5_b",
        "--parent-version",
        str(v1),
        version="v2",
    )

    image_id = _first_image_id(project_dir)
    result = cli_runner.invoke(
        app, ["--json", "dataset", "usage", "--image-id", str(image_id), "-p", PROJECT]
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    lines = [json.loads(line) for line in result.stdout.strip().splitlines()]
    items = [line for line in lines if line["kind"] == "item"]
    summary = lines[-1]

    assert [
        (
            item["version"],
            item["version_id"],
            item["dir_name"],
            item["file_stem"],
            item["texts"][0]["raw_text"],
        )
        for item in items
    ] == [
        ("v1", v1, "10_a", "a1", TEXT_A.decode("utf-8")),
        ("v1", v1, "5_b", "a1_in_b", "trig_b, shared image in b"),
        ("v2", v2, "10_a", "a1", "Trig_A, updated in v2"),
    ]
    assert summary["usages"] == 3
    assert summary["versions"] == 2

    # 使われていない image_id でもエラーにせず空の一覧を返す
    unused = cli_runner.invoke(app, ["--json", "dataset", "usage", "99999", "-p", PROJECT])
    assert unused.exit_code == 0, unused.stdout + unused.stderr
    unused_lines = [json.loads(line) for line in unused.stdout.strip().splitlines()]
    assert [line for line in unused_lines if line["kind"] == "item"] == []
    assert unused_lines[-1]["usages"] == 0
