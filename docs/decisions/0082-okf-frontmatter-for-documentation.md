---
type: ADR
title: 通常ドキュメントにも OKF frontmatter を付け SSoT 化する
status: Accepted
timestamp: 2026-06-29
tags: [Process, Documentation]
---
# ADR 0082: 通常ドキュメントにも OKF frontmatter を付け SSoT 化する

## Context

ADR 0069 により、`docs/decisions/` 配下の ADR は [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) バンドルとなり、YAML frontmatter を SSoT として索引を生成する運用へ移行した。一方で、通常の `docs/**/*.md`、`local_packages/image-annotator-lib/docs/**/*.md`、`local_packages/genai-tag-db-tools/docs/**/*.md` には共通の frontmatter 規約が存在しない。

このため、次の 3 つの課題が生じている。

1. **横断検索と索引化ができない**: 文書種別(Guide、Reference、Contract 等)、ドメイン(annotation、search、db-write 等)、依存技術(pyside6、sqlalchemy 等)が機械可読でない。その結果、3 リポジトリを横断した絞り込みができず、エージェントが関連文書を見つけにくい。
2. **メタデータの所在が統一されていない**: 作成日、状態、対象ドメインが本文の散文に埋もれており、形式がそろわない。
3. **ADR と通常ドキュメントで運用が非対称である**: ADR だけが OKF 化されており、通常ドキュメントがその恩恵を受けられていない。

ADR 向けに導入済みの `okf-bundle` スキル(Python 標準ライブラリのみで動作し、プロジェクト非依存)には検証・索引生成スクリプトがすでに備わっている。この仕組みを通常ドキュメントへ拡張できる。

## Decision

**通常ドキュメントにも OKF frontmatter を付与し、frontmatter を SSoT とする。** 語彙、適用範囲、移行戦略を以下に定める。

### frontmatter スキーマ

```yaml
---
type: Contract                 # 必須 (OKF SPEC §4.1 の唯一の必須キー)
title: tag-db CLI JSONL Contract
status: Accepted
timestamp: 2026-06-29          # ISO 8601 (YYYY-MM-DD)
tags: [cli, search, db-read, tag-normalization]
depends_on: [pydantic, sqlalchemy, sqlite]
---
```

- **`type`(必須)**: 文書種別。`ADR`、`Guide`、`Reference`、`Contract`、`Plan`、`Investigation`、`Report` のいずれかを選ぶ。
- **`title`(任意)**: 表示用タイトル。
- **`status`(任意)**: ADR 0069 と統一する。`Draft` または `Proposed` で始め、`Accepted`、`Implemented`、`Deprecated`、`Superseded`、`Rejected` のいずれかを先頭に置く。補足は `(…)` や `(...)` で後ろに付与してよい。
- **`timestamp`(任意)**: 作成日、決定日、または最終重要更新日。ISO 8601 形式(`YYYY-MM-DD`)で記述する。
- **`tags`(任意)**: 機能、責務、動作を表す**抽象的な**分類(下記の語彙一覧から選ぶ)。**技術名は入れない**。
- **`depends_on`(任意)**: 文書内容が強く依存する技術、ライブラリ、外部仕様(下記の語彙一覧から選ぶ)。

### 持たないフィールド

- **`version`**: 版や鮮度は `timestamp` と Git 履歴で管理するため、frontmatter には版番号を持たない。
- **`packages`**: 内部パッケージ名はファイルパス(`local_packages/<pkg>/docs/…`)から判別できるため不要とする。

### 語彙一覧(最小構成・拡張時は本 ADR を改訂)

語彙の無秩序な増加を防ぐため最小限から始め、追加が必要になった場合は本 ADR を改訂する。

- **`type`(7 種)**:
  `ADR` / `Guide` / `Reference` / `Contract` / `Plan` / `Investigation` / `Report`
- **`tags`(機能・責務・動作。技術名は禁止)**:
  `annotation` / `image-editing` / `image-import` / `image-export` / `dataset-export` /
  `search` / `db-read` / `db-write` / `db-migration` / `tag-normalization` / `tag-conversion` /
  `model-selection` / `model-registry` / `provider-batch` / `webapi` / `gui-view` / `gui-widget` /
  `worker` / `service-layer` / `config` / `logging` / `validation` / `error-handling` / `performance` /
  `cli` / `process`
- **`depends_on`(技術・ライブラリ・外部仕様)**:
  `pyside6` / `sqlalchemy` / `sqlite` / `alembic` / `pydantic` / `pydanticai` / `litellm` /
  `torch` / `transformers` / `huggingface-hub` / `openai-api` / `anthropic-api` / `google-genai`

### 適用範囲

**必須対象(frontmatter を付与する)**:

- `docs/**/*.md`
- `local_packages/image-annotator-lib/docs/**/*.md`
- `local_packages/genai-tag-db-tools/docs/**/*.md`

なお、`docs/decisions/*.md` は ADR 0069 のルールを継続する(別個の OKF バンドルとして全件で frontmatter 必須)。

**対象外(frontmatter 不要)**:

