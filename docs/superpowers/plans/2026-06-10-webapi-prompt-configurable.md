# WebAPI アノテーションプロンプト設定化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `additional_prompt` 引数を iam-lib のコールチェーン全体に追加し、LoRAIro の `prompts.additional` 設定が WebAPI アノテーションのシステムプロンプトに反映されるようにする。BASE_PROMPT も最新要件（ポーズ・光源・構図・スタイル重視）に書き直す。

**Architecture:** iam-lib の `api.annotate()` に `additional_prompt: str | None = None` を追加し、`WebApiAnnotator.__init__` に保存、`ProviderManager._build_system_prompt()` で `BASE_PROMPT + "\n\n" + additional_prompt` として結合する。LoRAIro の `AnnotatorLibraryAdapter.annotate()` で config から値を読んで渡す。

**Tech Stack:** Python 3.13, PydanticAI, image-annotator-lib (editable submodule), pytest, uv

---

## 重要な前提

- **iam-lib の変更は in-place** で行う: `/workspaces/LoRAIro/local_packages/image-annotator-lib/` を直接編集する。worktree では editable install が解決できないため。
- **LoRAIro の変更は worktree** で行う: `.agents/worktree/feat-webapi-prompt/` 内で実施。
- 全テストコマンドは `/workspaces/LoRAIro` から実行（UV_PROJECT_ENVIRONMENT 設定済み）。

---

## ファイル変更マップ

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/webapi_shared.py` | Modify | BASE_PROMPT を全面書き直し |
| `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/provider_manager.py` | Modify | `_build_system_prompt()` / `run_inference_with_model_async()` / `run_inference_with_model()` に `additional_prompt` 追加 |
| `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/annotator.py` | Modify | `__init__()` / `_run_inference()` に `additional_prompt` 追加 |
| `local_packages/image-annotator-lib/src/image_annotator_lib/core/annotation_runner.py` | Modify | `run_annotation()` / `_execute_model_annotation()` / `get_annotator_instance()` / `_create_annotator_instance()` に `additional_prompt` 追加 |
| `local_packages/image-annotator-lib/src/image_annotator_lib/api.py` | Modify | `annotate()` に `additional_prompt` 追加 |
| `local_packages/image-annotator-lib/tests/unit/webapi/test_build_system_prompt.py` | Create | `_build_system_prompt()` の単体テスト |
| `src/lorairo/annotations/annotator_adapter.py` | Modify | `annotate()` で config から `additional_prompt` を読んで渡す |
| `tests/unit/annotations/test_annotator_adapter_prompt.py` | Create | adapter が `additional_prompt` を正しく渡すテスト |

---

## Task 1: Worktreeセットアップ

**Files:**
- Create worktree: `.agents/worktree/feat-webapi-prompt/`

- [ ] **Step 1: worktree作成**

```bash
git fetch origin
git worktree add .agents/worktree/feat-webapi-prompt -b feat/webapi-configurable-prompt origin/main
```

Expected: `.agents/worktree/feat-webapi-prompt/` が作成され、`feat/webapi-configurable-prompt` ブランチに切り替わっている。

- [ ] **Step 2: 現在のテストが通ることを確認（iam-lib）**

```bash
cd /workspaces/LoRAIro
make test-iam-lib
```

Expected: 全テストPASS（RED状態でなく、実装前のベースラインを確認）

---

## Task 2: BASE_PROMPT の全面書き直し

**Files:**
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/webapi_shared.py`

> NOTE: BASE_PROMPTはコンテンツ変更のみでAPIシグネチャ変更なし。TDD不要だが既存テストが通ることを確認する。

- [ ] **Step 1: webapi_shared.py を更新**

`local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/webapi_shared.py` の `BASE_PROMPT` を以下に置き換える（ファイル全体を上書き）:

