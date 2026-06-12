"""CLI リファレンスタブ (Wireframes v11 Frame 8 / Issue #756)。

GUI と並ぶ第二の操作面である ``lorairo-cli`` の機械可読契約を、GUI 内で読みやすく
図解する読み取り専用リファレンス。コマンド実行機能は持たない。

コマンド総覧とエラーコード一覧は ``lorairo.cli.introspection.TOOL_SPECS`` /
``lorairo.cli._errors.ErrorCode`` から動的生成し、CLI 本体とのドキュメント drift を
構造的に防ぐ (Issue #756 推奨事項)。説明文の静的バンドは ADR 0057/0058/0059/0060 の
確定契約に基づく固定文。

HTML 生成ロジックは Qt 非依存のモジュール関数に分離し、ユニットテスト可能にする。
"""

from __future__ import annotations

import html
import re

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from ...utils.log import logger

# ---------------------------------------------------------------------------
# 配色 (HANDOFF.md Frame 8 スタイルメモのダークペイン風、QTextBrowser 対応の範囲)
# ---------------------------------------------------------------------------
_PANE_BG = "#23211d"
_PANE_FG = "#d6d3cd"
_COLOR_KEY = "#9ecbff"
_COLOR_STR = "#a5d6a7"
_COLOR_NUM = "#ffcc80"
_COLOR_BOOL = "#f48fb1"
_COLOR_MUTED = "#8a877f"

_BADGE_READ_ONLY = "#2e7d32"
_BADGE_SIDE_EFFECT = "#b26a00"
_CHIP_BG = "#eceae6"
_CHIP_FG = "#4a4742"

# JSONL 1 行を着色するための簡易トークナイザ。
# "key": / "string" / true|false|null / 数値 の 4 種を判別する。
_JSON_TOKEN_RE = re.compile(
    r'("(?:[^"\\]|\\.)*")(\s*:)|("(?:[^"\\]|\\.)*")|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)'
)


def _esc(text: str) -> str:
    """HTML 特殊文字をエスケープする。"""
    return html.escape(text, quote=False)


def highlight_jsonl(line: str) -> str:
    """JSONL 1 行に色分け ``<span>`` を付与した HTML を返す。

    Args:
        line: 生の JSONL 1 行 (valid JSON である必要はない)。

    Returns:
        キー / 文字列 / 真偽値 / 数値を色分けした HTML 断片。
    """

    def _replace(match: re.Match[str]) -> str:
        key, colon, string, boolean, number = match.groups()
        if key is not None:
            return f'<span style="color:{_COLOR_KEY}">{_esc(key)}</span>{colon}'
        if string is not None:
            return f'<span style="color:{_COLOR_STR}">{_esc(string)}</span>'
        if boolean is not None:
            return f'<span style="color:{_COLOR_BOOL}">{boolean}</span>'
        return f'<span style="color:{_COLOR_NUM}">{number}</span>'

    return _JSON_TOKEN_RE.sub(_replace, line)


def _pane(title: str, lines: list[str], *, highlight: bool = True) -> str:
    """ダーク端末風ペインの HTML を返す。

    Args:
        title: ペイン左上のラベル (例: ``stdout``)。
        lines: 表示する行のリスト。
        highlight: True なら各行に JSONL 色分けを適用する。

    Returns:
        ``<table>`` ベースのペイン HTML。
    """
    rendered = "<br/>".join(highlight_jsonl(line) if highlight else _esc(line) for line in lines)
    return (
        f'<table width="100%" bgcolor="{_PANE_BG}" cellpadding="8" cellspacing="0">'
        f'<tr><td><span style="color:{_COLOR_MUTED}; font-family:monospace; font-size:8pt">'
        f"{_esc(title)}</span><br/>"
        f'<span style="color:{_PANE_FG}; font-family:monospace">{rendered}</span>'
        f"</td></tr></table>"
    )


def _chip(text: str, color: str = _CHIP_FG, bg: str = _CHIP_BG) -> str:
    """ADR 参照などの小さなチップ HTML を返す。"""
    return (
        f'<span style="background-color:{bg}; color:{color}; font-family:monospace; font-size:8pt">'
        f"&nbsp;{_esc(text)}&nbsp;</span>"
    )