- `README.md`、`CHANGELOG.md`、`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`
- `index.md`、`log.md`(OKF の予約ファイル名)
- 生成ドキュメント: 再生成で上書きされるため**手書きで frontmatter を入れない**。索引化したい場合は生成スクリプト側から出力する(例: `docs/cli.md` は `scripts/generate_cli_docs.py` が frontmatter を出力するため、`--skip-missing` 検証の対象に残る)。
- 外部ツールが固有フォーマットを要求するファイル(例: `SKILL.md` は `name` と `description` の frontmatter を持つ)。

### 移行戦略(判断付きバックフィルと遅延移行の併用)

全ファイルを未付与許容にして触ったときだけ付与する純粋な遅延移行では、日常的に参照される中核ドキュメントへの横断検索・索引化が当面機能しない。そのため、ハイブリッド方式を採用する。

- **即時付与(中核ドキュメント)**: 本 ADR の導入 PR で、LoRAIro 本体の中核ドキュメントに frontmatter を付与する。対象は `architecture`、`services`、`integrations`、`testing`、`technical`、`provider-batch-api`、`development-workflow`、`documentation-maintenance`、`lessons-learned`、`cli` など、`CLAUDE.md` やドキュメントハブから恒常的に参照される文書とする。
- **遅延付与(更新時に付与)**: 一過性または履歴的なドキュメント(`investigations/`、`specs/`、`plans/`、`migration*`、`skill-evaluations/`、`archived_ui/` 等)は、新規作成または実質的な更新を行う際に付与する。
- **`local_packages`(サブモジュール)**: `image-annotator-lib` と `genai-tag-db-tools` のドキュメントは別リポジトリ(サブモジュール)であるため、各サブモジュールの PR フローで付与する(中核文書は追従 PR、その他は更新時に付与)。本 ADR で規約を定め、`make docs-okf` の検証対象に含める(未付与ファイルは `--skip-missing` で合格とする)。

検証には `okf-bundle` の `okf_validate.py --skip-missing` を使用する。frontmatter 未付与のファイルは違反とせず合格させ、付与済みファイルのみ `type` 必須と `timestamp` の ISO 8601 形式を強制する。一方、`docs/decisions` は全件必須のため `--skip-missing` を付けない(ADR 0069 を維持)。

### 検証の駆動方針(CI で強制しない)

ADR 0069 および ADR 0039 と同様に、検証は CI で強制せず**エージェントが判断して起動**する。`make docs-okf` で 3 バンドルに対して `--skip-missing` 検証を実行する。生成と検証を決定論的スクリプトに委ねるため、起こり得るのは実行漏れのみであり、内容の乖離は原理的に発生しない。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. frontmatter の SSoT 化 + 遅延移行 + 判断付きバックフィル(本 ADR) | OKF を通常ドキュメントへ拡張し、中核は即時付与、残りは更新時に付与する | **採用** |
| B. 全 117 件の一括バックフィル | すべてのドキュメントに今すぐ frontmatter を付与する | 却下(人手負荷が大きく、分類が機械的でないため一括作業では誤りやすい) |
| C. 純粋な遅延移行(ツール導入のみ・即時付与なし) | `--skip-missing` のみ追加し、付与は更新時に限定する | 却下(中核ドキュメントの索引化が当面効かず、目的を達成できない) |
| D. 適用しない(ADR のみ OKF 維持) | 通常ドキュメントは規約なしのままにする | 却下(横断検索やエージェント参照の課題が解消しない) |

- **ADR 0069 の資産を再利用できる**: `okf-bundle` スキルは `--bundle-root` で任意ディレクトリに適用できる汎用ツールである。`--skip-missing` を追加するだけで通常ドキュメントへ展開できる。
- **段階移行により作業負荷を平準化できる**: 参照価値の高い中核ドキュメントを即座に索引化しつつ、残りの文書は更新のタイミングで無理なく移行できる。
- **検索軸を分離できる**: `tags` を抽象的な機能分類、`depends_on` を技術依存に分けることで、「何についての文書か」と「何に依存するか」を別軸で検索できる。

## Consequences

### 良い点

- ドキュメントの種別、ドメイン、依存技術が機械可読になり、3 リポジトリを横断して絞り込める。
- ADR と通常ドキュメントが同一の OKF 規約にそろい、`okf-bundle` の仕組みを共通利用できる。
- 遅延移行を併用することで、一括バックフィルの過度な負荷を避けられる。

### トレードオフ

- ドキュメントを新規作成または実質更新するたびに、エージェントが判断して frontmatter を付与する必要がある。
- 語彙を固定しているため、新しいドメインや技術が登場した際は本 ADR の改訂が必要になる。
- 通常ドキュメントでは当面は検証のみを導入し、索引生成は見送る(`okf_index.py` による索引生成は将来別途検討する)。

### 導入時の変更範囲

- `okf_validate.py` に `--skip-missing` オプションを追加する(frontmatter 未付与を違反にしない)。
- `Makefile` に `docs-okf` ターゲットを追加する(3 バンドルに対して `--skip-missing` 検証を実行する)。
- `docs/documentation-maintenance.md` に運用ルールへのポインタを追記する。

## Related

- [Open Knowledge Format SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- ADR 0069: ADR を OKF バンドル化し frontmatter を SSoT にする
- ADR 0039: Agent PR Maintenance Automation(エージェントの判断で運用を回す思想の先例)
- `okf-bundle` スキル(`.agents/skills/okf-bundle/`)
- Issue #971
