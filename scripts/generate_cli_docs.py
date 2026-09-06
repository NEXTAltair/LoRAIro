"""Generate docs/cli.md from CLI introspection specs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lorairo.cli.introspection import (  # noqa: E402
    FieldSpec,
    ModelSpec,
    ToolSpec,
    get_global_options,
    iter_tool_specs,
)

OUTPUT = ROOT / "docs" / "cli.md"


# Preserve migration guidance when regenerating the command reference.
PARTIAL_FAILURE_MIGRATION = """### 部分失敗と既存スクリプトの移行 (#1313)

`images register`、`annotate import-batch`、`batch import`、`errors resolve` は、
集計結果を返した後も失敗があれば exit 1 で終了します。人間向け出力にも同じ終了コードを適用します。
JSONL の終端は既存の `kind=result` と件数を維持し、`status` と `ok` で結果を判定できます。

| status | ok | exit | 意味 |
|---|---|---|---|
| success | true | 0 | 成功、空集合、重複/既取込みの正常skip、正常dry-run |
| partial_success | false | 1 | 成功または正常skipを含み、一部が失敗 |
| failed | false | 1 | 成功済み対象がなく失敗 |

登録は `errors` と `error_details`、legacy取込みは `parse_errors` / `save_errors` /
`unmatched` と `unmatched_ids` / `error_details` を確認します。dry-runでもparse不正や未一致は失敗です。
Batch取込みの従来 `skipped` は正常skipと取込み不能の両方を含みます。新しい `already_imported`、
`non_importable`、`save_skipped`、`missing_custom_ids`、`failed_custom_ids`、`error_details` で調査し、
`incomplete=true` の場合は `batch status JOB_ID --project PROJECT` と保存済みitemエラーを確認してください。
保存結果が件数のみで部分成功のIDを確定できない場合、`failed_custom_ids` は保存完了を確認できない候補を保守的に含めます。
この集合だけを根拠に全件再送せず、保存状態を確認してください。
空結果は exit 0 ですが、`job_imported=false` はジョブ全体の完了を意味しません。
`errors resolve` は重複を除いた `requested` と実更新件数 `resolved` を保持します。repositoryの失敗や
要求IDの未存在による更新件数不足は exit 1 です。既に解決済みの存在するIDは従来どおり再更新して成功とします。

以前はこれらの部分失敗でも exit 0 となる場合がありました。終了コードだけで後続処理へ進むスクリプトは、
exit 1 を処理し成功件数を保存してください。成功済み登録や送信済みBatchを全件再送する自動retryは行いません。
例外により集計結果を返せない場合は、従来どおり `kind=error` と安定エラーコードを出力します。"""
OUTPUT_OPTION_MIGRATION = """#### `--output` の移行 (#1310)

`annotate run` はプロジェクトDBへ注釈を保存します。従来の `--output` / `-o` は実装がなく、
指定先へファイルを書かずに成功していました。このオプションは非推奨とし、値が指定されると
プロジェクト確認・DB接続・モデル/設定取得・推論・出力先アクセスの前に `INVALID_INPUT` / exit 2 で拒否します。
空文字列、存在しないパス、書込み不能なパスも同じ契約です。

既存スクリプトでは `--output DIR` を削除し、注釈後に同じプロジェクトと明示的な対象IDを使って
`export create` を実行してください。以前の実行結果がDBに保存済みなら、出力ファイルがないことだけを
理由に注釈を再実行せず、保存内容を確認してexportしてください。`--output` 未指定時のDB保存・
推論部分失敗・保存失敗の契約は維持します。"""


def _field_text(field: FieldSpec) -> str:
    required = "required" if field.required else "optional"
    has_default = "default" in field.to_dict()
    default = f", default `{field.default}`" if has_default else ""
    description = f" - {field.description}" if field.description else ""
    aliases = (field.schema or {}).get("x-cli-options", [])
    if aliases:
        description += " (CLI: " + ", ".join(f"`{alias}`" for alias in aliases) + ")"
    return f"- `{field.name}`: `{field.type}` ({required}{default}){description}"


def _model_section(model: ModelSpec) -> list[str]:
    lines = [f"**{model.role.title()} `{model.name}`**"]
    if model.description:
        lines.append("")
        lines.append(model.description)
    if model.resolved_fields():
        lines.append("")
        lines.extend(_field_text(field) for field in model.resolved_fields())
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
    if spec.path == "annotate run":
        index = lines.index("#### Compact Introspection")
        lines[index:index] = [*OUTPUT_OPTION_MIGRATION.splitlines(), ""]
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
        "設定と保存先を固定するには root オプション `--workspace DIR` / `--config FILE` を使います。",
        "[workspace/config の優先順位と移行](cli-workspace-config.md) を参照してください。",
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
        "- **GUI 稼働中の CLI は `uv run --no-sync` で起動する (Windows, #1190)**: GUI が共有 venv の",
        "  `Scripts\\lorairo.exe` をロックしているため、`uv run lorairo-cli` の暗黙 sync が entry point",
        "  再生成に失敗して中断し、`lorairo-cli.exe` が消えたまま venv が部分破損することがあります。",
        "  `uv run --no-sync lorairo-cli ...` なら venv を書き換えず安全です。破損した場合は",
        "  GUI 終了後に `uv sync --dev` で復旧してください (GUI を止めずに使う応急処置は",
        '  `uv run --no-sync python -c "from lorairo.cli.main import main; main()" ...`)。',
        "",
        "大量アノテーションを GUI と CLI で同時実行するようなワークロードは現状の想定外です。本格的な",
        "複数 writer 対応が必要になった場合は PostgreSQL 等への移行を別途検討します。",
        "",
        "## Exit Code",
        "",
        "例外の exit code はエラーコードから機械的に導出されます (`src/lorairo/cli/_errors.py`):",
        "",
        "| exit code | 意味 |",
        "|---|---|",
        "| 0 | 成功 |",
        "| 2 | 入力・検証エラー (引数不正、フィルタ未指定等) |",
        "| 1 | その他の実行時エラー |",
        "",
        *PARTIAL_FAILURE_MIGRATION.splitlines(),
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
        "`item` 行に包みます。入力は登録済み Typer/Click の型・必須・既定値・範囲から導出し、",
        "compact も同じ Pydantic スキーマから生成します。既定値が定義されたフィールドは null を含めて公開します。",
        "各 compact フィールドの `schema` は制約を含む対応プロパティです。JSON Schema の",
        "`x-cli-options` / `x-cli-destinations` が引数・短縮別名と Python パラメータの対応を示します。",
        "`images search` の `ImagesSearchInput` は CLI 引数、`ImageSearchQuery` は渡す JSON 本体です。",
        "処理本体で行う排他・ID 件数・ファイル内容の検証はフィールド説明も参照してください。",
        "生 SQL や DB スキーマは公開しません。",
        "",
        "自己記述の `describe` / `list-commands` は操作コマンド一覧には含めません。終端 result の",
        "`excluded_commands` にこの方針を明示します。`count` は引き続き列挙した操作コマンド数です。",
        "各操作について item と終端 result の両モデルを公開します。",
        "",
        "## Command Reference",
        "",
        "> Generated by `scripts/generate_cli_docs.py`. Edit introspection specs, then regenerate.",
        "",
    ]
    lines.extend(_model_section(get_global_options()))
    lines.append("")
    for spec in iter_tool_specs():
        lines.extend(_tool_section(spec))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUTPUT.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