```python
BASE_PROMPT = """You are an expert image annotation assistant for AI training datasets.

Analyze the image and provide the following annotations.

## Priority: What Tagger Models Miss
Focus especially on these elements that automated taggers cannot reliably detect:

**Pose & Orientation** (high priority):
- Facing direction: facing left / facing right / facing viewer / from behind / three-quarter view
- Body posture: standing / sitting / crouching / lying / leaning / jumping, etc.
- Hand and arm positions with left/right distinction
- Gaze direction: looking at viewer / looking left / looking away / looking down, etc.
- Dynamic motion or stillness

**Lighting & Atmosphere** (high priority):
- Light source direction: top-down / side light (left/right) / backlit / rim light / fill light
- Lighting type: natural daylight / golden hour / indoor artificial / dramatic / soft / harsh
- Shadow placement and quality
- Overall mood: bright and airy / dark and moody / warm / cool / neutral

**Composition & Framing** (high priority):
- Shot type: close-up / portrait / upper body / waist up / full body / wide shot
- Subject placement: centered / rule of thirds / off-center
- Depth: flat / shallow depth of field / deep focus
- Perspective: eye level / low angle / high angle / bird's eye / worm's eye
- Use of negative space

**Style & Rendering** (high priority):
- Medium: photograph / digital illustration / traditional painting / 3D render / sketch / watercolor
- Line quality (if applicable): clean linework / loose sketch / no outlines
- Color palette: monochrome / limited palette / vibrant / desaturated / complementary colors
- Rendering detail level: highly detailed / stylized / minimalist

## Secondary Elements
Briefly note these (taggers handle them well, so keep concise):
- Subject: number of people/objects, key identifying features
- Setting/background: location type, environmental elements
- Expression (if human): emotional state

## Scoring (1.00-10.00)
Rate the overall quality across three dimensions:

Technical & Composition (0-4 pts):
- Image clarity, sharpness, or rendering quality
- Compositional strength: framing, balance, visual flow

Artistic Merit (0-4 pts):
- Lighting and atmosphere execution
- Style consistency and expressiveness
- Detail level appropriate to the work

Overall Impact (0-2 pts):
- Immediate visual appeal and cohesion

Score reference:
- 9.00-10.00: Exceptional, masterwork quality
- 7.50-8.99: High quality, professional level
- 6.00-7.49: Good quality, minor imperfections
- 4.50-5.99: Average, notable areas for improvement
- Below 4.50: Significant quality issues

## Output Format
Respond ONLY in this exact format -- no additional text:

tags: [comma-separated descriptors, 20-50 items, always specify left/right for directional elements, no underscores]
caption: [1-2 objective sentences emphasizing pose, lighting, and composition]
score: [X.XX]
"""

SYSTEM_PROMPT = """
                    You are an AI that MUST output ONLY valid JSON, with no additional text, markdown formatting, or explanations.

                    Output Structure:
                    {
                        "tags": ["tag1", "tag2", "tag3", ...],  // List of tags describing image features (max 150 tokens)
                        "captions": ["caption1", "caption2", ...],  // List of short descriptions explaining the image content (max 75 tokens)
                        "score": 0.85  // Quality evaluation of the image (decimal value between 0.0 and 1.0)
                    }

                    Rules:
                    1. ONLY output the JSON object - no other text or formatting
                    2. DO NOT use markdown code blocks (```) or any other formatting
                    3. DO NOT include any explanations or comments
                    4. Always return complete, valid, parseable JSON
                    5. Include all required fields: tags, captions, and score
                    6. Never truncate or leave incomplete JSON
                    7. DO NOT add any leading or trailing whitespace or newlines
                    8. DO NOT start with any introductory text like "Here is the analysis:"

                    Example of EXACT expected output format:
                    {"tags":["1girl","red_hair"],"captions":["A girl with long red hair"],"score":0.95}
                """

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {"type": "array", "items": {"type": "string"}},
        "captions": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "number"},
    },
    "required": ["tags", "captions", "score"],
}
```

- [ ] **Step 2: iam-lib テストがまだ通ることを確認**

```bash
cd /workspaces/LoRAIro
make test-iam-lib
```

Expected: 全テストPASS

- [ ] **Step 3: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add src/image_annotator_lib/model_class/annotator_webapi/webapi_shared.py
git commit -m "refactor(prompt): BASE_PROMPT を pose/lighting/composition/style 重視に全面改訂"
```

---

## Task 3: `_build_system_prompt()` に `additional_prompt` 引数を追加

**Files:**
- Create: `local_packages/image-annotator-lib/tests/unit/webapi/test_build_system_prompt.py`
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/provider_manager.py`

- [ ] **Step 1: 失敗するテストを書く**

`local_packages/image-annotator-lib/tests/unit/webapi/test_build_system_prompt.py` を新規作成:

```python
"""_build_system_prompt() の単体テスト。"""

import pytest

from image_annotator_lib.core.types import TaskCapability
from image_annotator_lib.model_class.annotator_webapi.webapi_shared import BASE_PROMPT
from image_annotator_lib.webapi.provider_manager import _build_system_prompt


@pytest.mark.unit
def test_build_system_prompt_no_additional_returns_base():
    result = _build_system_prompt(None, None)
    assert result == BASE_PROMPT


@pytest.mark.unit
def test_build_system_prompt_empty_string_returns_base():
    """空文字列は追記しない。"""
    result = _build_system_prompt(None, "")
    assert result == BASE_PROMPT


@pytest.mark.unit
def test_build_system_prompt_whitespace_only_returns_base():
    """空白のみは追記しない。"""
    result = _build_system_prompt(None, "   ")
    assert result == BASE_PROMPT


@pytest.mark.unit
def test_build_system_prompt_with_additional_appends():
    """additional_prompt は BASE_PROMPT の末尾に二重改行で追記される。"""
    result = _build_system_prompt(None, "Focus on red objects.")
    assert result == BASE_PROMPT + "\n\nFocus on red objects."


@pytest.mark.unit
def test_build_system_prompt_strips_additional():
    """additional_prompt の前後の空白は除去される。"""
    result = _build_system_prompt(None, "  extra instruction  ")
    assert result == BASE_PROMPT + "\n\nextra instruction"


@pytest.mark.unit
def test_build_system_prompt_ratings_capability_no_additional():
    """RATINGS capability があれば rating 指示が追記される。"""
    result = _build_system_prompt({TaskCapability.RATINGS}, None)
    assert "Rating task:" in result
    assert result.startswith(BASE_PROMPT)


@pytest.mark.unit
def test_build_system_prompt_ratings_and_additional():
    """RATINGS + additional_prompt の両方が追記される。"""
    result = _build_system_prompt({TaskCapability.RATINGS}, "extra note")
    assert "Rating task:" in result
    assert result.endswith("\n\nextra note")
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/tests/unit/webapi/test_build_system_prompt.py -v
```

Expected: 引数エラーで FAIL（現在 `_build_system_prompt` は `additional_prompt` 引数を持たない）

- [ ] **Step 3: `_build_system_prompt()` を更新**

`local_packages/image-annotator-lib/src/image_annotator_lib/webapi/provider_manager.py` の `_build_system_prompt()` 関数を以下に置き換える:

```python
def _build_system_prompt(
    capabilities: set[TaskCapability] | frozenset[TaskCapability] | None,
    additional_prompt: str | None = None,
) -> str:
    """Build the WebAPI system prompt for the requested task capabilities."""
    base = BASE_PROMPT

    if capabilities is not None and TaskCapability.RATINGS in capabilities:
        base = (
            base
            + "\n\n"
            + "Rating task: return any requested content rating as a model-native label in the "
            + "`rating` or `ratings` output field. Do not include rating labels in `tags` or "
            + "`score_labels`, and do not map them to LoRAIro canonical ratings."
        )

    if additional_prompt and additional_prompt.strip():
        base = base + "\n\n" + additional_prompt.strip()

    return base
```

- [ ] **Step 4: テストが通ることを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/tests/unit/webapi/test_build_system_prompt.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add tests/unit/webapi/test_build_system_prompt.py \
        src/image_annotator_lib/webapi/provider_manager.py
git commit -m "feat(prompt): _build_system_prompt() に additional_prompt 引数を追加"
```

---

## Task 4: ProviderManager の `run_inference_with_model*` に `additional_prompt` を追加

**Files:**
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/provider_manager.py`

> NOTE: `run_inference_with_model_async()` と `run_inference_with_model()` に引数を追加し、`_build_system_prompt()` 呼び出しに渡す。

- [ ] **Step 1: `run_inference_with_model_async()` の引数リストに `additional_prompt` を追加**

`provider_manager.py` の `run_inference_with_model_async()` のシグネチャを変更。`_test_agent` の直前に追加する:

変更前:
```python
    @classmethod
    async def run_inference_with_model_async(
        cls,
        *,
        model_name: str,
        images_list: list[Image.Image],
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        config: dict[str, Any] | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
        _test_agent: Agent | None = None,
    ) -> dict[str, AnnotationResult]:
```

変更後:
```python
    @classmethod
    async def run_inference_with_model_async(
        cls,
        *,
        model_name: str,
        images_list: list[Image.Image],
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        config: dict[str, Any] | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
        additional_prompt: str | None = None,
        _test_agent: Agent | None = None,
    ) -> dict[str, AnnotationResult]:
```

docstring の Args セクションに追記:
```
            additional_prompt: BASE_PROMPT の末尾に追記するユーザー定義プロンプト。
                None または空文字列の場合は追記しない。
```

- [ ] **Step 2: `_build_system_prompt()` の呼び出しに `additional_prompt` を渡す**

同ファイル内の `Agent(...)` 生成箇所を変更:

変更前:
```python
                agent = Agent(
                    model=model,
                    output_type=build_annotation_output_normalizer(capabilities),
                    system_prompt=_build_system_prompt(capabilities),
                    retries={"output": _OUTPUT_RETRIES},
                )
```

変更後:
```python
                agent = Agent(
                    model=model,
                    output_type=build_annotation_output_normalizer(capabilities),
                    system_prompt=_build_system_prompt(capabilities, additional_prompt),
                    retries={"output": _OUTPUT_RETRIES},
                )
```

- [ ] **Step 3: `run_inference_with_model()` の sync wrapper にも `additional_prompt` を追加**

変更前:
```python
    @classmethod
    def run_inference_with_model(
        cls,
        *,
        model_name: str,
        images_list: list[Image.Image],
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        config: dict[str, Any] | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
        _test_agent: Agent | None = None,
    ) -> dict[str, AnnotationResult]:
```

変更後:
```python
    @classmethod
    def run_inference_with_model(
        cls,
        *,
        model_name: str,
        images_list: list[Image.Image],
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        config: dict[str, Any] | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
        additional_prompt: str | None = None,
        _test_agent: Agent | None = None,
    ) -> dict[str, AnnotationResult]:
```

`asyncio.run(cls.run_inference_with_model_async(...))` の呼び出しにも `additional_prompt=additional_prompt` を追加:

変更前:
```python
        return asyncio.run(
            cls.run_inference_with_model_async(
                model_name=model_name,
                images_list=images_list,
                litellm_model_id=litellm_model_id,
                api_keys=api_keys,
                config=config,
                capabilities=capabilities,
                mode=mode,
                max_concurrency=max_concurrency,
                _test_agent=_test_agent,
            )
        )
```

変更後:
```python
        return asyncio.run(
            cls.run_inference_with_model_async(
                model_name=model_name,
                images_list=images_list,
                litellm_model_id=litellm_model_id,
                api_keys=api_keys,
                config=config,
                capabilities=capabilities,
                mode=mode,
                max_concurrency=max_concurrency,
                additional_prompt=additional_prompt,
                _test_agent=_test_agent,
            )
        )
```

- [ ] **Step 4: iam-lib テストが通ることを確認**

```bash
cd /workspaces/LoRAIro
make test-iam-lib
```

Expected: 全テスト PASS（後方互換: `additional_prompt=None` がデフォルト）

- [ ] **Step 5: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add src/image_annotator_lib/webapi/provider_manager.py
git commit -m "feat(prompt): ProviderManager.run_inference_with_model* に additional_prompt 引数を追加"
```

---

## Task 5: `WebApiAnnotator` に `additional_prompt` を追加

**Files:**
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/webapi/annotator.py`

- [ ] **Step 1: `WebApiAnnotator.__init__()` に `additional_prompt` を追加**

`webapi/annotator.py` の `__init__()` シグネチャを変更:

変更前:
```python
    def __init__(
        self,
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        model_name: str | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | list[str] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
    ) -> None:
```

変更後:
```python
    def __init__(
        self,
        litellm_model_id: str,
        api_keys: dict[str, str] | None = None,
        model_name: str | None = None,
        capabilities: set[TaskCapability] | frozenset[TaskCapability] | list[str] | None = None,
        mode: str = "chat",
        max_concurrency: int | None = None,
        additional_prompt: str | None = None,
    ) -> None:
```

docstring の Args に追記:
```
            additional_prompt: BASE_PROMPT の末尾に追記するユーザー定義プロンプト。
                None または空文字列の場合は追記しない。
```

`__init__` 本体の属性設定部分（`self.max_concurrency = max_concurrency` の直後）に追加:
```python
        self.additional_prompt = additional_prompt
```

- [ ] **Step 2: `_run_inference()` に `additional_prompt` を渡す**

`_run_inference()` 内の `ProviderManager.run_inference_with_model()` 呼び出しを変更:

変更前:
```python
        results_dict = ProviderManager.run_inference_with_model(
            model_name=self.model_name,
            images_list=processed,
            litellm_model_id=self.litellm_model_id,
            api_keys=self.api_keys,
            capabilities=self.capabilities,
            mode=self.mode,
            max_concurrency=self.max_concurrency,
        )
```

変更後:
```python
        results_dict = ProviderManager.run_inference_with_model(
            model_name=self.model_name,
            images_list=processed,
            litellm_model_id=self.litellm_model_id,
            api_keys=self.api_keys,
            capabilities=self.capabilities,
            mode=self.mode,
            max_concurrency=self.max_concurrency,
            additional_prompt=self.additional_prompt,
        )
```

- [ ] **Step 3: iam-lib テストが通ることを確認**

```bash
cd /workspaces/LoRAIro
make test-iam-lib
```

Expected: 全テスト PASS

- [ ] **Step 4: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add src/image_annotator_lib/webapi/annotator.py
git commit -m "feat(prompt): WebApiAnnotator に additional_prompt 属性を追加"
```

---

## Task 6: `annotation_runner.py` のコールチェーンに `additional_prompt` を追加

**Files:**
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/core/annotation_runner.py`

- [ ] **Step 1: `_create_annotator_instance()` に `additional_prompt` を追加**

シグネチャを変更:

変更前:
```python
def _create_annotator_instance(model_name: str, api_keys: dict[str, str] | None = None) -> BaseAnnotator:
```

変更後:
```python
def _create_annotator_instance(
    model_name: str,
    api_keys: dict[str, str] | None = None,
    additional_prompt: str | None = None,
) -> BaseAnnotator:
```

WebApiAnnotator の構築箇所に `additional_prompt=additional_prompt` を追加:

変更前:
```python
            return WebApiAnnotator(
                litellm_model_id=litellm_model_id,
                api_keys=api_keys,
                model_name=actual_model_name,
                capabilities=get_model_capabilities(actual_model_name),
                mode=mode,
            )
```

変更後:
```python
            return WebApiAnnotator(
                litellm_model_id=litellm_model_id,
                api_keys=api_keys,
                model_name=actual_model_name,
                capabilities=get_model_capabilities(actual_model_name),
                mode=mode,
                additional_prompt=additional_prompt,
            )
```

- [ ] **Step 2: `get_annotator_instance()` に `additional_prompt` を追加**

変更前:
```python
def get_annotator_instance(model_name: str, api_keys: dict[str, str] | None = None) -> Any:
```

変更後:
```python
def get_annotator_instance(
    model_name: str,
    api_keys: dict[str, str] | None = None,
    additional_prompt: str | None = None,
) -> Any:
```

`api_keys` が指定されている場合の分岐内:

変更前:
```python
    if api_keys:
        logger.debug(f"APIキー指定のためモデル '{model_name}' の新しいインスタンスを作成")
        return _create_annotator_instance(model_name, api_keys=api_keys)
```

変更後:
```python
    if api_keys:
        logger.debug(f"APIキー指定のためモデル '{model_name}' の新しいインスタンスを作成")
        return _create_annotator_instance(model_name, api_keys=api_keys, additional_prompt=additional_prompt)
```

キャッシュなしの通常生成パスも更新（`api_keys` が空の場合のフォールスルー）:

変更前:
```python
    instance = _create_annotator_instance(model_name)
```

変更後:
```python
    instance = _create_annotator_instance(model_name, additional_prompt=additional_prompt)
```

- [ ] **Step 3: `_execute_model_annotation()` に `additional_prompt` を追加**

変更前:
```python
def _execute_model_annotation(
    model_name: str,
    images_list: list[Image.Image],
    phash_list: list[str],
    phash_map: dict[int, str],
    results_by_phash: PHashAnnotationResults,
    api_keys: dict[str, str] | None,
) -> None:
```

変更後:
```python
def _execute_model_annotation(
    model_name: str,
    images_list: list[Image.Image],
    phash_list: list[str],
    phash_map: dict[int, str],
    results_by_phash: PHashAnnotationResults,
    api_keys: dict[str, str] | None,
    additional_prompt: str | None = None,
) -> None:
```

内部の `get_annotator_instance` 呼び出しに追加:

変更前:
```python
        annotator = get_annotator_instance(model_name, api_keys=api_keys)
```

変更後:
```python
        annotator = get_annotator_instance(model_name, api_keys=api_keys, additional_prompt=additional_prompt)
```

- [ ] **Step 4: `run_annotation()` に `additional_prompt` を追加**

変更前:
```python
def run_annotation(
    images: list[Image.Image],
    model_names: list[str],
    phash_list: list[str] | None = None,
    api_keys: dict[str, str] | None = None,
) -> PHashAnnotationResults:
```

変更後:
```python
def run_annotation(
    images: list[Image.Image],
    model_names: list[str],
    phash_list: list[str] | None = None,
    api_keys: dict[str, str] | None = None,
    additional_prompt: str | None = None,
) -> PHashAnnotationResults:
```

docstring の Args に追記:
```
        additional_prompt: WebAPI モデルの BASE_PROMPT 末尾に追記するプロンプト。
            None または空文字列の場合は追記しない。ローカル ML モデルには無視される。
```

ループ内の `_execute_model_annotation` 呼び出しに `additional_prompt=additional_prompt` を追加:

変更前:
```python
        _execute_model_annotation(
            model_name, images, phash_list_final, phash_map, results_by_phash, api_keys
        )
```

変更後:
```python
        _execute_model_annotation(
            model_name, images, phash_list_final, phash_map, results_by_phash, api_keys,
            additional_prompt=additional_prompt,
        )
```

- [ ] **Step 5: iam-lib テストが通ることを確認**

```bash
cd /workspaces/LoRAIro
make test-iam-lib
```

Expected: 全テスト PASS

- [ ] **Step 6: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add src/image_annotator_lib/core/annotation_runner.py
git commit -m "feat(prompt): annotation_runner.py のコールチェーンに additional_prompt を追加"
```

---

## Task 7: `api.py` の公開 API に `additional_prompt` を追加

**Files:**
- Modify: `local_packages/image-annotator-lib/src/image_annotator_lib/api.py`

- [ ] **Step 1: `annotate()` に `additional_prompt` を追加**

変更前:
```python
def annotate(
    images_list: list[Image.Image],
    model_name_list: list[str],
    phash_list: list[str] | None = None,
    api_keys: dict[str, str] | None = None,
) -> PHashAnnotationResults:
    """複数の画像を指定された複数のモデルで評価(アノテーション)する。

    Args:
        images_list: 評価対象の PIL Image オブジェクトのリスト。
        model_name_list: 使用するモデル名のリスト。
        phash_list: 各画像に対応するpHashのリスト。
        api_keys: WebAPIモデル用のAPIキー辞書 (オプション)。

    Returns:
        結果を格納した PHashAnnotationResults 辞書。
    """
    return run_annotation(
        images=images_list,
        model_names=model_name_list,
        phash_list=phash_list,
        api_keys=api_keys,
    )
```

変更後:
```python
def annotate(
    images_list: list[Image.Image],
    model_name_list: list[str],
    phash_list: list[str] | None = None,
    api_keys: dict[str, str] | None = None,
    additional_prompt: str | None = None,
) -> PHashAnnotationResults:
    """複数の画像を指定された複数のモデルで評価(アノテーション)する。

    Args:
        images_list: 評価対象の PIL Image オブジェクトのリスト。
        model_name_list: 使用するモデル名のリスト。
        phash_list: 各画像に対応するpHashのリスト。
        api_keys: WebAPIモデル用のAPIキー辞書 (オプション)。
        additional_prompt: WebAPI モデルの BASE_PROMPT 末尾に追記するプロンプト。
            None または空文字列の場合は追記しない。ローカル ML モデルには無視される。

    Returns:
        結果を格納した PHashAnnotationResults 辞書。
    """
    return run_annotation(
        images=images_list,
        model_names=model_name_list,
        phash_list=phash_list,
        api_keys=api_keys,
        additional_prompt=additional_prompt,
    )
```

- [ ] **Step 2: iam-lib CI-equivalent テストを実行**

```bash
cd /workspaces/LoRAIro
uv run pytest local_packages/image-annotator-lib/ \
    -m "not downloads_and_runs_model and not calls_real_webapi" \
    --timeout=60 -v
```

Expected: 全テスト PASS

- [ ] **Step 3: コミット（iam-lib）**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git add src/image_annotator_lib/api.py
git commit -m "feat(prompt): annotate() 公開 API に additional_prompt 引数を追加"
```

---

## Task 8: LoRAIro の `AnnotatorLibraryAdapter` を更新

**Files:**
- Create: `tests/unit/annotations/test_annotator_adapter_prompt.py` (worktree内)
- Modify: `src/lorairo/annotations/annotator_adapter.py` (worktree内)

> NOTE: 以降のファイル操作は `.agents/worktree/feat-webapi-prompt/` 内で行う。

- [ ] **Step 1: 失敗するテストを書く**

`.agents/worktree/feat-webapi-prompt/tests/unit/annotations/test_annotator_adapter_prompt.py` を新規作成:

```python
"""AnnotatorLibraryAdapter が prompts.additional を annotate() に渡すことを検証する。"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter


@pytest.fixture
def dummy_image() -> Image.Image:
    return Image.new("RGB", (64, 64))


@pytest.fixture
def config_service_with_prompt() -> MagicMock:
    """prompts.additional = "test instruction" を返す ConfigurationService モック。"""
    svc = MagicMock()

    def get_setting(section: str, key: str, default: str = "") -> str:
        if section == "prompts" and key == "additional":
            return "test instruction"
        return ""

    svc.get_setting.side_effect = get_setting
    return svc


@pytest.fixture
def config_service_empty_prompt() -> MagicMock:
    """prompts.additional = "" を返す ConfigurationService モック。"""
    svc = MagicMock()
    svc.get_setting.return_value = ""
    return svc


@pytest.mark.unit
def test_annotate_passes_additional_prompt_to_lib(
    dummy_image: Image.Image,
    config_service_with_prompt: MagicMock,
) -> None:
    """prompts.additional が設定されている場合、annotate() に additional_prompt として渡される。"""
    adapter = AnnotatorLibraryAdapter(config_service_with_prompt)

    # annotator_adapter.py 内でローカルインポート `from image_annotator_lib import annotate`
    # されるため、image_annotator_lib モジュール側をパッチする
    with patch("image_annotator_lib.annotate") as mock_annotate:
        mock_annotate.return_value = {}
        adapter.annotate([dummy_image], ["openai/gpt-4o"])

    mock_annotate.assert_called_once()
    call_kwargs = mock_annotate.call_args.kwargs
    assert call_kwargs["additional_prompt"] == "test instruction"


