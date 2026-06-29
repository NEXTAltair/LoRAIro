---
type: ADR
title: 通常ドキュメントにも OKF frontmatter を付け SSoT 化する
status: Accepted
timestamp: 2026-06-29
tags: [Process, Documentation]
---
# ADR 0082: 通常ドキュメントにも OKF frontmatter を付け SSoT 化する

## Context

ADR 0069 で `docs/decisions/` の ADR は [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
バンドルとなり、YAML frontmatter を SSoT として索引を生成する運用に移行した。一方で、
通常の `docs/**/*.md`・`local_packages/image-annotator-lib/docs/**/*.md`・
`local_packages/genai-tag-db-tools/docs/**/*.md` には共通の frontmatter 規約が無い。

このため次の課題がある。

1. **横断検索・索引化ができない**: ドキュメントの種別 (Guide / Reference / Contract …)・
   ドメイン (annotation / search / db-write …)・依存技術 (pyside6 / sqlalchemy …) が機械可読でなく、
   3 リポジトリ横断でドキュメントを絞り込めない。エージェントが関連ドキュメントを見つけにくい。
2. **メタデータの所在が不定**: 作成日・状態・対象ドメインが本文の散文に埋もれ、フォーマットが揃わない。
3. **ADR との非対称**: ADR だけ OKF 化され、通常ドキュメントは恩恵を受けていない。

ADR は OKF バンドル化済みで `okf-bundle` スキル (stdlib only・プロジェクト非依存) の
検証/索引生成スクリプトが既にある。通常ドキュメントへも同じ仕組みを拡張できる。

## Decision

**通常ドキュメントにも OKF frontmatter を付け、frontmatter を SSoT とする。** 語彙・適用範囲・
移行戦略を以下で定める。

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

- **`type`** (必須): 文書種別。`ADR` / `Guide` / `Reference` / `Contract` / `Plan` /
  `Investigation` / `Report` から選ぶ。
- **`title`** (任意): 表示タイトル。
- **`status`** (任意): ADR 0069 と統一。`Draft` / `Proposed` で始め、`Accepted` / `Implemented` /
  `Deprecated` / `Superseded` / `Rejected` のいずれかで始める。詳細は ` (…)` で付与してよい。
- **`timestamp`** (任意): 作成日・決定日・最終重要更新日。`YYYY-MM-DD` (ISO 8601)。
- **`tags`** (任意): 機能・責務・動作の**抽象的な**分類 (下記語彙)。**技術名は入れない**。
- **`depends_on`** (任意): 文書内容が強く依存する技術・ライブラリ・外部仕様 (下記語彙)。

### 持たないフィールド

- **`version`**: 版・鮮度は `timestamp` と Git 履歴で扱う。frontmatter に版番号を持たない。
- **`packages`**: 内部 package 名はファイルパス (`local_packages/<pkg>/docs/…`) で判別できるため不要。

### 語彙 (最小限・拡張は本 ADR を改訂)

**`type`** (7 種):
`ADR` / `Guide` / `Reference` / `Contract` / `Plan` / `Investigation` / `Report`

**`tags`** (機能・責務・動作。技術名は禁止):
`annotation` / `image-editing` / `image-import` / `image-export` / `dataset-export` /
`search` / `db-read` / `db-write` / `db-migration` / `tag-normalization` / `tag-conversion` /
`model-selection` / `model-registry` / `provider-batch` / `webapi` / `gui-view` / `gui-widget` /
`worker` / `service-layer` / `config` / `logging` / `validation` / `error-handling` / `performance` /
`cli` / `process`

**`depends_on`** (技術・ライブラリ・外部仕様):
`pyside6` / `sqlalchemy` / `sqlite` / `alembic` / `pydantic` / `pydanticai` / `litellm` /
`torch` / `transformers` / `huggingface-hub` / `openai-api` / `anthropic-api` / `google-genai`

語彙は最小限から始め、必要が出たら本 ADR を改訂して追加する (`tags`/`depends_on` の語彙ドリフトを防ぐ)。

### 適用範囲

**必須対象** (frontmatter を付ける):

- `docs/**/*.md`
- `local_packages/image-annotator-lib/docs/**/*.md`
- `local_packages/genai-tag-db-tools/docs/**/*.md`

`docs/decisions/*.md` は ADR 0069 ルールを継続する (別 OKF バンドル・全件 frontmatter 必須)。

**対象外** (frontmatter 不要):

- `README.md` / `CHANGELOG.md` / `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`
- `index.md` / `log.md` (OKF 予約ファイル名)
- 生成ドキュメント (generated docs)
- 外部ツールが固有フォーマットを要求するファイル (例: `SKILL.md` は `name`/`description` frontmatter を持つ)

### 移行戦略 (判断付きバックフィル + lazy)

純 lazy (全ファイルを skip し、触ったときだけ付与) では、横断検索・索引化が「今アクティブに
参照される中核ドキュメント」に当面効かない。よってハイブリッドにする。

- **eager (今付与)**: 本 ADR 導入 PR では LoRAIro 本体の中核ドキュメント
  (`architecture` / `services` / `integrations` / `testing` / `technical` / `provider-batch-api` /
  `development-workflow` / `documentation-maintenance` / `lessons-learned` / `cli` 等、CLAUDE.md /
  docs ハブから恒常的に参照されるもの) に frontmatter を付ける。
- **lazy (触るとき)**: 一過性・履歴的なドキュメント (`investigations/` / `specs/` / `plans/` /
  `migration*` / `skill-evaluations/` / `archived_ui/` 等) は、新規作成・実質更新するときに付与する。
- **local_packages (submodule)**: `image-annotator-lib` / `genai-tag-db-tools` の docs は別リポジトリ
  (submodule) なので、各 submodule 自身の PR フローで付与する (中核 docs は追従 PR、その他は lazy)。
  本 ADR は規約を定め、`make docs-okf` の検証対象に含める (未付与は `--skip-missing` で pass)。

検証は `okf-bundle` の `okf_validate.py --skip-missing` で行い、frontmatter 未付与ファイルは
違反にせず pass、付与済みファイルだけ `type` 必須 / `timestamp` ISO 8601 を強制する。
`docs/decisions` は全件必須なので `--skip-missing` を付けない (ADR 0069 のまま)。

### 駆動方針 (CI 自走しない)

ADR 0069 / ADR 0039 と同様、検証は CI で強制せず**エージェントが判断で起動**する。
`make docs-okf` で 3 バンドルを `--skip-missing` 検証する。生成・検証は決定論スクリプトに
委ねるため、許容するのは「実行漏れ」だけで内容ドリフトは原理的に発生しない。

## Rationale

| 選択肢 | 概要 | 採否 |
|-------|------|------|
| A. frontmatter=SSoT + lazy 移行 + 判断付きバックフィル (本 ADR) | OKF を通常 docs へ拡張。中核は今付与、残りは触るとき | **採用** |
| B. 全 117 件一括バックフィル | 全ドキュメントに今すぐ frontmatter を付与 | 却下: 人手負荷大・分類が機械的でなく一括は誤りやすい |
| C. 純 lazy (ツールのみ・即時付与なし) | `--skip-missing` だけ追加、付与は触るときのみ | 却下: 中核 docs の索引化が当面効かず目的を達しない |
| D. 適用しない (ADR のみ OKF) | 通常 docs は規約なしのまま | 却下: 横断検索・エージェント参照の課題が残る |

- **ADR 0069 の資産を再利用**: `okf-bundle` スキルは `--bundle-root` で任意ディレクトリに使える
  汎用 stdlib ツール。`--skip-missing` を足すだけで通常 docs へ展開できる。
- **段階移行で負荷を平準化**: 価値の高い中核 docs を即索引化しつつ、長い尾は触るときに付与する。
- **語彙を frontmatter へ寄せる設計**: `tags` を抽象的な機能分類に、`depends_on` を技術依存に
  分離することで、「何についての文書か」と「何に依存するか」を別軸で検索できる。

## Consequences

### 良い点

- ◎ ドキュメントの種別・ドメイン・依存技術が機械可読になり、3 リポジトリ横断で絞り込める。
- ◎ ADR と通常 docs が同じ OKF 規約に揃い、`okf-bundle` を共通利用できる。
- ◎ lazy 移行で一括バックフィルの負荷を負わずに済む。

### トレードオフ

- △ ドキュメントを新規作成・実質更新するたびに frontmatter 付与が必要 (エージェントが判断)。
- △ 語彙が固定されるため、新ドメイン/新技術の登場時は本 ADR の改訂が要る。
- △ 索引生成は通常 docs では当面導入せず検証のみ (将来 `okf_index.py` での索引生成は別途検討)。

### 適用範囲

- `okf_validate.py` に `--skip-missing` を追加 (frontmatter 未付与を違反にしない)。
- `Makefile` に `docs-okf` target を追加 (3 バンドルを `--skip-missing` 検証)。
- 運用ポインタを `docs/documentation-maintenance.md` に追記する。

## Related

- [Open Knowledge Format SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
- ADR 0069: ADR を OKF バンドル化し frontmatter を SSoT にする
- ADR 0039: Agent PR Maintenance Automation (エージェント判断で回す思想の先例)
- `okf-bundle` skill (`.agents/skills/okf-bundle/`)
- Issue #971
