# ADR 0058: CLI Output Mode Trigger and Entry-Point Policy

- **日付**: 2026-06-05
- **ステータス**: Accepted
- **関連 Issue**: #634 (epic) / #637 / #636

## Context

ADR 0057 は CLI の機械可読 (JSONL) 出力契約とエラー契約を定めたが、**いつ JSONL を出すか (出力モードの
トリガ)** と **CLI/GUI のエントリポイント方針** は未定で、0057 はその決定に依存して保留されていた。本 ADR が
それを確定する。

LoRAIro は既に `lorairo` (GUI) と `lorairo-cli` (CLI) の 2 entry を持ち、CLI は Typer 製で rich 人間向け
出力が育っている (`console.print` 158 箇所等)。sibling の `genai-tag-db-tools` は単一 entry `tag-db` +
`--gui` フラグで、help は GUI を import せず headless-safe (tag-db ADR 0002)。ただし **LoRAIro は GUI 主体**
のアプリであり、CLI/DB ツール主体の tag-db とは性質が異なる。

## Scope / Non-Goals

本 ADR は出力モードの **トリガとエントリ方針の決定** を固定する。Click/Typer の具体的な起動・パース機構
(`standalone_mode`、`no_args_is_help` の内部挙動、オプションの位置解決の実装) は実装 Issue (#640) で確定し、
本 ADR は「raw argv/env で Click パース前にモードを解決する」という要件レベルの決定に留める。

## Decision

### 1. 出力モードのトリガ = 明示 `--json` グローバルフラグ

`lorairo-cli` にグローバルな **tri-state `--json` / `--no-json` フラグ**を追加する (callback `_configure`、
`--log-level` と同列)。既定は未指定 (None)。`--json` で ADR 0057 の JSONL 機械可読契約に切り替え、
`--no-json` で rich 人間向けを明示する。

env `LORAIRO_CLI_JSON=1` を併設し、agent / CI が環境変数でも JSONL を有効化できる (既存 `LORAIRO_CLI_MODE`
と同じ流儀)。**解決順序は「明示フラグ > env > 既定 rich」**: `--json` / `--no-json` が指定されればそれが
勝ち、未指定のときだけ env を見る。env が JSONL を有効化していても `--no-json` で rich に上書きできる
(共有 shell で env が export 済みでも個別コマンドで rich に戻せる)。正の `--json` 単独では env-on を
打ち消せないため、tri-state にして「明示フラグが env より優先」を実装可能にする。

**モードは中央エラー境界 (ADR 0057 §7) が raw `sys.argv` / env から、Click のパース前に解決する**。Click は
callback (`_configure`) より前に context を構築・パースするため、`--json` を callback option としてだけ
扱うと `lorairo-cli --json bad-option` のような parse 時 usage error がモード確定前に境界へ到達し、JSONL
ではなく人間向けエラーになってしまう。これを防ぐため境界は argv/env を自前で先読みしてモードを確定して
から Click を起動する (callback の `--json` / `--no-json` 宣言は help/補完表示用を兼ねる)。この先読みは
位置非依存で、`--json` / `--no-json` は **グローバル位置でもサブコマンド後でも**受理される
(`lorairo-cli --json annotate run` も `lorairo-cli annotate run --json` も同義。Click の global-option-only
制約による `NoSuchOption` を prescan が回避する)。

**TTY 自動判定でフォーマット契約を切り替えない**。pipe したら勝手に JSONL になる "magic" 挙動は採らない。

### 2. 装飾 (色 / progress) は presentation として TTY で自動抑制

**フォーマット契約 (rich/JSONL) と装飾 (色・progress バー) を分離する**。色・progress は stdout/stderr が
TTY でないとき自動抑制する (gh CLI と同様の presentation 最適化)。これはフォーマット契約の切替とは独立。

`--json` 時は当然 stdout に装飾を一切出さない (ADR 0057 の stdout 純度契約)。progress は ADR 0057 のとおり
stderr 限定で、非 TTY ではさらに抑制される。

### 3. エントリポイントは 2 本分離を維持 (統一しない)

`lorairo` = GUI entry、`lorairo-cli` = CLI / agent entry の **2 本を維持**する。引数 (`--gui` 等) で
GUI/CLI をモード分岐しない。

LoRAIro は GUI 主体のアプリであり、GUI に専用 entry を与えるのが自然。tag-db の「単一 entry + `--gui`」は
CLI 主体ツールの形であり、LoRAIro には合わない (この点だけ tag-db ADR 0002 と意図的に分岐する)。

### 4. CLI は headless で動作する (GUI 非依存)

`lorairo-cli` 経路は GUI (QtWidgets / QtGui / QApplication / 表示プラットフォーム) を要さず、display の
無い環境 (server / CI / agent) で動く。entry が分離し GUI を起動しないことでこれは構造的に満たされる。

**QtCore (QObject 等) の import は許容する**。QtCore は headless-safe な非 GUI モジュール (Qt 公式: display
も QApplication も要さず server / CLI 用途向け) であり、import を禁止しても得られるのは僅かな起動時間短縮の
みで、PySide6 は GUI アプリとして常にインストール済みのため install / footprint の利点も無い。よって
「PySide6 を一切 import しない」という不変条件は課さず、「GUI / display を要さない」headless 動作だけを
要件とする (重い import-ban の enforcement test も課さない)。

### 5. help / `-h` / no-args は人間向け launcher meta 例外

`lorairo-cli` の `--help` / `-h` / 引数なし (Typer `no_args_is_help`) は人間向け help を stdout に出し
exit 0 で終わる。callback (`_configure`) は走らず (Issue #540)、`--json` 指定下でも help は人間向けのまま。
ADR 0057 の「コマンド実行は `result` / `error` で終わる」不変条件の**文書化例外**とする。

対して `version` / `status` は `@app.command()` の**実コマンド**であり、`--json` 時は他コマンド同様 JSONL
(`result`) を出す。meta の help と実コマンドを区別する。

### 6. legacy `project list --format json` を deprecate し JSONL に一本化

現状 `project list --format json` は pretty JSON 配列を出す唯一の構造化出力だが、これは ADR 0057 の JSONL
契約 (`item` + 終端 `result`) と非互換。**機械可読出力の SSoT は `--json` / env による JSONL 契約に
一本化**し、`--format json` は deprecate する。2 つの非互換な機械可読形式を併存させない。

- `--json` / env が有効なときは `project list` も他の list 系同様 JSONL (`item` + `result`) を出す。
  `--format json` が同時指定されても **JSONL 契約が勝つ** (legacy 形式は無視する)。
- `--format json` (pretty 配列) は非推奨とし将来削除する。`--format table` は `--json` 非指定時の人間向け
  既定 (rich 表示) として残す。

## Rationale

- **明示 `--json`**: agent は `describe` / docs で契約を知り明示的に script するため、magic 自動判定より
  明示フラグの方が安定・テスト容易。gh / docker と同じ慣習。
- **装飾とフォーマットの分離**: 「色を pipe で消す」は presentation の最適化、「JSONL に切替」は契約の選択。
  混ぜると pipe 時に契約が勝手に変わり人間が驚く。分離すれば両方を予測可能に扱える。
- **entry 分離維持**: LoRAIro は GUI 主体。GUI に専用 entry を与え、CLI を headless 動作 (GUI 非依存) に
  保つ方が、単一 entry に統合して GUI を遅延 import するより堅い (構造保証 + 既存 entry を壊さない)。
  QtCore は headless-safe なので import 自体は問題にしない (「Qt-free」でなく「GUI-free」が実益のある不変条件)。
- **help 例外**: help は人間がコマンドを発見する meta 操作で、機械契約の対象外。tag-db ADR 0002/0003 と
  同じ思想。
- **legacy `--format json` の deprecate**: epic の目的は単一の機械可読契約。pretty 配列の legacy 形式を
  残すと 2 つの非互換な機械契約が併存し agent が混乱するため、JSONL に一本化する。

## Consequences

- `lorairo-cli` に `--json` グローバルフラグ + env を実装し、ADR 0057 の `_emit` / 出力経路がこのモードを
  SSoT として参照する。中央エラー境界 (ADR 0057 §7) のモード分岐もこのフラグを見る。
- 色 / progress の TTY 抑制ロジックを `_console` / 出力層に入れる。
- entry は現状維持のため **console_scripts 変更なし** (`lorairo` / `lorairo-cli` 据え置き)。破壊的変更なし。
- `version` / `status` を `--json` 対応に改修する (現状は rich 固定)。
- `project list --format json` (legacy pretty 配列) を deprecate し、`project list` を `--json` JSONL に
  対応させる。`--format json` は将来削除予定。
- 出力モードは中央境界が raw argv/env から Click パース前に解決する実装が必要 (callback 依存にしない)。
- ADR 0057 の保留理由 (トリガ未定) が解消され、0057 と本 ADR は対で Accepted へ進める。

## 関連

- ADR 0057 (CLI Machine-Readable JSONL Output and Error Contract) — 本 ADR が出力モードのトリガ (`--json`) を供給し、0057 の前提依存を解消する
- ADR 0020 (CLI Message Language Policy) — 人間向け / 機械向けメッセージの言語方針
- ADR 0049 (Apply CLI Image List Limit in the Repository Query) — read/list 系の挙動
- tag-db ADR 0002 (CLI/GUI Entrypoint Policy) — 思想の参照元 (LoRAIro は GUI 主体ゆえ entry を分離する点が差分)
