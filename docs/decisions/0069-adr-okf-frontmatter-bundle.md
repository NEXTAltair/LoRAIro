---
type: ADR
title: ADR を OKF バンドル化し frontmatter を SSoT にする
status: Accepted
timestamp: 2026-06-19
tags: [Process, Documentation]
---
# ADR 0069: ADR を OKF バンドル化し frontmatter を SSoT にする

## Context

`docs/decisions/` 配下の ADR には次の 3 つの課題があった。

1. **メタデータの書式分裂**: 日付やステータスが本文中に散在し、太字箇条書き(`- **日付**` / `- **ステータス**`)、英語箇条書き(`- Date` / `- Status`)、`## Status` 節、非太字(`- Status:`)、メタデータなしの 5 系統に分裂していた。
2. **README テーブルへの手動転記による二重管理**: 各 ADR のタイトル・日付・ステータスを `README.md` のテーブルへ手動転記していたため、本文と README の間で乖離が発生していた(例: 0029 は本文が `Accepted (Revised: …)` である一方、README は `Accepted` のままだった)。この乖離を監視するためだけに `scripts/check_adr_drift.py` が存在していた。
3. **番号衝突と索引漏れ**: 並列 worktree での起票により、`0042` が 3 ファイル、`0043` が 2 ファイル重複して存在していた。そのうち 3 件が README の索引から漏れていた。

[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) は、YAML frontmatter 付き Markdown のディレクトリを知識バンドルとして扱う最小限のフォーマットである。ADR はほぼそのまま OKF バンドルとして管理できる。

## Decision

ADR 群を OKF バンドルとして管理し、各 ADR の YAML frontmatter を唯一の正本(SSoT)とする。

### frontmatter スキーマ

```yaml
---
type: ADR                       # 必須 (OKF SPEC §4.1 の唯一の必須キー)
title: <タイトル>
status: <下記の語で始める。必要なら (詳細) を付ける>
timestamp: <YYYY-MM-DD 決定日, ISO 8601>
tags: [<任意のドメインタグ>]
# 任意: superseded_by: ["NNNN"], deciders: <名前>
---
```

- **本文にスカラー値のメタデータを置かない**: 日付、ステータス、Deciders は frontmatter に集約し、本文は Context・Decision・Rationale・Consequences の記述に専念させる。
- **`status` の書式**: `Proposed`、`Accepted`、`Implemented`、`Deprecated`、`Superseded`、`Rejected` のいずれかで始める。補足が必要な場合は ` (…)` を後ろに付与してよい(例: `Accepted (amended by 0060)`)。
- **ADR 番号の扱い**: ADR 番号(`NNNN`)はファイル名から導出する概念 ID とし、frontmatter には持たない(OKF ではファイルパスが概念 ID となる)。
- **見出しの統一**: H1 は `# ADR NNNN: <タイトル>` に統一する。

### 派生ビューの自動生成

- `README.md` のテーブルと `index.md` は、frontmatter から決定論的に生成し、手動では編集しない。
- 生成および検証は、汎用スキル `okf-bundle`(`.agents/skills/okf-bundle/`)に含まれる標準ライブラリのみのスクリプトで実行する。
  - `okf_validate.py`: frontmatter の検証(必須キー `type`、ISO 日付、予約ファイル名など)を行う。
  - `okf_index.py`: `index.md` の生成、および frontmatter キーで列を指定する Markdown テーブルの生成を行う。
- 索引の再生成は `make adr-index`、検証は `make adr-okf` で実行する。

### 生成の駆動方針(CI では自動実行しない)

索引の再生成は CI で強制せず、薄い汎用スキルをエージェントが判断して起動する方針とする(ADR 0039 の PR 保守自走と同じ思想)。生成処理自体は決定論的スクリプトに委ねるため、許容するリスクは「実行漏れにより索引が一時的に古くなること」のみであり、内容の乖離は原理的に発生しない。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. frontmatter=SSoT + 生成(OKF) | メタデータを frontmatter に集約し、索引を自動生成する | **採用** |
| B. 現状維持 + 乖離監視の強化 | README への手動転記を続け、乖離をツールで検出する | 却下(二重管理が残る) |
| C. frontmatter 化するが索引も手編集 | frontmatter とテーブルを両方手で書く | 却下(二重管理が残る) |

- **二重管理の構造的な解消**: SSoT を frontmatter に一本化し、`index.md` と `README.md` を生成物にすることで、手動同期の作業がゼロになり、既存の本文・README 間の乖離も解消する。
- **OKF 準拠による可搬性**: ベンダー中立な形式であるため、Obsidian、MkDocs、LLM などの外部ツールでも ADR をそのまま活用できる。
- **スキルの汎用性**: `okf-bundle` はプロジェクト非依存かつ標準ライブラリのみで動作する。列指定も frontmatter キーで行えるため、他リポジトリの知識ベースや用語集など任意の OKF バンドルへ再利用できる。

## Consequences

### 良い点

- frontmatter が機械可読な SSoT となり、README や索引の手動同期が不要になる。
- 索引から漏れていた ADR も自動生成された一覧に必ず現れ、番号衝突も可視化される。
- `okf-bundle` スキルを全エージェントおよび他プロジェクトで共有利用できる。

### トレードオフ

- ADR を追加・変更した際に `make adr-index` での再生成が必要になる(エージェントがスキルで実行する)。実行を忘れても索引が一時的に古くなるだけで、ADR 本体の内容は壊れない。
- 既存 71 件の一括移行で本文を SSoT として採用した結果、README の日付・ステータス表示が本文準拠に変わる(旧 README の簡略表記との差異は #777 で後続精査する)。

### 適用範囲

- `scripts/check_adr_drift.py` は frontmatter の `status` を読む形へ改修する。参照ファイルが ADR より新しいことを検出する `REFERENCE-DRIFT` 機能は、引き続きプロジェクト固有ロジックとして残す。
- 番号衝突していた孤立 ADR 3 件は `0070`–`0072` へ採番し直した(#777)。

## Related

- [Open Knowledge Format SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- ADR 0039: Agent PR Maintenance Automation(エージェント判断で運用を回す思想の先例)
- Issue #777