@pytest.mark.unit
def test_annotate_passes_none_when_prompt_empty(
    dummy_image: Image.Image,
    config_service_empty_prompt: MagicMock,
) -> None:
    """prompts.additional が空文字列の場合、additional_prompt=None として渡される。"""
    adapter = AnnotatorLibraryAdapter(config_service_empty_prompt)

    with patch("image_annotator_lib.annotate") as mock_annotate:
        mock_annotate.return_value = {}
        adapter.annotate([dummy_image], ["openai/gpt-4o"])

    mock_annotate.assert_called_once()
    call_kwargs = mock_annotate.call_args.kwargs
    assert call_kwargs["additional_prompt"] is None
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest .agents/worktree/feat-webapi-prompt/tests/unit/annotations/test_annotator_adapter_prompt.py -v
```

Expected: FAIL（`annotate()` が `additional_prompt` 引数を受け付けていないか、まだ渡していない）

- [ ] **Step 3: `AnnotatorLibraryAdapter.annotate()` を更新**

`.agents/worktree/feat-webapi-prompt/src/lorairo/annotations/annotator_adapter.py` の `annotate()` メソッド内を変更。

`api_keys = self._prepare_api_keys()` の直後（`results = annotate(...)` の前）に追加:

```python
            additional_prompt = self.config_service.get_setting("prompts", "additional", "") or None