def _badge_for_spec(read_only: bool, side_effects: tuple[str, ...]) -> str:
    """read-only / side_effect バッジの HTML を返す。

    Args:
        read_only: コマンドが読み取り専用かどうか。
        side_effects: introspection の side_effects タプル。

    Returns:
        バッジ HTML 断片。
    """
    if read_only:
        return f'<b><span style="color:{_BADGE_READ_ONLY}">read-only</span></b>'
    effects = ", ".join(side_effects) if side_effects else "side_effect"
    return f'<span style="color:{_BADGE_SIDE_EFFECT}">{_esc(effects)}</span>'


def build_command_overview_html() -> str:
    """``TOOL_SPECS`` からコマンド総覧テーブルの HTML を動的生成する。

    グループ (path の先頭トークン) ごとに節を分け、各コマンドに read-only /
    side_effect バッジと summary を付ける。``list-commands`` / ``describe`` は
    introspection 専用 top-level コマンドとして静的に補記する。

    Returns:
        コマンド総覧セクションの HTML。
    """
    # 起動時間への影響を避けるため、CLI introspection はここで遅延 import する
    from ...cli.introspection import iter_tool_specs

    specs = iter_tool_specs()
    groups: dict[str, list[str]] = {}
    for spec in specs:
        parts = spec.path.split()
        group = parts[0] if len(parts) > 1 else "top-level"
        row = (
            f"<tr><td><code>{_esc(spec.path)}</code></td>"
            f"<td>{_badge_for_spec(spec.read_only, spec.side_effects)}</td>"
            f"<td>{_esc(spec.summary)}</td></tr>"
        )
        groups.setdefault(group, []).append(row)

    # introspection 専用の top-level コマンド (TOOL_SPECS 外) を補記する
    static_rows = [
        (
            "<tr><td><code>list-commands</code></td>"
            f'<td><b><span style="color:{_BADGE_READ_ONLY}">read-only</span></b></td>'
            "<td>全コマンドを kind:item / type:tool で一覧する (ADR 0059)。</td></tr>"
        ),
        (
            "<tr><td><code>describe</code></td>"
            f'<td><b><span style="color:{_BADGE_READ_ONLY}">read-only</span></b></td>'
            "<td>コマンドの入出力モデルを compact / json_schema で開示する (ADR 0059)。</td></tr>"
        ),
    ]
    groups.setdefault("top-level", []).extend(static_rows)

    total = len(specs) + 2
    sections: list[str] = [f"<h2>コマンド総覧 ({total} サブコマンド)</h2>"]
    ordered = sorted(groups, key=lambda name: (name == "top-level", name))
    for group in ordered:
        rows = groups[group]
        sections.append(f"<h3><code>{_esc(group)}</code> ({len(rows)})</h3>")
        sections.append(
            '<table width="100%" cellpadding="4" cellspacing="0" border="0">'
            "<tr>"
            '<th align="left" width="28%">コマンド</th>'
            '<th align="left" width="30%">バッジ</th>'
            '<th align="left">概要</th>'
            "</tr>" + "".join(rows) + "</table>"
        )
    return "".join(sections)


def build_error_codes_html() -> str:
    """``ErrorCode`` 列挙からエラーコード一覧テーブルを動的生成する。

    共有 / AI 固有 / pagination の 3 カテゴリへ仕分けし、列挙に新コードが
    追加された場合は共有カテゴリに自動で現れる (drift 防止)。

    Returns:
        エラーコード一覧の HTML。
    """
    # 起動時間への影響を避けるため、CLI エラー契約はここで遅延 import する
    from ...cli._errors import ErrorCode

    ai_codes = {ErrorCode.RESOURCE_EXHAUSTED, ErrorCode.AUTH_ERROR, ErrorCode.RATE_LIMITED}
    pagination_codes = {ErrorCode.RESULT_SET_TOO_LARGE}

    def _category(code: ErrorCode) -> str:
        if code in ai_codes:
            return "AI 固有"
        if code in pagination_codes:
            return "pagination"
        return "共有"

    rows = "".join(
        f"<tr><td><code>{code.value}</code></td><td>{_category(code)}</td></tr>" for code in ErrorCode
    )
    return (
        f"<p>エラーコードは全 {len(ErrorCode)} 種。"
        "<code>code</code> で機械分岐し、<code>retryable</code> / "
        "<code>user_action_required</code> フラグで再試行戦略を決める。</p>"
        '<table cellpadding="4" cellspacing="0" border="0">'
        '<tr><th align="left" width="50%">code</th><th align="left">カテゴリ</th></tr>'
        f"{rows}</table>"
    )


