---
trigger: model_decision
description: "依存パッケージを追加・更新するとき。AI 推論 SDK は最新追従、他は計画的 bump"
---

# Dependency Management Rules

依存パッケージ管理ルール。AI 推論 SDK は更新頻度が他の依存と質的に異なるため、最新追従を原則とし、それ以外は計画的な bump で運用を分ける。

> **プロジェクト固有:** パッケージマネージャ (uv, poetry, npm 等) 固有のコマンド、lockfile 名、CI と同等の pytest / test filter コマンドは導入先で追記する。

## 核心ルール

**AI 推論 SDK は常に最新の安定版を使う。** 古い SDK は新モデルのレスポンス形式を parse しきれず inference が fail することがある (発端事例は導入先の記録を参照)。

## 対象 SDK (最新追従)

以下の library は本ルールの「常に最新」対象:

- `pydantic-ai` — agentic inference orchestration
- `anthropic` — Anthropic API client
- `openai` — OpenAI API client
- `google-genai` — Google Gemini API client
- `litellm` — model registry / capability discovery DB
- `transformers` — local ML inference
- `huggingface-hub` — model download
- `torch` / `torchvision` — local ML backend

## pyproject.toml の pin 方針

- **lower bound のみ pin** (`>=` 表記)
- **upper bound (`<X.Y`) は付けない**
- 例外: 下位互換性破壊が確認された minor / major release のみ一時 upper bound 追加、追従修正 PR で外す

```toml
# 正しい
"pydantic-ai>=1.97",
"anthropic>=0.102",
"transformers>=4.50",

# 禁止: upper bound で upgrade 抑止
"pydantic-ai>=1.97,<2.0",
"anthropic==0.102.0",
```

## lockfile 更新タイミング

lockfile は git 管理下に置き、SDK は積極的に更新する方針とする (lockfile 管理方針の詳細は導入先の記録を参照):

1. **新モデル対応 / WebAPI バグ修正 PR で**:
   ```bash
   uv lock --upgrade-package pydantic-ai --upgrade-package anthropic
   ```
2. **ベンダリング/サブモジュール依存の pin 更新時に** 該当 SDK を bump
3. **月次 dependency review** (毎月 1 日近辺):
   ```bash
   uv lock --upgrade
   # → CI-equivalent filter 全 pass を確認 → PR 起票 (label: `dependency review`)
   ```

## 適用しない依存 (計画的 bump)

以下は別運用 (major version で API / schema 破壊されるため):

| カテゴリ | 例 | 運用 |
|---|---|---|
| UI / GUI | `PySide6`, `qt-material` | major 変更時に手動移行 |
| DB / migration | `SQLAlchemy`, `Alembic` | schema 整合性確認 + migration 同時更新 |
| test framework | `pytest`, `pytest-qt`, `pytest-bdd` | runner 互換性確認 |
| 汎用 library | `Pillow`, `loguru`, `polars` 等 | 通常の依存更新運用 |

## bump 時の regression check

SDK bump 前後で **CI-equivalent filter** (CI ワークフローと完全一致する test filter) を必ず実行する:

```bash
# 例 (実際のフィルタは導入先の testing ルール文書を参照)
pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
```

実 API での挙動確認は手動 smoke test で行う (自動テストは実 API を叩かない)。

## PR 運用ルール

- **依存更新を含む PR** は マニフェスト (`pyproject.toml` 等) と lockfile を **必ず同時 commit**
- **サブモジュール/ベンダリング依存の pin 更新 PR** は 依存先パッケージ側の lockfile と本体側の lockfile の **両方** を更新
- **SDK の major / breaking minor release** が public announcement で確認された場合、PR description で明示
- **月次 review PR** は label `dependency review` を付与

## 判断フロー

1. このパッケージは AI 推論 SDK か? → Yes → 常に最新追従、lower bound のみ pin
2. UI / DB / test framework か? → Yes → 計画的 bump、major 変更時に手動移行
3. それ以外 → 通常の依存更新運用

## 関連

> **プロジェクト固有:** 本ルールを支える ADR / Issue へのリンクを追記する。
