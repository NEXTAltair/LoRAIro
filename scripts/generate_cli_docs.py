"""Generate docs/cli.md from CLI introspection specs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lorairo.cli.introspection import FieldSpec, ModelSpec, ToolSpec, iter_tool_specs  # noqa: E402

OUTPUT = ROOT / "docs" / "cli.md"


def _field_text(field: FieldSpec) -> str:
    required = "required" if field.required else "optional"
    default = f", default `{field.default}`" if field.default is not None else ""
    description = f" - {field.description}" if field.description else ""
    return f"- `{field.name}`: `{field.type}` ({required}{default}){description}"


def _model_section(model: ModelSpec) -> list[str]:
    lines = [f"**{model.role.title()} `{model.name}`**"]
    if model.description:
        lines.append("")
        lines.append(model.description)
    if model.fields:
        lines.append("")
        lines.extend(_field_text(field) for field in model.fields)
    return lines


def _tool_section(spec: ToolSpec) -> list[str]:
    lines = [
        f"### `{spec.path}`",
        "",
        spec.summary,
        "",
        f"- Read only: `{str(spec.read_only).lower()}`",
        f"- Side effects: {', '.join(f'`{effect}`' for effect in spec.side_effects)}",
        "",
        "#### Compact Introspection",
        "",
        "```bash",
        f'lorairo-cli --json describe "{spec.path}"',
        "```",
        "",
        "#### Models",
        "",
    ]
    for model in (*spec.inputs, *spec.outputs, *spec.errors):
        lines.extend(_model_section(model))
        lines.append("")
    if spec.search_schema is not None:
        lines.extend(
            [
                "#### JSON Schema",
                "",
                "This search-driven command exposes the public `ImageFilterCriteria` schema:",
                "",
                "```bash",
                f'lorairo-cli --json describe "{spec.path}" --schema json_schema',
                "```",
                "",
            ]
        )
    return lines


def render() -> str:
    lines = [
        # OKF frontmatter (ADR 0082)。生成ファイルなので generator から emit し、
        # 再生成で消えないようにする。鮮度は Git 履歴で追う (timestamp は持たない)。
        "---",
        "type: Reference",
        "title: LoRAIro CLI ドキュメント",
        "status: Accepted",
        "tags: [cli, annotation, dataset-export]",
        "---",
        "# LoRAIro CLI ドキュメント",
        "",
        "LoRAIro のコマンドラインインターフェース（CLI）。GUI なし環境でのデータセット管理、",
        "バッチ処理、プログラマティックアクセスを提供します。",
        "",
        "## インストール",
        "",
        "```bash",
        "uv sync",
        "lorairo-cli --help",
        "```",
        "",
        "## 基本的な使い方",
        "",
        "OpenAI Moderation で未評価画像に rating を付与する CLI 手順は",
        "[CLI Rating Preflight Workflow](cli-rating-preflight.md) を参照してください。",
        "",
        "```bash",
        "lorairo-cli --help",
        "lorairo-cli project --help",
        "lorairo-cli version",
        "lorairo-cli status",
        "```",
        "",
        # 運用ノート (#1164): 手書きで docs/cli.md に足すと再生成で消えるため、
        # generator が emit する固定 preamble として保持する。
        "## GUI との同時利用 (DB ロックの制約)",
        "",
        "LoRAIro の画像 DB は SQLite です。SQLite は同時読み取りは可能ですが、**同時書き込みは",
        "1 プロセスのみ**に制限されます (ADR 0067)。GUI を開いたまま CLI を併用する場合、次の点に",
        "注意してください。",
        "",
        "- **検索・一覧 (read) は併用しやすい**: WAL モードのため、GUI の書き込み中でも CLI の",
        "  読み取りはブロックされにくいです。",
        "- **書き込みの同時実行は避ける**: GUI と CLI が同時に同じプロジェクト DB へ書き込む",
        "  (アノテーション保存・画像登録・タグ編集など) と一時的に競合します。`PRAGMA busy_timeout`",
        "  (既定 30 秒、`config/lorairo.toml` の `[database] busy_timeout_ms`) により短時間の競合は",
        "  自動で待機・再試行されますが、長時間の書き込みを両側で同時に走らせるのは推奨しません。",
        "- **ロック競合時の表示**: 待機時間を超えてロックが解放されない場合、CLI は `CONFLICT`",
        "  エラー (`retryable=true`) と「他プロセスの書き込み完了を待って再試行」のヒントを返します。",
        "  GUI も同様の日本語メッセージを表示します。いずれも入力を変えずに再試行すれば成功し得ます。",
        "- **CLI で書き換えた後の GUI 表示**: CLI が DB を更新しても、GUI のメモリ上の検索結果・",
        "  件数表示は自動更新されません。CLI 併用後は GUI 側で **再検索 / 再読み込み**してください。",
        "",
        "大量アノテーションを GUI と CLI で同時実行するようなワークロードは現状の想定外です。本格的な",
        "複数 writer 対応が必要になった場合は PostgreSQL 等への移行を別途検討します。",
        "",
        "## Exit Code",
        "",
        "exit code はエラーコードから機械的に導出されます (`src/lorairo/cli/_errors.py`):",
        "",
        "| exit code | 意味 |",
        "|---|---|",
        "| 0 | 成功 |",
        "| 2 | 入力・検証エラー (引数不正、フィルタ未指定等) |",
        "| 1 | その他の実行時エラー |",
        "",
        "## Machine-Readable Introspection",
        "",
        "ADR 0059 に従い、introspection は既存 JSONL kind の `item` / `result` / `error`",
        "だけを使います。`tool` / `model` / `schema` は `item` payload の `type` フィールドです。",
        "",
        "```bash",
        "lorairo-cli --json list-commands",
        'lorairo-cli --json describe "images update"',
        'lorairo-cli --json describe "annotate run" --schema json_schema',
        "```",
        "",
        '`list-commands` は各コマンドを `kind:"item", type:"tool"` として出力し、',
        "`read_only` と `side_effects` を含めます。`describe` の既定 `compact` は",
        '`type:"model"` 行で入力・出力・エラーの簡易フィールドを返します。',
        '`--schema json_schema` は Pydantic 由来の公開スキーマを `type:"schema"` の',
        "`item` 行に包みます。検索駆動コマンドは公開フィルタ契約",
        "`ImageFilterCriteria` を晒しますが、生 SQL や DB スキーマは晒しません。",
        "",
        "## Command Reference",
        "",
        "> Generated by `scripts/generate_cli_docs.py`. Edit introspection specs, then regenerate.",
        "",
    ]
    for spec in iter_tool_specs():
        lines.extend(_tool_section(spec))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUTPUT.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
