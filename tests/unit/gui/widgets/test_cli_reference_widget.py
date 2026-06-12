"""CliReferenceWidget (Frame 8 · CLI 契約リファレンス) のユニットテスト。

HTML 生成ロジック (Qt 非依存) と、ウィジェットの遅延コンテンツ生成を検証する。
コマンド総覧は TOOL_SPECS から動的生成されるため、テストも TOOL_SPECS を
ground truth として drift を検出する。
"""

import pytest

from lorairo.cli._errors import ErrorCode
from lorairo.cli.introspection import iter_tool_specs
from lorairo.gui.widgets.cli_reference_widget import (
    CliReferenceWidget,
    build_cli_reference_html,
    build_command_overview_html,
    build_error_codes_html,
    highlight_jsonl,
)

pytestmark = pytest.mark.gui


class TestHighlightJsonl:
    """JSONL 色分けヘルパーの検証。"""

    def test_highlight_jsonl_colors_keys_strings_numbers_booleans(self):
        line = '{"kind": "item", "image_id": 1, "ok": true}'
        result = highlight_jsonl(line)
        assert '"kind"' in result
        assert '"item"' in result
        assert ">1</span>" in result
        assert ">true</span>" in result
        # キーと文字列値は異なる色で着色される
        assert result.count("<span") >= 4

    def test_highlight_jsonl_escapes_html_special_characters(self):
        line = '{"hint": "<script>"}'
        result = highlight_jsonl(line)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestBuildCommandOverview:
    """TOOL_SPECS からのコマンド総覧動的生成の検証。"""

    def test_overview_contains_every_tool_spec_path(self):
        html_text = build_command_overview_html()
        for spec in iter_tool_specs():
            assert f"<code>{spec.path}</code>" in html_text

    def test_overview_total_count_matches_tool_specs_plus_introspection(self):
        html_text = build_command_overview_html()
        expected_total = len(iter_tool_specs()) + 2  # list-commands / describe を補記
        assert f"({expected_total} サブコマンド)" in html_text

    def test_overview_includes_introspection_top_level_commands(self):
        html_text = build_command_overview_html()
        assert "<code>list-commands</code>" in html_text
        assert "<code>describe</code>" in html_text

    def test_overview_marks_read_only_and_side_effect_badges(self):
        html_text = build_command_overview_html()
        assert "read-only" in html_text
        # 書き込み系コマンドの side_effects がバッジとして表示される
        assert "db_write" in html_text

    def test_overview_groups_commands_by_top_token(self):
        html_text = build_command_overview_html()
        for group in ("annotate", "batch", "export", "images", "models", "project", "top-level"):
            assert f"<code>{group}</code>" in html_text


class TestBuildErrorCodes:
    """ErrorCode 列挙からのエラーコード一覧動的生成の検証。"""

    def test_error_codes_table_contains_every_code(self):
        html_text = build_error_codes_html()
        for code in ErrorCode:
            assert f"<code>{code.value}</code>" in html_text

    def test_error_codes_total_count_matches_enum(self):
        html_text = build_error_codes_html()
        assert f"全 {len(ErrorCode)} 種" in html_text

    def test_error_codes_categorized_into_shared_ai_pagination(self):
        html_text = build_error_codes_html()
        assert "共有" in html_text
        assert "AI 固有" in html_text
        assert "pagination" in html_text


class TestBuildCliReferenceHtml:
    """リファレンス全体ドキュメントの検証 (7 バンド + 総覧)。"""

    @pytest.fixture(scope="class")
    def document(self) -> str:
        return build_cli_reference_html()

    def test_document_explains_output_mode_resolution(self, document: str):
        assert "--json" in document
        assert "LORAIRO_CLI_JSON" in document
        assert "ADR 0058" in document

    def test_document_explains_stdout_stderr_separation(self, document: str):
        assert "stdout=JSONL" in document
        assert "stderr" in document

    def test_document_lists_three_kinds(self, document: str):
        assert "<code>item</code>" in document
        assert "<code>result</code>" in document
        assert "<code>error</code>" in document

    def test_document_explains_error_contract_and_exit_codes(self, document: str):
        assert "RESULT_SET_TOO_LARGE" in document
        assert "retryable" in document
        assert "user_action_required" in document
        # exit code 0/2/1 の説明
        assert "<code>0</code>" in document
        assert "<code>2</code>" in document
        assert "<code>1</code>" in document

    def test_document_explains_introspection_commands(self, document: str):
        assert "list-commands" in document
        assert "describe" in document
        assert "json_schema" in document

    def test_document_explains_bounded_pagination(self, document: str):
        assert "count-first" in document
        assert "<code>total</code>" in document
        assert "<code>has_more</code>" in document
        assert "500" in document

    def test_document_includes_agent_driving_flow(self, document: str):
        assert "project create" in document
        assert "images register" in document
        assert "annotate run" in document
        assert "export create" in document


class TestCliReferenceWidget:
    """ウィジェットの生成と遅延コンテンツ生成の検証。"""

    def test_widget_creation_does_not_build_content(self, qtbot):
        widget = CliReferenceWidget()
        qtbot.addWidget(widget)
        assert widget.content_loaded is False

    def test_show_event_builds_content_once(self, qtbot):
        widget = CliReferenceWidget()
        qtbot.addWidget(widget)
        widget.show()
        qtbot.waitUntil(lambda: widget.content_loaded, timeout=5000)
        text = widget._browser.toPlainText()
        assert "CLI 契約リファレンス" in text
        assert "コマンド総覧" in text

    def test_ensure_content_is_idempotent(self, qtbot):
        widget = CliReferenceWidget()
        qtbot.addWidget(widget)
        widget.ensure_content()
        first_html = widget._browser.toHtml()
        widget.ensure_content()
        assert widget._browser.toHtml() == first_html
        assert widget.content_loaded is True

    def test_content_contains_dynamic_command_paths(self, qtbot):
        widget = CliReferenceWidget()
        qtbot.addWidget(widget)
        widget.ensure_content()
        text = widget._browser.toPlainText()
        for spec in iter_tool_specs():
            assert spec.path in text
