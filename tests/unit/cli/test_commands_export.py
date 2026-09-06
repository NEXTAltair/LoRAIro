"""export create コマンドのユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _make_export_container(tmp_path: Path) -> MagicMock:
    """export テスト用 ServiceContainer モックを生成する。"""
    container = MagicMock()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def complete(format_name):
        def export(image_ids, output_path, resolution, *, report, **kwargs):
            for image_id in image_ids:
                report.completed.setdefault(image_id, set()).add(format_name)
            return output_path

        return export

    container.dataset_export_service.export_dataset_txt_format.side_effect = complete("txt")
    container.dataset_export_service.export_dataset_json_format.side_effect = complete("json")
    return container


@pytest.fixture
def mock_export_context(tmp_path, monkeypatch):
    """project 確認と ServiceContainer をモック。"""
    container = _make_export_container(tmp_path)
    monkeypatch.setattr("lorairo.cli.commands.export.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.export.get_service_container", MagicMock(return_value=container)
    )
    return container, tmp_path


@pytest.mark.unit
class TestExportCreate:
    def test_create_with_image_ids_calls_both_exporters(self, mock_export_context, tmp_path):
        """--image-ids 指定時に txt と json 両エクスポーターが呼ばれる。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2,3",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        container.dataset_export_service.export_dataset_txt_format.assert_called_once()
        container.dataset_export_service.export_dataset_json_format.assert_called_once()

    def test_create_without_image_ids_fails(self, mock_export_context, tmp_path):
        """--image-ids なしは exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_json_output_has_result_row(self, mock_export_context, tmp_path):
        """--json 出力に kind=result 行が含まれる。"""
        _container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "--json",
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2,3",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        json_lines = []
        for line in result.output.strip().splitlines():
            if not line.strip():
                continue
            try:
                json_lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # loguru やその他の非 JSON 行はスキップ
        result_row = next(r for r in json_lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["total_images"] == 3

    def test_create_invalid_image_ids_fails(self, mock_export_context, tmp_path):
        """非整数の --image-ids は exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "abc,def",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_resolution_passed_to_exporters(self, mock_export_context, tmp_path):
        """--resolution が両エクスポーターに渡される。"""
        container, _ = mock_export_context
        runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1",
                "--output",
                str(tmp_path / "out"),
                "--resolution",
                "1024",
            ],
        )
        call_args_txt = container.dataset_export_service.export_dataset_txt_format.call_args
        call_args_json = container.dataset_export_service.export_dataset_json_format.call_args
        assert call_args_txt is not None
        assert call_args_json is not None
        # resolution は第3引数 (positional) または keyword "resolution" で渡される
        txt_args = call_args_txt[0]
        json_args = call_args_json[0]
        assert 1024 in txt_args or call_args_txt[1].get("resolution") == 1024
        assert 1024 in json_args or call_args_json[1].get("resolution") == 1024

    def test_create_tag_languages_passed_to_exporters(self, mock_export_context, tmp_path):
        """--tag-language の複数指定が両エクスポーターに渡される。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1",
                "--output",
                str(tmp_path / "out"),
                "--tag-language",
                "canonical",
                "--tag-language",
                "ja",
            ],
        )
        assert result.exit_code == 0
        txt_kwargs = container.dataset_export_service.export_dataset_txt_format.call_args.kwargs
        json_kwargs = container.dataset_export_service.export_dataset_json_format.call_args.kwargs
        assert txt_kwargs["tag_languages"] == ["canonical", "ja"]
        assert json_kwargs["tag_languages"] == ["canonical", "ja"]


@pytest.mark.unit
class TestExportCreateImageIdsFile:
    """export create の --image-ids-file 入力 (Issue #1216)。"""

    def test_create_with_image_ids_file(self, mock_export_context, tmp_path):
        container, _ = mock_export_context
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1\n2, 3\n")
        result = runner.invoke(
            app,
            [
                "--json",
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids-file",
                str(ids_file),
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        called_ids = container.dataset_export_service.export_dataset_txt_format.call_args.args[0]
        assert called_ids == [1, 2, 3]

    def test_create_both_ids_inputs_rejected(self, mock_export_context, tmp_path):
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1")
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--image-ids-file",
                str(ids_file),
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2


@pytest.fixture
def real_export_context(tmp_path, monkeypatch):
    """Real writers and local artifacts with isolated DB/copy boundaries."""
    import shutil

    from lorairo.services.dataset_export_service import DatasetExportService

    db = MagicMock()
    db.annotation_repo.get_merged_reader.return_value = None
    db.get_image_metadata.side_effect = lambda image_id: {"id": image_id} if image_id in (1, 2) else None
    db.get_image_annotations.return_value = {
        "tags": [{"tag": "sample"}],
        "captions": [{"caption": "Synthetic image"}],
        "score_labels": [],
        "quality_summary": {},
    }
    paths = {}
    for image_id in (1, 2):
        path = tmp_path / f"source-{image_id}.png"
        path.write_bytes(b"synthetic processed image")
        paths[image_id] = path
    db.check_processed_image_exists.side_effect = lambda image_id, resolution: (
        {"stored_image_path": str(paths[image_id])} if image_id in paths else None
    )
    fs = MagicMock()
    fs.copy_file.side_effect = shutil.copyfile
    service = DatasetExportService(MagicMock(), fs, db, MagicMock())
    container = MagicMock()
    container.dataset_export_service = service
    monkeypatch.setattr("lorairo.cli.commands.export.api_get_project", MagicMock())
    monkeypatch.setattr("lorairo.cli.commands.export.get_service_container", lambda: container)
    monkeypatch.setattr("lorairo.services.dataset_export_service.resolve_stored_path", Path)
    return service, db, paths


def _invoke_real_export(output, image_ids="1,2"):
    result = runner.invoke(
        app,
        [
            "--json",
            "export",
            "create",
            "--project",
            "synthetic",
            "--image-ids",
            image_ids,
            "--output",
            str(output),
        ],
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 1
    from lorairo.cli.introspection import ExportCreateResult

    ExportCreateResult.model_validate(rows[0])
    return result, rows[0]


@pytest.mark.parametrize("use_file", [False, True])
def test_export_reuses_metadata_lookup_per_format(real_export_context, tmp_path, use_file):
    """Tracking must retain the legacy two metadata reads per ID across both writers."""
    from collections import Counter

    _service, db, _paths = real_export_context
    output = tmp_path / "out"
    selection = ["--image-ids", "1,2,99"]
    if use_file:
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1\n2\n99\n", encoding="utf-8")
        selection = ["--image-ids-file", str(ids_file)]
    result = runner.invoke(
        app,
        ["--json", "export", "create", "--project", "synthetic", *selection, "--output", str(output)],
    )
    row = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1
    assert row["status"] == "partial_success"
    assert row["exported_ids"] == [1, 2]
    assert row["failed_ids"] == [99]
    assert all(error["reason"] == "image_not_found" for error in row["error_details"][0]["errors"])
    assert Counter(call.args[0] for call in db.get_image_metadata.call_args_list) == {1: 2, 2: 2, 99: 2}
    assert Counter(call.args[0] for call in db.get_image_annotations.call_args_list) == {1: 2, 2: 2}
    assert len(json.loads((output / "metadata.json").read_text())) == 2
    assert len(list(output.glob("*.txt"))) == 2
    assert len(list(output.glob("*.caption"))) == 2


@pytest.mark.parametrize("use_file,count", [(False, 2), (True, 2), (True, 501)])
@pytest.mark.parametrize("languages", [["canonical"], ["canonical", "ja"]])
@pytest.mark.parametrize("last_suffix", [".png", ".webp"])
def test_export_collision_preserves_first_image_across_formats(
    real_export_context, tmp_path, use_file, count, languages, last_suffix
):
    """Flat image or tag filenames must not silently replace another selected ID."""
    service, db, paths = real_export_context
    db.get_image_metadata.side_effect = lambda image_id: {"id": image_id}
    db.get_image_annotations.side_effect = lambda image_id: {
        "tags": [{"tag": f"tag{image_id}"}],
        "captions": [{"caption": f"caption{image_id}"}],
    }
    for image_id in range(1, count + 1):
        source = (
            tmp_path
            / "sources"
            / str(image_id)
            / (
                "shared.png"
                if image_id == 1
                else f"shared{last_suffix}"
                if image_id == count
                else "unique.png"
            )
        )
        if image_id not in (1, count):
            source = source.with_name(f"unique-{image_id}.png")
        source.parent.mkdir(parents=True)
        source.write_bytes(f"image-{image_id}".encode())
        paths[image_id] = source
    selection = ["--image-ids", ",".join(map(str, range(1, count + 1)))]
    if use_file:
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("\n".join(map(str, range(1, count + 1))), encoding="utf-8")
        selection = ["--image-ids-file", str(ids_file)]
    output = tmp_path / "out"
    language_options = [option for language in languages for option in ("--tag-language", language)]
    result = runner.invoke(
        app,
        [
            "--json",
            "export",
            "create",
            "--project",
            "synthetic",
            *selection,
            "--output",
            str(output),
            *language_options,
        ],
    )
    row = json.loads(result.stdout.splitlines()[-1])
    assert result.exit_code == 1
    assert row["status"] == "partial_success"
    assert row["exported"] == count - 1
    assert row["failed"] == 1
    assert row["skipped"] == 0
    assert row["failed_ids"] == [count]
    assert row["exported_ids"] == list(range(1, count))
    failure = row["error_details"][0]
    assert failure["errors"][0]["reason"] == "output_path_collision"
    assert failure["output_files"] == failure["completed_formats"] == []
    assert db.get_image_metadata.call_count == 2 * count - 1
    assert service.file_system_manager.copy_file.call_count == 2 * (count - 1) * len(languages)
    for language in languages:
        root = output / language if len(languages) > 1 else output
        assert (root / "shared.png").read_bytes() == b"image-1"
        assert (root / "shared.txt").read_text() == "tag1"
        assert (root / "shared.caption").read_text() == "caption1"
        metadata = json.loads((root / "metadata.json").read_text())
        assert len(metadata) == count - 1
        assert metadata[str(root / "shared.png")]["tags"] == "tag1"
        assert len(list(root.glob("*.png"))) == count - 1
        assert len(list(root.glob("*.txt"))) == count - 1
        if last_suffix != ".png":
            assert not (root / f"shared{last_suffix}").exists()


def test_destination_collision_does_not_reserve_other_paths(tmp_path):
    from lorairo.services.dataset_export_service import ExportResult

    report = ExportResult([1, 2, 3])
    first, other = tmp_path / "first.png", tmp_path / "other.png"
    assert report.reserve_destinations(1, [first], "txt")
    assert not report.reserve_destinations(2, [other, first], "txt")
    assert report.reserve_destinations(3, [other], "txt")
    assert report.reserve_destinations(1, [first], "json")
    assert not report.reserve_destinations(2, [tmp_path / "new.png"], "json")


def test_json_only_allows_same_stem_with_distinct_image_extensions(real_export_context, tmp_path):
    from lorairo.services.dataset_export_service import ExportResult

    service, _db, paths = real_export_context
    for image_id, suffix in ((1, ".png"), (2, ".webp")):
        source = tmp_path / f"shared{suffix}"
        source.write_bytes(f"image-{image_id}".encode())
        paths[image_id] = source
    output = tmp_path / "json-only"
    report = ExportResult([1, 2])
    service.export_dataset_json_format([1, 2], output, report=report)
    assert not report.failures
    assert report.completed == {1: {"json"}, 2: {"json"}}
    assert len(json.loads((output / "metadata.json").read_text())) == 2
    assert (output / "shared.png").read_bytes() == b"image-1"
    assert (output / "shared.webp").read_bytes() == b"image-2"
    assert not list(output.glob("*.txt"))


def test_duplicate_csv_ids_report_unique_actual_outputs(real_export_context, tmp_path):
    service, _db, _paths = real_export_context
    result, row = _invoke_real_export(tmp_path / "out", "1,1")
    assert result.exit_code == 0
    assert row["total_images"] == 2  # Preserve the legacy CSV input count.
    assert row["requested"] == row["exported"] == 1
    assert row["exported_ids"] == [1]
    assert len(list((tmp_path / "out").glob("*.png"))) == 1
    assert len(json.loads((tmp_path / "out" / "metadata.json").read_text())) == 1
    assert service.file_system_manager.copy_file.call_count == 2  # One per current format writer.


@pytest.mark.parametrize("language", ["../bad", "bad/value", "bad!value"])
def test_invalid_export_language_is_input_error_before_side_effects(
    mock_export_context, tmp_path, language
):
    container, _ = mock_export_context
    result = runner.invoke(
        app,
        [
            "--json",
            "export",
            "create",
            "--project",
            "proj",
            "--image-ids",
            "1,2",
            "--output",
            str(tmp_path / "uncreated"),
            "--tag-language",
            language,
        ],
    )
    assert result.exit_code == 2
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 1
    assert rows[0]["kind"] == "error"
    assert rows[0]["code"] == "INVALID_INPUT"
    container.set_active_project.assert_not_called()
    container.dataset_export_service.export_dataset_txt_format.assert_not_called()
    container.dataset_export_service.export_dataset_json_format.assert_not_called()
    assert not (tmp_path / "uncreated").exists()


@pytest.mark.parametrize(
    ("missing", "copy_error", "expected_exported", "expected_skipped", "expected_failed"),
    [((), False, 2, 0, 0), ((1, 2), False, 0, 2, 0), ((2,), False, 1, 1, 0), ((), True, 0, 0, 2)],
)
def test_real_export_counts_match_artifacts(
    real_export_context, tmp_path, missing, copy_error, expected_exported, expected_skipped, expected_failed
):
    service, _db, paths = real_export_context
    for image_id in missing:
        paths[image_id].unlink()
    if copy_error:
        service.file_system_manager.copy_file.side_effect = OSError("copy failed")
    output = tmp_path / "out"
    result, row = _invoke_real_export(output)
    assert result.exit_code == (0 if expected_exported == 2 else 1)
    assert row["ok"] is (expected_exported == 2)
    assert row["requested"] == row["total_images"] == 2
    assert (row["exported"], row["skipped"], row["failed"]) == (
        expected_exported,
        expected_skipped,
        expected_failed,
    )
    metadata = json.loads((output / "metadata.json").read_text())
    assert (
        len(metadata)
        == len(list(output.glob("*.png")))
        == len(list(output.glob("*.txt")))
        == expected_exported
    )
    for entry in metadata.values():
        assert entry["tags"] == "sample"
        assert entry["caption"] == "Synthetic image"
    assert row["status"] == (
        "success" if expected_exported == 2 else "partial_success" if expected_exported else "failed"
    )


def test_export_missing_id_differs_from_missing_processed(real_export_context, tmp_path):
    _service, _db, paths = real_export_context
    paths[2].unlink()
    result, row = _invoke_real_export(tmp_path / "out", "2,99")
    assert result.exit_code == 1
    reasons = {item["image_id"]: item["errors"][0]["reason"] for item in row["error_details"]}
    assert reasons == {2: "processed_image_missing", 99: "image_not_found"}


@pytest.mark.parametrize(
    "operation", ["get_image_metadata", "check_processed_image_exists", "get_image_annotations"]
)
def test_export_db_errors_are_failures_not_missing(real_export_context, tmp_path, operation):
    _service, db, _paths = real_export_context
    getattr(db, operation).side_effect = RuntimeError("DB read failed")
    result, row = _invoke_real_export(tmp_path / "out")
    assert result.exit_code == 1
    assert row["failed"] == 2
    assert row["skipped"] == 0
    assert all(
        error["reason"] == "export_error" for item in row["error_details"] for error in item["errors"]
    )


def test_json_finalization_failure_preserves_txt_and_retry_ids(real_export_context, tmp_path, monkeypatch):
    import builtins

    original_open = builtins.open

    def fail_metadata(file, mode="r", *args, **kwargs):
        if Path(file).name == "metadata.json" and mode == "w":
            raise OSError("metadata disk error")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_metadata)
    output = tmp_path / "out"
    result, row = _invoke_real_export(output)
    assert result.exit_code == 1
    assert row["exported"] == 0
    assert row["failed_ids"] == [1, 2]
    assert len(list(output.glob("*.txt"))) == 2
    for item in row["error_details"]:
        assert item["completed_formats"] == ["txt"]
        assert any(path.endswith(".txt") for path in item["output_files"])
        assert item["errors"][0]["reason"] == "metadata_write_error"
    monkeypatch.setattr(builtins, "open", original_open)
    retry, retry_row = _invoke_real_export(tmp_path / "retry", ",".join(map(str, row["failed_ids"])))
    assert retry.exit_code == 0
    assert retry_row["exported_ids"] == [1, 2]


@pytest.mark.parametrize(
    ("count", "file_input", "expected_exit"),
    [(0, False, 2), (1, False, 0), (500, False, 0), (501, False, 2), (501, True, 0)],
)
def test_export_input_boundaries(mock_export_context, tmp_path, count, file_input, expected_exit):
    values = ",".join(str(value) for value in range(1, count + 1))
    option = "--image-ids"
    if file_input:
        file_path = tmp_path / "ids.txt"
        file_path.write_text(values)
        values = str(file_path)
        option = "--image-ids-file"
    result = runner.invoke(
        app,
        [
            "--json",
            "export",
            "create",
            "--project",
            "synthetic",
            option,
            values,
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == expected_exit


def test_human_export_failure_does_not_claim_success(real_export_context, tmp_path):
    service, _db, _paths = real_export_context
    service.file_system_manager.copy_file.side_effect = OSError("copy failed")
    result = runner.invoke(
        app,
        [
            "export",
            "create",
            "--project",
            "synthetic",
            "--image-ids",
            "1,2",
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
    assert "Export completed successfully" not in result.stdout
    assert "Export incomplete" in result.stdout
    assert "Retry image IDs" in result.stdout


def test_export_output_directory_failure_retains_counts(real_export_context, tmp_path):
    output = tmp_path / "occupied"
    output.write_text("preexisting file")
    result, row = _invoke_real_export(output)
    assert result.exit_code == 1
    assert row["failed"] == row["requested"] == 2
    assert output.read_text() == "preexisting file"