```

`results = annotate(...)` の呼び出しに引数を追加:

変更前:
```python
            results = annotate(
                images_list=images,
                model_name_list=litellm_model_ids,
                phash_list=phash_list,
                api_keys=api_keys,  # 明示的に引数として渡す
            )
```

変更後:
```python
            results = annotate(
                images_list=images,
                model_name_list=litellm_model_ids,
                phash_list=phash_list,
                api_keys=api_keys,
                additional_prompt=additional_prompt,
            )
```

- [ ] **Step 4: テストが通ることを確認**

```bash
cd /workspaces/LoRAIro
uv run pytest .agents/worktree/feat-webapi-prompt/tests/unit/annotations/test_annotator_adapter_prompt.py -v
```

Expected: 全テスト PASS

- [ ] **Step 5: LoRAIro CI-equivalent フィルターを実行**

```bash
cd /workspaces/LoRAIro/.agents/worktree/feat-webapi-prompt
uv run pytest tests/ \
    -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" \
    --timeout=60
```

Expected: 全テスト PASS

- [ ] **Step 6: worktree 内でコミット**

```bash
cd .agents/worktree/feat-webapi-prompt
git add tests/unit/annotations/test_annotator_adapter_prompt.py \
        src/lorairo/annotations/annotator_adapter.py
