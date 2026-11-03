"""CLI contract for the read-only tag health report."""

import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.tag_health_service import (
    MissingExpectedTag,
    TagFrequency,
    TagHealthReport,
    TagVariant,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def test_health_emits_typed_sections_and_exact_summary(monkeypatch):
    report = TagHealthReport(
        total_images=3,
        tagged_images=1,
        untagged_images=2,
        unique_tags=1,
        expected_tag_count=1,
        frequencies=[TagFrequency("Cat", 1)],
        variants=[TagVariant("Cat", "cat", "normalization")],
        missing_expected=[MissingExpectedTag("cat", "cat", 2, [2], True)],
        frequency_count=1,
        variant_count=1,
        missing_expected_count=1,
        frequencies_truncated=False,
        variants_truncated=False,
        missing_expected_truncated=False,
        spelling_candidates_truncated=False,
        limit=1,
    )
    api = Mock(return_value=report)
    monkeypatch.setattr("lorairo.public_api.tag_health.report_tag_health", api)
    result = runner.invoke(
        app,
        [
            "--json",
            "tags",
            "health",
            "--project",
            "fixture",
            "--expected-tag",
            "cat",
            "--expected-tag",
            "dog",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    api.assert_called_once_with("fixture", ["cat", "dog"], limit=1)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row.get("section") for row in rows[:-1]] == ["frequency", "variant", "missing_expected"]
    assert rows[-1]["kind"] == "result" and rows[-1]["read_only"] is True
    assert rows[-1]["total_images"] == 3 and rows[-1]["untagged_images"] == 2
    assert rows[2]["missing_count"] == 2 and rows[2]["image_ids_truncated"] is True
    assert "frequencies" not in rows[-1]


@pytest.mark.parametrize("limit", ["0", "501"])
def test_health_cli_rejects_invalid_limit_before_api(monkeypatch, limit):
    api = Mock()
    monkeypatch.setattr("lorairo.public_api.tag_health.report_tag_health", api)
    result = runner.invoke(app, ["--json", "tags", "health", "-p", "fixture", "--limit", limit])
    assert result.exit_code == 2
    api.assert_not_called()
