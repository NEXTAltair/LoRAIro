---
type: ADR
title: ADR を OKF バンドル化し frontmatter を SSoT にする
status: Accepted
timestamp: 2026-06-19
tags: [Process, Documentation]
---
# ADR 0069: ADR を OKF バンドル化し frontmatter を SSoT にする

## Context

`docs/decisions/` の ADR には以下の問題があった。

1. **メタデータが本文に散文で散在し、フォーマットが分裂**: 日付/ステータスが
   `- **日付**` / `- **ステータス**` (太字 bullet)、`- Date` / `- Status` (英語 bullet)、
   `## Status` 節、`- Status:` (非太字)、メタ無し、と 5 系統に分裂していた。
2. **README テーブルへの手動転記による二重管理**: 各 ADR の title/date/status を
   `README.md` のテーブルへ手で転記しており、本文と README が drift していた
   (例: 0029 は本文 `Accepted (Revised: …)` だが README は `Accepted`)。
   その drift を監視するためだけに `scripts/check_adr_drift.py` が存在していた。
3. **番号衝突**: 並列 worktree 起票で `0042` が 3 ファイル・`0043` が 2 ファイル実在し、
   うち 3 件が README 索引から漏れていた。

[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
は「YAML frontmatter 付き Markdown のディレクトリ」を知識バンドルとして扱う最小フォーマットで、
ADR はほぼそのまま OKF バンドル化できる。

## Decision

**ADR を OKF バンドルとして管理し、各 ADR の YAML frontmatter を唯一の正準ソース (SSoT) とする。**

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

- **本文にスカラー値メタデータを置かない**。日付/ステータス/Deciders は frontmatter に集約し、
  本文は Context / Decision / Rationale / Consequences の散文に純化する。
- `status` は `Proposed` / `Accepted` / `Implemented` / `Deprecated` / `Superseded` / `Rejected`
  のいずれかで始め、詳細は ` (…)` で付与してよい (`Accepted (amended by 0060)` 等)。
- ADR 番号 (`NNNN`) は**ファイル名から導出する概念 ID**。frontmatter には持たない
  (OKF の concept ID = ファイルパス)。
- H1 は `# ADR NNNN: <タイトル>` に統一する。

### 派生ビューは生成物

- `README.md` のテーブルと `index.md` は frontmatter から**決定論的に生成**する。手編集しない。
- 生成・検証は汎用スキル `okf-bundle` (`.agents/skills/okf-bundle/`) の stdlib-only スクリプトが行う:
  - `okf_validate.py` — frontmatter 検証 (必須 `type` / ISO 日付 / 予約ファイル名)。
  - `okf_index.py` — `index.md` 生成 + 列を frontmatter キーで指定する Markdown テーブル生成。
- `make adr-index` で再生成、`make adr-okf` で検証する。

### 生成の駆動方針 (CI 自走しない)

索引の再生成は CI で強制せず、**薄い汎用スキルを Agent が判断で起動**する
(ADR 0039 の PR 保守自走と同じ思想)。生成は決定論スクリプトに委ねるため、
許容するのは「実行漏れ (索引が一時的に古い)」だけで、内容ドリフトは原理的に発生しない。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. frontmatter=SSoT + 生成 (OKF) | メタを FM に集約、索引は生成 | **採用** |
| B. 現状維持 + drift 監視強化 | README 手動転記を続け drift をツールで検出 | 却下: 二重管理が残る |
| C. FM 化するが索引も手編集 | FM とテーブルを両方手で書く | 却下: 二重管理が残る |

- **二重管理の構造的解消**: SSoT を frontmatter 1 本にし、index/README を生成物にすることで
  手動同期がゼロになる。既存の README↔本文 drift も解消する。
- **OKF 準拠の可搬性**: フォーマットがベンダー中立。ADR を他ツール (Obsidian/MkDocs/LLM) でも
  そのまま消費できる。
- **スキルの汎用性**: `okf-bundle` はプロジェクト非依存・stdlib only で、他リポジトリの
  任意の OKF バンドル (知識ベース・用語集等) にも再利用できる。列も FM キー指定で汎用。

## Consequences

### 良い点

- ◎ frontmatter が機械可読な SSoT になり、README/index の手動同期が不要になる。
- ◎ 索引から漏れていた ADR も生成索引に必ず現れる (番号衝突も可視化される)。
- ◎ `okf-bundle` スキルを全エージェント・他プロジェクトで共有利用できる。

### トレードオフ

- △ ADR を追加/変更したら `make adr-index` の再生成が必要 (Agent がスキルで実行)。
  実行漏れ時は索引が一時的に古くなるが内容は壊れない。
- △ 既存 71 件の一括移行で、本文を SSoT 採用した結果 README の日付/ステータス表示が
  本文準拠に変わる (旧 README の簡略表記との差異は #777 で後続精査)。

### 適用範囲

- `scripts/check_adr_drift.py` は frontmatter の `status` を読む形に改修し、
  REFERENCE-DRIFT (参照ファイルが ADR より新しい) は引き続きプロジェクト固有ロジックとして残す。
- 番号衝突していた orphan 3 件は `0070`–`0072` へ採番し直した (#777)。

## Related

- [Open Knowledge Format SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- ADR 0039: Agent PR Maintenance Automation (Agent 判断で回す思想の先例)
- Issue #777
