# Dependency Management Rules

LoRAIro / image-annotator-lib の依存パッケージ管理ルール。AI 推論 SDK は最新追従、それ以外は計画的 bump。

## 核心ルール

**AI 推論 SDK は常に最新の安定版を使う。** 古い SDK は新モデル response 形式を parse しきれず inference が fail する (LoRAIro #275 の `claude-haiku-4-5` `KeyError 'type'` が代表例)。

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
# ✅ 正しい
"pydantic-ai>=1.97",
"anthropic>=0.102",
"transformers>=4.50",

# ❌ 禁止: upper bound で upgrade 抑止
"pydantic-ai>=1.97,<2.0",
"anthropic==0.102.0",
```

## lockfile (`uv.lock`) 更新タイミング

ADR 0025 (lockfile は commit) と整合させつつ、SDK は積極更新:

1. **新モデル対応 / WebAPI バグ修正 PR で**:
   ```bash
   uv lock --upgrade-package pydantic-ai --upgrade-package anthropic
   ```
2. **submodule pin (`local_packages/*`) 更新時に** 該当 SDK を bump
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
| 汎用 library | `Pillow`, `loguru`, `polars` 等 | ADR 0025 通常運用 |

## bump 時の regression check

SDK bump 前後で **CI-equivalent filter** を必ず実行 (`.claude/rules/testing.md` 参照):

```bash
# LoRAIro 本体
.venv/bin/pytest -m "not gui_show and not real_api and not slow" --timeout=60

# image-annotator-lib
.venv/bin/pytest local_packages/image-annotator-lib/tests/ \
  -m "not real_api and not heavy and not system_integration" --timeout=60
```

実 API での挙動確認は ADR 0026 (On-Demand Runtime Validation) に従い手動 smoke で行う。

## PR 運用ルール

- **依存更新を含む PR** は `pyproject.toml` と `uv.lock` を **必ず同時 commit**
- **submodule pin 更新 PR** は iam-lib 側 `uv.lock` と LoRAIro 側 `uv.lock` の **両方** を更新
- **SDK の major / breaking minor release** が public announcement で確認された場合、PR description で明示
- **月次 review PR** は label `dependency review` を付与

## 判断フロー

1. このパッケージは AI 推論 SDK か? → Yes → 常に最新追従、lower bound のみ pin
2. UI / DB / test framework か? → Yes → 計画的 bump、major 変更時に手動移行
3. それ以外 → ADR 0025 通常運用

## 関連

- **ADR 0023** (PydanticAI / LiteLLM WebAPI Inference Boundary) — 本ルールで支える SDK 群の SSoT
- **ADR 0025** (uv.lock Version Control Policy) — lockfile は commit、bump は積極的に
- **ADR 0026** (On-Demand Runtime Validation Strategy) — SDK bump 時の実 API 確認方針
- **.claude/rules/testing.md** — CI-equivalent filter の詳細
- **発端 Issue**: NEXTAltair/LoRAIro#275 (claude-haiku-4-5 KeyError)
