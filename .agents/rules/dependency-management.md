---
trigger: model_decision
description: "依存パッケージを追加・更新するとき。AI 推論 SDK は最新追従、他は計画的 bump"
---

# 依存パッケージ管理ルール

AI 推論 SDK は他の依存パッケージと更新頻度が質的に異なる。そのため、AI 推論 SDK は最新追従を原則とし、それ以外の依存は計画的なバージョン更新(bump)で運用を分ける。

> **プロジェクト固有:** パッケージマネージャ(`uv`、`poetry`、`npm` など)固有のコマンド、lockfile 名、CI と同等のテストフィルタコマンドは導入先で追記する。

## 核心ルール

**AI 推論 SDK は常に最新の安定版を使う。** 古い SDK では新モデルのレスポンス形式を正しく解析できず、推論が失敗することがある(発端となった事例は導入先の記録を参照すること)。

## 最新追従の対象となる SDK

以下のライブラリを「常に最新」の対象とする。

- `pydantic-ai`:エージェント推論のオーケストレーション
- `anthropic`:Anthropic API クライアント
- `openai`:OpenAI API クライアント
- `google-genai`:Google Gemini API クライアント
- `litellm`:モデルレジストリと機能判別データベース
- `transformers`:ローカル機械学習推論
- `huggingface-hub`:モデルのダウンロード
- `torch` / `torchvision`:ローカル機械学習バックエンド

## `pyproject.toml` のバージョン指定方針

- **下限(lower bound)のみを指定する**(`>=` 表記を使う)。
- **上限(upper bound、`<X.Y`)は付けない。**
- 例外として、下位互換性の破壊が確認されたマイナーまたはメジャーリリースに限り、一時的に上限を追加する。この場合、追従修正を行う PR で上限を外す。

```toml
# 正しい
"pydantic-ai>=1.97",
"anthropic>=0.102",
"transformers>=4.50",

# 禁止: 上限指定でアップグレードを抑止しない
"pydantic-ai>=1.97,<2.0",
"anthropic==0.102.0",
```

## lockfile の更新タイミング

lockfile は git 管理下に置き、SDK を積極的に更新する方針とする(lockfile 管理方針の詳細は導入先の記録を参照すること)。

1. **新モデル対応や WebAPI のバグ修正 PR で更新する**
   ```bash
   uv lock --upgrade-package pydantic-ai --upgrade-package anthropic
   ```
2. **ベンダリング依存や submodule 依存の固定バージョン更新時に、該当 SDK を更新する**
3. **月次の依存レビュー(毎月 1 日前後)で一括更新する**
   ```bash
   uv lock --upgrade
   # CI と同等のフィルタで全テストが通ることを確認し、label `dependency review` を付けて PR を起票する
   ```

## 最新追従を適用しない依存(計画的更新)

以下のカテゴリはメジャーバージョンで API やスキーマが破壊されるため、計画的に更新する。

| カテゴリ | 例 | 運用方針 |
|---|---|---|
| UI / GUI | `PySide6`、`qt-material` | メジャー変更時に手動で移行する |
| DB / マイグレーション | `SQLAlchemy`、`Alembic` | スキーマの整合性を確認し、マイグレーションを同時に更新する |
| テストフレームワーク | `pytest`、`pytest-qt`、`pytest-bdd` | テストランナーの互換性を確認して更新する |
| 汎用ライブラリ | `Pillow`、`loguru`、`polars` など | 通常の依存更新として扱う |

## 更新時の回帰確認

SDK を更新する前後で、**CI と完全に一致するテストフィルタ(CI-equivalent filter)** を必ず実行する。

```bash
# 例(実際のフィルタは導入先のテストルール文書を参照)
pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```

自動テストでは実 API を呼び出さないため、実 API での挙動確認は手動のスモークテストで行う。

## PR 運用ルール

- 依存更新を含む PR では、マニフェスト(`pyproject.toml` など)と lockfile を必ず同時にコミットする。
- submodule やベンダリング依存の固定バージョンを更新する PR では、依存先パッケージ側と本体側の両方の lockfile を更新する。
- SDK のメジャーリリースや破壊的変更を含むマイナーリリースが公式に告知されている場合は、PR の説明欄にその旨を明記する。
- 月次の依存レビュー PR には `dependency review` ラベルを付与する。

## 判断フロー

1. 対象のパッケージが AI 推論 SDK に該当する場合は、常に最新へ追従し、下限のみを指定する。
2. UI、DB、テストフレームワークに該当する場合は、計画的に更新し、メジャー変更時は手動で移行する。
3. 上記のいずれにも該当しない場合は、通常の依存更新として運用する。

## 関連

> **プロジェクト固有:** 本ルールを支える ADR や Issue へのリンクを追記する。
