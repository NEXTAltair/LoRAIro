"""images search コマンドのユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.filter_criteria import ImageFilterCriteria

runner = CliRunner()


@pytest.mark.unit
class TestImageFilterCriteriaSort:
    def test_default_sort_is_image_id_asc(self) -> None:
        criteria = ImageFilterCriteria()
        assert criteria.sort_field == "image_id"
        assert criteria.sort_direction == "asc"

    def test_sort_fields_can_be_set(self) -> None:
        criteria = ImageFilterCriteria(sort_field="file_path", sort_direction="desc")
        assert criteria.sort_field == "file_path"
        assert criteria.sort_direction == "desc"


def _make_container(records: list[dict]) -> MagicMock:  # type: ignore[type-arg]
    container = MagicMock()
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.image_repo.get_images_count_only.return_value = len(records)
    return container


@pytest.fixture
def mock_search_context(tmp_path: pytest.FixtureDef, monkeypatch: pytest.MonkeyPatch):  # type: ignore[type-arg]
    records = [
        {"id": 1, "image_id": 1, "file_path": "a.webp"},
        {"id": 2, "image_id": 2, "file_path": "b.webp"},
    ]
    container = _make_container(records)
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return container, tmp_path


@pytest.mark.unit
class TestImagesSearch:
    def test_search_query_file(self, mock_search_context: tuple, tmp_path: pytest.FixtureDef) -> None:
        _container, _ = mock_search_context
        query_file = tmp_path / "search.json"
        query_file.write_text('{"tags": ["cat"], "limit": 10}')

        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0
        # JSON 行のみを抽出 (loguru 等の非 JSON 出力を除外)
        json_lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in json_lines if r.get("kind") == "item"]
        result_row = next(r for r in json_lines if r.get("kind") == "result")
        assert len(items) == 2
        assert result_row["ok"] is True
        assert "image_id" in items[0]
        assert "file_path" in items[0]

    def test_search_stdin(self, mock_search_context: tuple) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query", "-"],
            input='{"include_nsfw": true}',
        )
        assert result.exit_code == 0
        json_lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        assert any(r.get("kind") == "result" for r in json_lines)

    def test_search_invalid_json_returns_exit2(self, mock_search_context: tuple) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query", "-"],
            input="not json",
        )
        assert result.exit_code == 2

    def test_search_invalid_schema_returns_exit2(
        self, mock_search_context: tuple, tmp_path: pytest.FixtureDef
    ) -> None:
        query_file = tmp_path / "bad.json"
        # limit は 1-500 の範囲でないと ValidationError
        query_file.write_text('{"limit": 999}')
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 2

    def test_search_with_sort(self, mock_search_context: tuple, tmp_path: pytest.FixtureDef) -> None:
        query_file = tmp_path / "sort.json"
        query_file.write_text('{"sort": [{"field": "file_path", "direction": "desc"}]}')
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0

    def test_search_metadata_conditions_flow_to_criteria(
        self, mock_search_context: tuple, tmp_path: pytest.FixtureDef
    ) -> None:
        """width/height/filename/format 条件が ImageFilterCriteria へ渡る (Issue #1216)。"""
        container, _ = mock_search_context
        query_file = tmp_path / "meta.json"
        query_file.write_text(
            json.dumps(
                {
                    "width_max": 999,
                    "height_min": 100,
                    "filename_pattern": "sample_%",
                    "format": "jpeg",
                    "tags": ["absurdres"],
                }
            )
        )
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0
        criteria = container.db_manager.image_repo.get_images_by_filter.call_args.args[0]
        assert criteria.width_max == 999
        assert criteria.height_min == 100
        assert criteria.filename_pattern == "sample_%"
        assert criteria.format_name == "jpeg"

    def test_emit_ids_pages_all_matching_bypassing_guard(
        self, mock_search_context: tuple, tmp_path
    ) -> None:
        """emit_ids は 500 超でも count-first ガードをバイパスし全 ID をページ出力する (Issue #1216)。"""
        container, _ = mock_search_context
        # 総数 600 (>500 でガード発火域)。500 件 → 100 件の 2 ページで返す。
        container.db_manager.image_repo.get_images_count_only.return_value = 600
        pages = [
            ([{"id": i, "image_id": i, "file_path": f"{i}.webp"} for i in range(1, 501)], 600),
            ([{"id": i, "image_id": i, "file_path": f"{i}.webp"} for i in range(501, 601)], 600),
            ([], 600),
        ]
        container.db_manager.image_repo.get_images_by_filter.side_effect = pages
        query_file = tmp_path / "emit.json"
        query_file.write_text(json.dumps({"tags": ["absurdres"], "emit_ids": True}))
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0  # ResultSetTooLargeError にならない
        rows = [json.loads(x) for x in result.stdout.strip().splitlines() if x.strip().startswith("{")]
        items = [r for r in rows if r.get("kind") == "item"]
        assert len(items) == 600  # 全件 ID 出力
        result_row = next(r for r in rows if r.get("kind") == "result")
        assert result_row["count"] == 600
        assert result_row["total"] == 600
        assert result_row["truncated"] is False

    def test_search_no_options_returns_exit2(self, mock_search_context: tuple) -> None:
        """--query-file も --query も指定しない場合は UsageError (exit 2)。"""
        result = runner.invoke(
            app,
            ["--json", "images", "search", "--project", "proj"],
        )
        assert result.exit_code == 2

    def test_search_both_options_returns_exit2(
        self, mock_search_context: tuple, tmp_path: pytest.FixtureDef
    ) -> None:
        """--query-file と --query を同時指定すると UsageError (exit 2)。"""
        query_file = tmp_path / "q.json"
        query_file.write_text("{}")
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "search",
                "--project",
                "proj",
                "--query-file",
                str(query_file),
                "--query",
                "-",
            ],
            input="{}",
        )
        assert result.exit_code == 2

    def test_search_human_output_tab_rows(
        self, mock_search_context: tuple, tmp_path: pytest.FixtureDef
    ) -> None:
        """--json なし時は image_id TAB file_path の plain 行を出力する。"""
        query_file = tmp_path / "q.json"
        query_file.write_text("{}")
        result = runner.invoke(
            app,
            ["images", "search", "--project", "proj", "--query-file", str(query_file)],
        )
        assert result.exit_code == 0
        assert "1\ta.webp" in result.output
        assert "2\tb.webp" in result.output
