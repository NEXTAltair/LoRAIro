---
name: okf-bundle
version: "1.0.0"
description: "Maintain a directory of markdown docs as an Open Knowledge Format (OKF) bundle in any project: ensure each concept file has valid OKF frontmatter (required `type`, plus optional title/description/tags/timestamp), keep frontmatter the single source of truth, and regenerate the derived index.md (and an optional human-readable table) from it. Use when adding/editing concept docs (ADRs, knowledge bases, glossaries) or when a bundle's index looks stale. Project-specific drift detection stays in the project."
metadata:
  short-description: 任意プロジェクトの md 群を OKF バンドルとして保守(frontmatter=SSoT → index/表を生成・検証)。
---

# OKF バンドル保守ガイド

Markdown ファイル群のディレクトリを [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) バンドルとして保守する汎用スキルである。**frontmatter を唯一の正準ソース(SSoT)**と位置づけ、`index.md` や人間向けの表は frontmatter から生成する派生物として扱う。

このスキルはプロジェクト非依存かつ Python 標準ライブラリのみで動作する。`--bundle-root` で対象ディレクトリを指定できるため、ADR・知識ベース・用語集など任意の OKF バンドルに適用できる。

## OKF の必須ルール(SPEC v0.1)

- frontmatter の必須キーは **`type` のみ**である。`title`・`description`・`tags`・`timestamp` は任意とする。
- `status` や `timestamp` などのスカラー値メタデータは **frontmatter に記述する**。本文の散文には書かない。
- `index.md` と `log.md` は予約ファイル名であり、概念ドキュメントには使わない。`log.md` の日付は ISO 8601 形式で記述する。
- `index.md` や生成された表は**生成物**であるため、手で編集しない。

## スクリプト(`scripts/`)

すべてのスクリプトは外部依存なしで `python3` 単体で動作する。

| スクリプト | 役割 |
|---|---|
| `okf_validate.py --bundle-root DIR` | frontmatter を検証する(必須 `type`、ISO 形式の `timestamp`、`--require`・`--exclude`・`--skip-missing` に対応) |
| `okf_index.py --bundle-root DIR --index` | OKF 形式の `index.md`(箇条書き)を生成する |
| `okf_index.py --bundle-root DIR --table --columns ... --link-column ...` | frontmatter のキーを列に指定して Markdown の表を生成する |

### 主なオプションの動作

- `okf_index.py --check`: ファイルを書き込まず、生成物が最新かどうかだけを検証する(差分・ドリフトの検出)。
- `--table-output`: 出力先に `<!-- OKF-TABLE:START -->` と `<!-- OKF-TABLE:END -->` のマーカーがある場合、その区間だけを置換する。表の前後に書かれた散文を保持したまま更新できる。
- `okf_validate.py --skip-missing`: frontmatter が無いファイルを違反とみなさず除外する(段階的移行・lazy migration 用)。未付与の既存ドキュメントを許容しつつ、付与済みのファイルだけに `type` 必須や ISO `timestamp` を強制したいバンドルで使う。ADR のように全件 frontmatter 必須のバンドルには付けない。

## ワークフロー(エージェントの判断で起動)

概念ドキュメントを追加・編集・改番したら、次の手順を実行する。

1. **検証**: `python3 <skill>/scripts/okf_validate.py --bundle-root <DIR> [--exclude README.md]` を実行し、frontmatter の欠落や必須キーの漏れを補う。
2. **再生成**: `python3 <skill>/scripts/okf_index.py --bundle-root <DIR> --index ...`(必要に応じて `--table ...` も併用)で派生ビューを更新する。
3. **コミット**: 生成物を含めてコミットする(ドキュメント保守であれば `main` への直接 push を許可しているプロジェクトもある)。

CI の自動実行に頼らず、エージェントの判断で運用する。生成処理は決定論的であるため、一時的に索引が古くなることはあっても内容のドリフトは起きない。書式ブレや転記ミスを防ぐため、**索引や表を手で書き起こしてはならない**。

## プロジェクト固有の責務(スキル外)

「概念を参照しているコードが概念ドキュメントより新しい」といった参照ドリフト(REFERENCE-DRIFT)の検出は、各プロジェクトの構成に依存する。そのため本スキルには含めず、プロジェクト側のツール(LoRAIro では `scripts/check_adr_drift.py`)が担う。

## LoRAIro での使用例

```bash
# ADR バンドル検証(全件 frontmatter 必須: type,title,status,timestamp + index/README 一致確認)
python3 .agents/skills/okf-bundle/scripts/okf_validate.py --bundle-root docs/decisions --require type,title,status,timestamp --exclude README.md
make adr-okf     # 上記 validate + okf_index.py --check を一括実行
# index.md + README テーブルを再生成
make adr-index   # 内部で .agents/skills/okf-bundle/scripts/okf_index.py を呼ぶ

# 通常ドキュメント検証(lazy migration: 未付与は skip、付与済みのみ検証。ADR 0082)
make docs-okf    # docs / iam-lib docs / genai-tag docs を --skip-missing で検証
```
