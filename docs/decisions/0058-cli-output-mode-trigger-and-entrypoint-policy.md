# ADR 0058: CLI Output Mode Trigger and Entry-Point Policy

- **日付**: 2026-06-05
- **ステータス**: Proposed
- **関連 Issue**: #634 (epic) / #637 / #636

## Context

ADR 0057 は CLI の機械可読 (JSONL) 出力契約とエラー契約を定めたが、**いつ JSONL を出すか (出力モードの
トリガ)** と **CLI/GUI のエントリポイント方針** は未定で、0057 はその決定に依存して保留されていた。本 ADR が
それを確定する。

LoRAIro は既に `lorairo` (GUI) と `lorairo-cli` (CLI) の 2 entry を持ち、CLI は Typer 製で rich 人間向け
出力が育っている (`console.print` 158 箇所等)。sibling の `genai-tag-db-tools` は単一 entry `tag-db` +
`--gui` フラグで、help は GUI を import せず headless-safe (tag-db ADR 0002)。ただし **LoRAIro は GUI 主体**
のアプリであり、CLI/DB ツール主体の tag-db とは性質が異なる。

## Decision

### 1. 出力モードのトリガ = 明示 `--json` グローバルフラグ

`lorairo-cli` にグローバル `--json` フラグを追加する (callback `_configure`、`--log-level` と同列)。既定は
オフ = rich 人間向け出力。`--json` 指定で ADR 0057 の JSONL 機械可読契約に切り替える。

env `LORAIRO_CLI_JSON=1` を併設し、agent / CI が環境変数でも有効化できる (既存 `LORAIRO_CLI_MODE` と同じ
流儀)。明示フラグを env より優先する。

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

### 4. CLI は Qt-free 不変条件

`lorairo-cli` 経路は PySide6 / Qt を import しない。entry が分離していることでこれを**構造的に保証**し、
headless (server / CI / agent) 安全性と起動速度を担保する。

### 5. help / `-h` / no-args は人間向け launcher meta 例外

`lorairo-cli` の `--help` / `-h` / 引数なし (Typer `no_args_is_help`) は人間向け help を stdout に出し
exit 0 で終わる。callback (`_configure`) は走らず (Issue #540)、`--json` 指定下でも help は人間向けのまま。
ADR 0057 の「コマンド実行は `result` / `error` で終わる」不変条件の**文書化例外**とする。

対して `version` / `status` は `@app.command()` の**実コマンド**であり、`--json` 時は他コマンド同様 JSONL
(`result`) を出す。meta の help と実コマンドを区別する。

## Rationale

- **明示 `--json`**: agent は `describe` / docs で契約を知り明示的に script するため、magic 自動判定より
  明示フラグの方が安定・テスト容易。gh / docker と同じ慣習。
- **装飾とフォーマットの分離**: 「色を pipe で消す」は presentation の最適化、「JSONL に切替」は契約の選択。
  混ぜると pipe 時に契約が勝手に変わり人間が驚く。分離すれば両方を予測可能に扱える。
- **entry 分離維持**: LoRAIro は GUI 主体。GUI に専用 entry を与え CLI を Qt-free に保つ方が、単一 entry に
  統合して Qt を遅延 import するより堅い (構造保証 + 既存 entry を壊さない)。
- **help 例外**: help は人間がコマンドを発見する meta 操作で、機械契約の対象外。tag-db ADR 0002/0003 と
  同じ思想。

## Consequences

- `lorairo-cli` に `--json` グローバルフラグ + env を実装し、ADR 0057 の `_emit` / 出力経路がこのモードを
  SSoT として参照する。中央エラー境界 (ADR 0057 §7) のモード分岐もこのフラグを見る。
- 色 / progress の TTY 抑制ロジックを `_console` / 出力層に入れる。
- entry は現状維持のため **console_scripts 変更なし** (`lorairo` / `lorairo-cli` 据え置き)。破壊的変更なし。
- `version` / `status` を `--json` 対応に改修する (現状は rich 固定)。
- ADR 0057 の保留理由 (トリガ未定) が解消され、0057 と本 ADR は対で Accepted へ進める。

## 関連

- ADR 0057 (CLI Machine-Readable JSONL Output and Error Contract) — 本 ADR が出力モードのトリガ (`--json`) を供給し、0057 の前提依存を解消する
- ADR 0020 (CLI Message Language Policy) — 人間向け / 機械向けメッセージの言語方針
- ADR 0049 (Apply CLI Image List Limit in the Repository Query) — read/list 系の挙動
- tag-db ADR 0002 (CLI/GUI Entrypoint Policy) — 思想の参照元 (LoRAIro は GUI 主体ゆえ entry を分離する点が差分)
