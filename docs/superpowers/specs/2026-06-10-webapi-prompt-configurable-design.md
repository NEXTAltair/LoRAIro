# WebAPI アノテーションプロンプト設定化 — 設計仕様

**日付:** 2026-06-10  
**対象リポジトリ:** LoRAIro および image-annotator-lib(サブモジュール)  
**ステータス:** Draft

---

## 背景と目的

WebAPI アノテーションのシステムプロンプト(`BASE_PROMPT`)は現在 `iam-lib` 内にハードコードされており、変更できない。また、`config/lorairo.toml` の `[prompts] additional` フィールドと GUI 入力欄はすでに実装されているが、`iam-lib` に渡されておらず機能していない。

**目的:**
1. `BASE_PROMPT` を最新の要件(ポーズ、光源、構図、スタイルの重視)に合わせて書き直す。
2. ユーザーが追加できるプロンプト(`prompts.additional`)を実際のアノテーション処理へ反映させる。

---

## 設計概要

### アーキテクチャ

```
config/lorairo.toml [prompts.additional]
    ↓ (既存GUI — 設定ウィンドウで編集・保存)
AnnotatorLibraryAdapter.annotate(additional_prompt=)   ← LoRAIro: 新規接続のみ
    ↓
image_annotator_lib.annotate(additional_prompt=)       ← iam-lib: 引数追加
    ↓
annotation_runner.run_annotation(additional_prompt=)   ← iam-lib: スレッド
    ↓
WebApiAnnotator.__init__(additional_prompt=)           ← iam-lib: 保存
WebApiAnnotator._run_inference(additional_prompt=)     ← iam-lib: 転送
    ↓
ProviderManager.run_inference_with_model_async(additional_prompt=)
    ↓
_build_system_prompt(capabilities, additional_prompt)
    ↓ BASE_PROMPT + "\n\n" + additional_prompt (additional が空でない場合のみ)
Agent(system_prompt=...)
```

### 基本方針

- 引数を `additional_prompt: str | None = None` とし、デフォルトを `None` にして後方互換を維持する。
- `additional_prompt` が空文字列(`""`)の場合は `None` と同等に扱い、追記しない。
- `iam-lib` 側での結合処理は `_build_system_prompt()` の 1 箇所のみで行う。
- GUI と設定保存はすでに動作しているため変更しない。

---

## 変更ファイル一覧

### `iam-lib` 側(5 ファイル)

| ファイル | 変更内容 |
|---|---|
| `model_class/annotator_webapi/webapi_shared.py` | `BASE_PROMPT` を全面的に書き直す |
| `api.py` | `annotate()` に `additional_prompt: str \| None = None` を追加する |
| `core/annotation_runner.py` | `run_annotation()`、`_execute_model_annotation()`、`get_annotator_instance()`、`_create_annotator_instance()` に引数を追加する |
| `webapi/annotator.py` | `WebApiAnnotator.__init__()` と `_run_inference()` に引数を追加し、値を保持する |
| `webapi/provider_manager.py` | `_build_system_prompt()`、`run_inference_with_model_async()`、`run_inference_with_model()` に引数を追加する |

### LoRAIro 側(1 ファイル)

| ファイル | 変更内容 |
|---|---|
| `src/lorairo/annotations/annotator_adapter.py` | `annotate()` 内で `config_service.get_setting("prompts", "additional", "")` を読み込み、`annotate(..., additional_prompt=...)` へ渡す |

---

## 新しい `BASE_PROMPT`

WD-Tagger などのタガーモデルは被写体の識別を得意とする一方、ポーズ、光源、構図、スタイルの記述が弱い。そこで、WebAPI がその弱点を補う役割分担とする。

```
You are an expert image annotation assistant for AI training datasets.

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

## Scoring (1.00–10.00)
Rate the overall quality across three dimensions:

Technical & Composition (0–4 pts):
- Image clarity, sharpness, or rendering quality
- Compositional strength: framing, balance, visual flow

Artistic Merit (0–4 pts):
- Lighting and atmosphere execution
- Style consistency and expressiveness
- Detail level appropriate to the work

Overall Impact (0–2 pts):
- Immediate visual appeal and cohesion

Score reference:
- 9.00–10.00: Exceptional, masterwork quality
- 7.50–8.99: High quality, professional level
- 6.00–7.49: Good quality, minor imperfections
- 4.50–5.99: Average, notable areas for improvement
- Below 4.50: Significant quality issues

## Output Format
Respond ONLY in this exact format — no additional text:

tags: [comma-separated descriptors, 20–50 items, always specify left/right for directional elements, no underscores]
caption: [1–2 objective sentences emphasizing pose, lighting, and composition]
score: [X.XX]
```

---

## 詳細実装仕様

### `_build_system_prompt()` の変更

```python
def _build_system_prompt(
    capabilities: set[TaskCapability] | frozenset[TaskCapability] | None,
    additional_prompt: str | None = None,
) -> str:
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

### `AnnotatorLibraryAdapter.annotate()` の変更(LoRAIro 側)

```python
def annotate(
    self,
    images: list[Image.Image],
    litellm_model_ids: list[str],
    phash_list: list[str] | None = None,
) -> PHashAnnotationResults:
    ...
    api_keys = self._prepare_api_keys()
    additional_prompt = self.config_service.get_setting("prompts", "additional", "") or None

    results = annotate(
        images_list=images,
        model_name_list=litellm_model_ids,
        phash_list=phash_list,
        api_keys=api_keys,
        additional_prompt=additional_prompt,
    )
    ...
```

---

## エラーハンドリング

- `additional_prompt` が空文字列や空白のみの場合は `None` と同等に扱い、`BASE_PROMPT` のみを使用する。
- 設定ファイルの不正などで設定取得に失敗した場合は、`additional_prompt=None` へフォールバックしてエラーログを出力する。
- `iam-lib` 側はプロンプトの結合以上の処理を行わないため、追加の例外処理は設けない。

---

## テスト方針

### `iam-lib` 側

- `_build_system_prompt()` の単体テストで以下を検証する。
  - `additional_prompt=None` のとき、`BASE_PROMPT` のみが返ること。
  - `additional_prompt=""` のとき、空文字が無視されて `BASE_PROMPT` のみが返ること。
  - `additional_prompt="custom text"` のとき、`BASE_PROMPT + "\n\n" + "custom text"` が返ること。
  - `capabilities={RATINGS}` と `additional_prompt` を併用したとき、すべて結合されること。
- `WebApiAnnotator` の既存テストが通り、後方互換が保たれていることを確認する。

### LoRAIro 側

- `annotate` をモック化し、`AnnotatorLibraryAdapter.annotate()` で `additional_prompt` が正しく渡されることを確認する。
- 設定に `additional = "test"` がある場合にその値が渡されることを確認する。

---

## 後方互換性

- すべての対象関数に `additional_prompt: str | None = None` のデフォルト引数を設ける。
- Batch API など既存の呼び出し側は引数なしでそのまま動作する。
- `BASE_PROMPT` の内容変更はアノテーション結果に影響するが、API シグネチャの後方互換は維持される。

---

## 対象外(スコープ外)

- GUI 入力欄の変更(すでに実装済み)。
- 設定ファイル構造の変更(`[prompts] additional` はすでに存在する)。
- Batch API プロンプト(`webapi/batch/adapters/`)の変更(別管理のため対象外)。
- 未使用定数 `SYSTEM_PROMPT` の削除。
