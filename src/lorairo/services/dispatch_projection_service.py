"""Async batch dispatch 射影 service (Qt-free)。

ADR 0076 §2: Annotate の選択モデル集合を「async Provider Batch dispatch の射影」
として確定する。選択モデルを ``list_batch_capable_models()`` の discovery と
intersect し、``provider_batch_capability`` helper で provider / task ルールを
当てて batch 適格を判定する。batch-capable モデル1台につき 1 つの
:class:`DispatchEntry` (= 1 ``provider_batch_jobs`` 行) を生成する。

設計上の不変条件 (ADR 0076 §2):

- **非 batch-capable 混在は拒否** (a)。部分射影しない。「選んだのに走らない」を防ぐ。
- **1 submit = 1 model**: 各 entry は単一モデル。呼び出し側が entry ごとに
  ``submit_images`` をループ呼び出しすれば N 行になる (service 改変ゼロ)。
- 射影出力契約に **model_id (DB Model.id) / prompt_profile / description /
  processed 画像パス (image_paths override, ADR 0064)** を含める。

moderation preflight の自動2段オーケストレーションは本射影の対象外
(ADR 0076 line 54 / ADR 0070 の deferral を引き継ぐ)。送信ゲートの fail-closed
判定は呼び出し側 (GUI 配線) が ``classify_preflight_counts`` で行う。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from lorairo.services.provider_batch_capability import (
    direct_provider_for_model,
    endpoint_for_task,
    litellm_id_from_batch_model,
    model_supports_task_type,
)


class DispatchProjectionError(ValueError):
    """async batch dispatch 射影が成立しないときに送出する。"""


@dataclass(frozen=True)
class DispatchEntry:
    """単一モデル = 単一 provider batch job の dispatch 契約。

    Attributes:
        provider: direct provider ("openai" / "anthropic")。
        endpoint: provider / task_type から解決したエンドポイントパス。
        litellm_model_id: 送信に使う litellm_model_id。
        model_id: DB ``Model.id`` (rating_preflight reject 回避・結果 import に必須)。
        prompt_profile: job metadata の prompt profile (ADR 0038)。
        description: job 監査用の説明 (任意)。
        task_type: 現状 "annotation" 固定。
        image_ids: 送信対象の LoRAIro image_id。
        image_paths: processed/resized パス override (ADR 0064)。None なら service 側解決。
    """

    provider: str
    endpoint: str
    litellm_model_id: str
    model_id: int
    prompt_profile: str
    description: str | None
    task_type: str
    image_ids: tuple[int, ...]
    image_paths: dict[int, str] | None


@dataclass(frozen=True)
class DispatchProjection:
    """選択モデル集合から射影した dispatch 実行計画。"""

    entries: tuple[DispatchEntry, ...]

    @property
    def job_count(self) -> int:
        """生成される provider batch job 数 (= batch-capable モデル数)。"""
        return len(self.entries)


def project_async_batch_dispatch(
    *,
    selected_litellm_model_ids: Sequence[str],
    batch_capable_models: Sequence[Any],
    model_resolver: Callable[[str], Any | None],
    image_ids: Sequence[int],
    prompt_profile: str,
    description: str | None = None,
    image_paths: Mapping[int, str] | None = None,
    task_type: str = "annotation",
) -> DispatchProjection:
    """選択モデル集合を async batch dispatch の実行計画へ射影する。

    Args:
        selected_litellm_model_ids: Annotate の選択モデル集合 (SSoT)。重複は順序保持で除去。
        batch_capable_models: ``list_batch_capable_models()`` の discovery 結果
            (str または litellm_model_id 属性を持つオブジェクト)。
        model_resolver: litellm_model_id から DB Model を解決する callable
            (例: ``model_repo.get_model_by_litellm_id``)。
        image_ids: 送信対象の image_id。
        prompt_profile: job metadata の prompt profile。
        description: job 監査用の説明 (任意)。
        image_paths: processed/resized パス override (ADR 0064、任意)。
        task_type: dispatch する task_type (現状 "annotation")。

    Returns:
        batch-capable モデル1台 = 1 entry の :class:`DispatchProjection`。

    Raises:
        DispatchProjectionError: 選択 / 画像が空、または非 batch-capable モデルが
            混在する場合 ((a) 拒否)。
    """
    selected = list(dict.fromkeys(selected_litellm_model_ids))
    if not selected:
        raise DispatchProjectionError("モデルが選択されていません。")

    ids = tuple(int(image_id) for image_id in image_ids)
    if not ids:
        raise DispatchProjectionError("対象画像がありません。")

    discovery_ids = {
        resolved
        for raw in batch_capable_models
        if (resolved := litellm_id_from_batch_model(raw)) is not None
    }

    resolved_models: list[tuple[str, Any, str]] = []
    ineligible: list[str] = []
    for litellm_id in selected:
        if litellm_id not in discovery_ids:
            ineligible.append(litellm_id)
            continue
        model = model_resolver(litellm_id)
        if model is None or getattr(model, "id", None) is None:
            ineligible.append(litellm_id)
            continue
        provider = direct_provider_for_model(model)
        if provider is None or not model_supports_task_type(model, provider, task_type):
            ineligible.append(litellm_id)
            continue
        resolved_models.append((litellm_id, model, provider))

    if ineligible:
        raise DispatchProjectionError(
            "次のモデルは Batch API 非対応のため async 送信できません: " + ", ".join(ineligible)
        )

    paths = dict(image_paths) if image_paths is not None else None
    entries = tuple(
        DispatchEntry(
            provider=provider,
            endpoint=endpoint_for_task(provider, task_type),
            litellm_model_id=litellm_id,
            model_id=int(model.id),
            prompt_profile=prompt_profile,
            description=description,
            task_type=task_type,
            image_ids=ids,
            image_paths=paths,
        )
        for litellm_id, model, provider in resolved_models
    )
    return DispatchProjection(entries=entries)