def build_cli_reference_html() -> str:
    """CLI リファレンス全体の HTML ドキュメントを生成する。

    HANDOFF.md Frame 8 の 7 バンド構成 (契約 / 2 ペイン / kind / エラー契約 /
    introspection / pagination / agent フロー) + コマンド総覧を 1 つの
    リッチテキストにまとめる。

    Returns:
        ``QTextBrowser.setHtml`` に渡す完全な HTML 文字列。
    """
    parts: list[str] = []
    parts.append("<h1>CLI 契約リファレンス</h1>")
    parts.append(
        "<p><code>lorairo-cli</code> は GUI と並ぶ<b>第二の操作面</b>。"
        "既存 CLI に被せた機械可読契約レイヤーにより、エージェントや自動化スクリプトが "
        "stdout の JSONL だけを読んで安全に駆動できる。本タブは読み取り専用のリファレンスであり、"
        "コマンドは実行しない。</p>"
    )

    # --- バンド 1: 契約 + 出力モード解決 ---
    parts.append("<h2>1. 機械可読契約と出力モード解決</h2>")
    parts.append(
        f"<p>{_chip('ADR 0057')} JSONL &amp; 構造化エラー契約&nbsp;&nbsp;"
        f"{_chip('ADR 0058')} 出力モード解決&nbsp;&nbsp;"
        f"{_chip('ADR 0059')} introspection&nbsp;&nbsp;"
        f"{_chip('ADR 0060')} bounded pagination</p>"
    )
    parts.append(
        "<p>出力モードの優先順位: <code>--json</code> / <code>--no-json</code> フラグ &gt; "
        "環境変数 <code>LORAIRO_CLI_JSON</code> &gt; 既定の rich (人間向け表示)。"
        "エージェントは常に <code>--json</code> を明示するのが安全。</p>"
    )

    # --- バンド 2: stdout=JSONL / stderr=ログ ---
    parts.append("<h2>2. stdout=JSONL / stderr=ログ の分離</h2>")
    parts.append(
        "<p>stdout は機械可読 JSONL 専用 (1 行 = 1 つの valid JSON object)。"
        "ログ・進捗・装飾はすべて stderr に出る。パイプで stdout だけを受ければ"
        "JSON パースが壊れない。</p>"
    )
    parts.append(
        _pane(
            "$ lorairo-cli --json images list --project demo --fetch  (stdout)",
            [
                '{"kind": "item", "image_id": 1, "file_path": "image_dataset/.../001.png"}',
                '{"kind": "item", "image_id": 2, "file_path": "image_dataset/.../002.png"}',
                '{"kind": "result", "ok": true, "count": 2, "total": 2, "has_more": false}',
            ],
        )
    )
    parts.append(
        _pane(
            "(stderr)",
            [
                "2026-06-11 10:00:00 | INFO | プロジェクトDB接続: demo",
                "2026-06-11 10:00:00 | INFO | 検索完了: 2件",
            ],
            highlight=False,
        )
    )

    # --- バンド 3: 3 つの kind ---
    parts.append("<h2>3. 3 つの kind</h2>")
    parts.append(
        "<p>stdout JSONL の <code>kind</code> は次の 3 種に閉じる (進捗用 event kind は採用しない)。</p>"
    )
    parts.append(
        '<table cellpadding="4" cellspacing="0" border="0">'
        '<tr><th align="left" width="14%">kind</th><th align="left">意味</th></tr>'
        "<tr><td><code>item</code></td><td>結果 1 件 (0 行以上)。検索ヒット・登録結果などの行データ。</td></tr>"
        "<tr><td><code>result</code></td><td>終端サマリー (成功時は必ず最後に 1 行)。<code>ok</code> と件数情報を含む。</td></tr>"
        "<tr><td><code>error</code></td><td>構造化エラー (失敗時は最後に 1 行)。下のエラー契約を参照。</td></tr>"
        "</table>"
    )

    # --- バンド 4: 構造化エラー契約 ---
    parts.append("<h2>4. 構造化エラー契約</h2>")
    parts.append(
        _pane(
            "error JSONL 例",
            [
                '{"kind": "error", "ok": false, "code": "RESULT_SET_TOO_LARGE", '
                '"message": "Matched 12000 images (limit 500).", "retryable": false, '
                '"user_action_required": true, "hint": "検索条件を追加して 500 件以下に絞ってください。"}',
            ],
        )
    )
    parts.append(build_error_codes_html())
    parts.append(
        "<p>exit code: <code>0</code> = 成功 / <code>2</code> = 入力エラー "
        "(<code>INVALID_INPUT</code>, <code>VALIDATION_FAILED</code>, "
        "<code>RESULT_SET_TOO_LARGE</code>) / <code>1</code> = 実行時エラー (その他)。</p>"
    )

    # --- バンド 5: introspection ---
    parts.append("<h2>5. introspection (自己記述)</h2>")
    parts.append(
        "<p>コマンド一覧とスキーマは CLI 自身から取得できる。"
        "introspection も既存の <code>item</code> / <code>result</code> kind だけを使い、"
        "<code>type</code> フィールドで <code>tool</code> / <code>model</code> / "
        "<code>schema</code> を区別する。</p>"
    )
    parts.append(
        _pane(
            "introspection の使い方",
            [
                "$ lorairo-cli --json list-commands",
                '{"kind": "item", "type": "tool", "name": "images list", "path": "images list", '
                '"read_only": true, "side_effects": ["db_read", "file_read"]}',
                "...",
                '$ lorairo-cli --json describe "images update"',
                '$ lorairo-cli --json describe "annotate run" --schema json_schema',
            ],
        )
    )

    # --- バンド 6: bounded pagination ---
    parts.append("<h2>6. bounded pagination (count-first)</h2>")
    parts.append(
        "<p>list 系コマンドは count-first: 既定はマッチ件数 (<code>total</code>) のみを返し、"
        "<code>--fetch</code> 指定時だけ行データを返す。作業集合の上限は 500 件で、"
        "超過すると <code>RESULT_SET_TOO_LARGE</code> エラーになる "
        "(<code>limit</code> / <code>offset</code> は 500 件以内のページングであり、上限の回避手段ではない)。"
        "<code>result</code> 行の <code>count</code> / <code>total</code> / <code>has_more</code> で"
        "残量を判断する。</p>"
    )

    # --- バンド 7: agent driving flow ---
    parts.append("<h2>7. エージェント駆動フロー例</h2>")
    parts.append(
        "<ol>"
        "<li><code>project create</code> — プロジェクトを作成</li>"
        "<li><code>images register</code> — 画像を登録</li>"
        "<li><code>annotate run</code> — AI アノテーションを実行</li>"
        "<li><code>export create</code> — データセットを書き出し</li>"
        "</ol>"
        "<p>各ステップで <code>kind</code> を見て分岐する: <code>error</code> なら <code>code</code> と "
        "<code>retryable</code> で再試行/修正を判断し、<code>result</code> の <code>has_more</code> が "
        "true なら条件を絞って続行する。</p>"
    )

    # --- コマンド総覧 (TOOL_SPECS から動的生成) ---
    parts.append(build_command_overview_html())

    return "".join(parts)


class CliReferenceWidget(QWidget):
    """CLI 契約リファレンスを表示する読み取り専用ウィジェット。

    コンテンツはタブが初めて表示されたときに遅延生成する
    (TOOL_SPECS の import / HTML 構築コストを起動時に払わない)。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """ウィジェットを初期化する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._content_loaded = False
        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._browser)

    def showEvent(self, event: QShowEvent) -> None:
        """初回表示時にリファレンスコンテンツを生成する。"""
        super().showEvent(event)
        self.ensure_content()

    def ensure_content(self) -> None:
        """リファレンス HTML を未生成なら生成して表示する (冪等)。"""
        if self._content_loaded:
            return
        self._browser.setHtml(build_cli_reference_html())
        self._content_loaded = True
        logger.debug("CLI リファレンスコンテンツを生成")

    @property
    def content_loaded(self) -> bool:
        """コンテンツ生成済みかどうか。"""
        return self._content_loaded