git commit -m "feat(prompt): AnnotatorLibraryAdapter が prompts.additional を iam-lib に渡すよう接続"
```

---

## Task 9: サブモジュール pin 更新と PR 起票

**Files:**
- Modify: `.gitmodules` ではなく submodule HEAD の更新（worktree内）

- [ ] **Step 1: iam-lib の submodule commit hash を確認**

```bash
cd /workspaces/LoRAIro/local_packages/image-annotator-lib
git log --oneline -5
```

最新コミットが Task 7 のコミット (`feat(prompt): annotate() ...`) であることを確認。

- [ ] **Step 2: LoRAIro worktree でサブモジュール pin を更新**

```bash
cd /workspaces/LoRAIro/.agents/worktree/feat-webapi-prompt
git submodule update --init local_packages/image-annotator-lib
cd local_packages/image-annotator-lib
git checkout <iam-lib の最新コミット hash>  # Step 1 で確認した hash
cd ../..
git add local_packages/image-annotator-lib
git commit -m "chore(deps): submodule pin 更新 — iam-lib (additional_prompt 対応)"
```

- [ ] **Step 3: LoRAIro CI-equivalent をフル実行**

```bash
cd /workspaces/LoRAIro
uv run pytest .agents/worktree/feat-webapi-prompt/tests/ \
    -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" \
    --timeout=60 -v
