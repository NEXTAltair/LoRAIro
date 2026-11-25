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
PARTIAL_FAILURE_MIGRATION = (
    "### 部分失敗と既存スクリプトの移行 (#1313)\n"
    "\n"
    "次のコマンドは、集計結果を出力した後に、部分成功なら終了コード 3、"
    "全件失敗なら終了コード 1 で終了します。人間向けの出力でも同じ終了コードを使用します。\n"
    "\n"
    "- `images register` / `images update` / `images process`\n"
    "- `annotate run` / `annotate import-batch`\n"
    "- `batch submit` / `batch import`\n"
    "- `errors resolve`\n"
    "- `export create`\n"
    "- `review run`\n"
    "- `tags translations add --file`\n"
    "\n"
    "JSONL 出力の終端行は、従来どおり `kind=result` と各件数フィールドを維持しており、"
    "`status` と `ok` で結果を判定できます。ただし旧形式の `images update` と "
    "`tags translations add --file` は互換性のため従来の出力形式(`ok=true`)を維持しているため、"
    "それぞれ `failed_tags` または `errors` と終了コードを併せて確認してください。"
    "なお、`annotate run --run-id ID` の安全な再開手順は "
    "[再開契約](cli-annotation-resume.md) を参照してください。\n"
    "\n"
    "| `status` | `ok` | 終了コード | 意味 |\n"
    "|---|---|---|---|\n"
    "| `success` | `true` | 0 | 成功、対象 0 件、重複・取り込み済みの正常スキップ、"
    "正常なドライラン |\n"
    "| `partial_success` | `false` | 3 | 成功または正常スキップを含み、一部が失敗 |\n"
    "| `failed` | `false` | 1 | 成功した対象がなく失敗 |\n"
    "\n"
    "#### コマンド別の確認ポイント\n"
    "\n"
    "- **画像登録(`images register`)**: `errors` と `error_details` を確認します。\n"
    "- **旧バッチ結果の取り込み(`annotate import-batch`)**: "
    "`parse_errors`、`save_errors`、`unmatched` とあわせて、`unmatched_ids` および "
    "`error_details` を確認します。ドライランでも解析エラーや未一致があれば失敗扱いになります。\n"
    "- **プロバイダーバッチの取り込み(`batch import`)**:\n"
    "  - 従来の `skipped` には、正常スキップと取り込み不能の両方が含まれます。"
    "詳細は新しいフィールド(`already_imported`、`non_importable`、`save_skipped`、"
    "`missing_custom_ids`、`failed_custom_ids`、`error_details`)で確認してください。\n"
    "  - `incomplete=true` の場合は、`batch status JOB_ID --project PROJECT` と"
    "保存済みの項目エラーを確認してください。\n"
    "  - 保存結果が件数のみで部分成功した ID を特定できない場合、`failed_custom_ids` には"
    "保存完了を確認できない候補が保守的に含まれます。この一覧だけを根拠に全件を再送信せず、"
    "必ず保存状態を確認してください。\n"
    "  - 対象が空の結果は終了コード 0 ですが、`job_imported=false` の場合は"
    "ジョブ全体が完了したわけではありません。\n"
    "- **エラー解決(`errors resolve`)**: 重複を除いた要求件数 `requested` と、"
    "実際の更新件数 `resolved` を出力します。リポジトリ処理の失敗や存在しない ID の指定により"
    "更新件数が不足した場合は、1 件でも更新できていれば終了コード 3、更新できなければ終了コード 1 "
    "になります。既に解決済みの存在する ID は、従来どおり再更新して成功扱いとします。\n"
    "\n"
    "#### 既存スクリプトの移行方針\n"
    "\n"
    "以前のバージョンでは、これらの部分失敗でも終了コード 0 が返る場合がありました。"
    "終了コードのみで後続処理へ進む既存スクリプトは、次のように見直してください。\n"
    "\n"
    "- 終了コード 3(部分成功)と終了コード 1(全件失敗)を区別し、成功件数を記録する。\n"
    "- 登録済みの画像や送信済みのバッチジョブを全件再送信するような自動再試行は行わない。\n"
    "- 例外によって集計結果を返せない場合は、従来どおり `kind=error` と安定したエラーコードが"
    "出力されるため、こちらもあわせて処理する。"
)
OUTPUT_OPTION_MIGRATION = (
    "#### `--output` の移行 (#1310)\n"
    "\n"
    "`annotate run` は、アノテーション結果をプロジェクト DB に保存するコマンドです。"
    "従来の `--output`(`-o`)オプションは未実装のまま、指定先へファイルを出力せずに成功していました。"
    "そのため現在は非推奨とし、値が指定された場合はプロジェクト確認・DB 接続・モデルや設定の取得・"
    "推論・出力先アクセスのいずれよりも前に `INVALID_INPUT`(終了コード 2)で拒否します。"
    "空文字列、存在しないパス、書き込みできないパスを指定した場合も同じ動作です。\n"
    "\n"
    "既存スクリプトを移行する際は、次の手順で対応してください。\n"
    "\n"
    "- `annotate run` から `--output DIR` を削除し、アノテーション完了後に同じプロジェクトと"
    "明示的な対象 ID を指定して `export create` を実行する。\n"
    "- 以前の実行結果が既に DB に保存されている場合は、出力ファイルがないことだけを理由に"
    "アノテーションを再実行せず、保存内容を確認してからエクスポートする。\n"
    "\n"
    "なお、`--output` を指定しない場合の DB 保存、推論の部分失敗、保存失敗に関する動作は"
    "従来どおり維持されます。"
)


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
        f"- Strict read only: `{str(spec.read_only).lower()}` (root `--read-only`; see [contract](cli-read-only.md))",
        f"- Conditional initialization: `{spec.tool_payload()['conditional_side_effects']}`",
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
        "LoRAIro のコマンドラインインターフェース(CLI)です。"
        "GUI のない環境でも、データセット管理やバッチ処理、プログラムからの自動操作を行えます。",
        "",
        "## インストール",
        "",
        "```bash",
        "uv sync",
        "lorairo-cli --help",
        "```",
        "",
        "設定ファイルや保存先を固定したい場合は、ルートオプションの `--workspace DIR` や "
        "`--config FILE` を指定します。詳しくは "
        "[workspace/config の優先順位と移行](cli-workspace-config.md) を参照してください。",
        "",
        "## 基本的な使い方",
        "",
        "OpenAI Moderation を使って未評価画像にレーティングを付与する手順は、"
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
        "## GUI との同時利用(DB ロックの制約)",
        "",
        "LoRAIro の画像データベースには SQLite を採用しています。"
        "SQLite は複数のプロセスから同時に読み取れますが、"
        "**同時に書き込めるのは 1 プロセスのみ**です(ADR 0067)。"
        "GUI を起動したまま CLI を併用する際は、次の点に注意してください。",
        "",
        "- **検索や一覧の読み取りは併用できます**: WAL モードを有効にしているため、"
        "GUI が書き込み中でも CLI の読み取り処理はブロックされにくくなります。",
        "- **書き込みの同時実行は避けてください**: GUI と CLI が同じプロジェクト DB へ同時に書き込む"
        "(アノテーション保存、画像登録、タグ編集など)と、一時的な競合が発生します。"
        "`PRAGMA busy_timeout`(既定 30 秒、`config/lorairo.toml` の `[database] busy_timeout_ms`)"
        "により短時間の競合は自動で待機・再試行されますが、"
        "長時間の書き込みを双方で同時に実行するのは推奨しません。",
        "- **ロック競合時は再試行できます**: 待機時間を超えてもロックが解放されない場合、"
        "CLI は `CONFLICT` エラー(`retryable=true`)とともに"
        "「他プロセスの書き込み完了を待って再試行」というヒントを返します。"
        "GUI でも同様の日本語メッセージが表示されます。"
        "どちらも入力内容を変えずに再試行すれば成功する場合があります。",
        "- **CLI で更新した後は GUI を再読み込みしてください**: CLI から DB を更新しても、"
        "GUI のメモリ上にある検索結果や件数表示は自動で更新されません。"
        "CLI を併用した後は、GUI 側で**再検索または再読み込み**を行ってください。",
        "- **GUI 稼働中の CLI は `uv run --no-sync` で起動してください(Windows、#1190)**: "
        "Windows では GUI が共有仮想環境(venv)の `Scripts\\lorairo.exe` をロックします。"
        "この状態で `uv run lorairo-cli` を実行すると、暗黙の同期処理がエントリーポイントの再生成に"
        "失敗して中断し、`lorairo-cli.exe` が消えたまま仮想環境が部分破損することがあります。"
        "`uv run --no-sync lorairo-cli ...` を使えば仮想環境を書き換えずに安全に実行できます。"
        "破損した場合は、GUI を終了してから `uv sync --dev` で復旧してください"
        "(GUI を止めずに使う応急処置は "
        '`uv run --no-sync python -c "from lorairo.cli.main import main; main()" ...` です)。',
        "",
        "なお、大量のアノテーション処理を GUI と CLI で同時に実行する使い方は現状では想定していません。"
        "本格的な複数プロセスからの同時書き込みが必要になった場合は、PostgreSQL などへの移行を別途検討します。",
        "",
        "## Exit Code",
        "",
        "例外発生時の終了コードは、エラーコードから機械的に決定されます"
        "(`src/lorairo/cli/_errors.py`)。",
        "",
        "| 終了コード | 意味 |",
        "|---|---|",
        "| 0 | 成功 |",
        "| 2 | 入力・検証エラー(引数の不正、フィルタの未指定など) |",
        "| 1 | 全件失敗、またはその他の実行時エラー |",
        "| 3 | 部分成功(成功または正常スキップと失敗が混在) |",
        "",
        *PARTIAL_FAILURE_MIGRATION.splitlines(),
        "",
        "## Machine-Readable Introspection",
        "",
        "ADR 0059 に従い、イントロスペクション機能では既存の JSONL 種別"
        "(`item`、`result`、`error`)のみを使用します。"
        "`tool`、`model`、`schema` は、`item` ペイロード内の `type` フィールドで表します。",
        "",
        "```bash",
        "lorairo-cli --json list-commands",
        'lorairo-cli --json describe "images update"',
        'lorairo-cli --json describe "annotate run" --schema json_schema',
        "```",
        "",
        "各コマンドの出力仕様は次のとおりです。",
        "",
        '- **`list-commands`**: 各コマンドを `kind:"item", type:"tool"` として出力し、'
        "`read_only` と `side_effects` を含めます。",
        '- **`describe`(既定の `compact` 形式)**: `type:"model"` の行で、'
        "入力・出力・エラーの簡易フィールド一覧を返します。"
        "各フィールドの `schema` には、制約を含む対応プロパティが入ります。",
        '- **`describe --schema json_schema`**: Pydantic 由来の公開スキーマを '
        '`type:"schema"` の `item` 行に包んで返します。',
        "",
        "スキーマ生成と公開範囲には、次のルールを適用しています。",
        "",
        "- 入力スキーマは登録済みの Typer/Click 定義(型・必須・既定値・範囲)から導出し、"
        "`compact` 形式も同じ Pydantic スキーマから生成します。"
        "既定値が定義されているフィールドは、`null` を含めて公開します。",
        "- JSON Schema の `x-cli-options` と `x-cli-destinations` により、"
        "CLI のオプション名・短縮別名と Python パラメータの対応を確認できます。",
        "- `images search` では、`ImagesSearchInput` が CLI 引数、"
        "`ImageSearchQuery` が渡す JSON 本体のスキーマを表します。",
        "- 処理本体で行う排他チェック、ID 件数制限、ファイル内容の検証については、"
        "各フィールドの説明も併せて参照してください。なお、生 SQL や DB スキーマは公開しません。",
        "- 自己記述コマンドである `describe` と `list-commands` は操作コマンド一覧に含めません。"
        "この方針は終端の `result` 行の `excluded_commands` に明示し、"
        "`count` は従来どおり列挙した操作コマンドの件数を返します。"
        "また、各操作について `item` と終端 `result` の両モデルを公開します。",
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