```

Expected: 全テスト PASS

iam-lib テストもフル実行:
```bash
uv run pytest local_packages/image-annotator-lib/ \
    -m "not downloads_and_runs_model and not calls_real_webapi" \
    --timeout=60
```

Expected: 全テスト PASS

- [ ] **Step 4: worktree から push**

```bash
cd .agents/worktree/feat-webapi-prompt
git push -u origin feat/webapi-configurable-prompt
```

- [ ] **Step 5: PR 起票**

```bash
gh pr create \
    --title "feat(prompt): WebAPI アノテーションプロンプトを設定可能に + BASE_PROMPT 改訂" \
    --body "$(cat <<'EOF'
## Summary
- BASE_PROMPT をポーズ・光源・構図・スタイル重視の内容に全面改訂（tagger モデルの弱点を補う設計）
- `additional_prompt: str | None = None` を iam-lib の `annotate()` から `_build_system_prompt()` まで全コールチェーンに追加
- LoRAIro の `prompts.additional` 設定値（既存 GUI で編集可能）を実際のアノテーション推論に反映

## Changes
- `iam-lib`: `webapi_shared.py`, `provider_manager.py`, `annotator.py`, `annotation_runner.py`, `api.py`
- `LoRAIro`: `annotator_adapter.py`

## Test plan
- [ ] `make test-iam-lib` PASS
- [ ] LoRAIro CI-equivalent filter PASS
- [ ] 設定ウィンドウで `prompts.additional` を設定 → WebAPI アノテーション実行 → ログで additional_prompt が反映されることを手動確認

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: worktree を削除（merge後）**

```bash
cd /workspaces/LoRAIro
git worktree remove .agents/worktree/feat-webapi-prompt
```

---

## 後方互換性チェックリスト

全ての新引数に `additional_prompt: str | None = None` のデフォルト値が設定されており、既存の呼び出し元（Batch API、既存テスト）は引数なしでそのまま動作する。

| 変更箇所 | デフォルト値 | 後方互換 |
|---|---|---|
| `api.annotate()` | `None` | ✅ |
| `run_annotation()` | `None` | ✅ |
| `_execute_model_annotation()` | `None` | ✅ |
| `get_annotator_instance()` | `None` | ✅ |
| `_create_annotator_instance()` | `None` | ✅ |
| `WebApiAnnotator.__init__()` | `None` | ✅ |
| `ProviderManager.run_inference_with_model_async()` | `None` | ✅ |
| `ProviderManager.run_inference_with_model()` | `None` | ✅ |
| `_build_system_prompt()` | `None` | ✅ |
