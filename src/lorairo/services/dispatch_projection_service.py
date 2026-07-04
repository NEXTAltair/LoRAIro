"""Async batch dispatch 射影 service (Qt-free)。

ADR 0076 §2: Annotate の選択モデル集合を「async Provider Batch dispatch の射影」
として確定する。選択モデルを ``list_batch_capable_models()`` の discovery と
intersect し、``provider_batch_capability`` helper で provider / task ルールを
当てて batch 適格を判定する。batch-capable モデル1台につき 1 つの
:class:`DispatchEntry` (= 1 ``provider_batch_jobs`` 行) を生成する。

設計上の不変条件:

- **部分射影を許可し、非対応モデルは同期へ振り分ける** (#1133、2026-07-04 ユーザー決定で
  #884 Phase 2a の「非 batch-capable 混在は拒否 (a)」を上書き)。batch 対応モデルのみを
  射影し、非対応 (discovery 外 / provider 非 direct / task_type 非対応) は
  ``ineligible_litellm_model_ids`` として返す。呼び出し側 (GUI 配線) が ineligible を
  同期ワークフローへ回し、batch と同期を並行起動する。「選んだのに走らない」問題は
  拒否ではなく自動振り分けで解消する。
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
    """選択モデル集合から射影した dispatch 実行計画。

    Attributes:
        entries: batch 対応モデル 1 台 = 1 entry の送信計画。
        ineligible_litellm_model_ids: batch 非対応で同期へ振り分けるべき
            litellm_model_id (順序保持、#1133)。呼び出し側が同期ワークフローへ回す。
    """

    entries: tuple[DispatchEntry, ...]
    ineligible_litellm_model_ids: tuple[str, ...] = ()

    @property
    def job_count(self) -> int:
        """生成される provider batch job 数 (= batch-capable モデル数)。"""
        return len(self.entries)


def _partition_batch_eligibility(
    selected: Sequence[str],
    batch_capable_models: Sequence[Any],
    model_resolver: Callable[[str], Any | None],
    task_type: str,
) -> tuple[list[tuple[str, Any, str]], list[str]]:
    """選択モデルを batch 適格 (id, model, provider) と非適格 id へ分ける (SSoT ロジック)。

    ``project_async_batch_dispatch`` と LEDGER preview (:func:`batch_eligible_litellm_ids`)
    が同じ eligibility 判定を共有するための内部ヘルパー (#1136: 実振り分けと preview の
    不整合を防ぐ)。判定: discovery に含まれ、DB 解決でき、direct provider を持ち、
    指定 task_type を support するモデルのみ適格。

    Returns:
        (resolved_models=[(litellm_id, model, provider)], ineligible=[litellm_id])。
    """
    discovery_ids = {
        resolved
        for raw in batch_capable_models
        if (resolved := litellm_id_from_batch_model(raw)) is not None
    }
    resolved_models: list[tuple[str, Any, str]] = []
    ineligible: list[str] = []
    for litellm_id in dict.fromkeys(selected):
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
    return resolved_models, ineligible


def batch_eligible_litellm_ids(
    *,
    selected_litellm_model_ids: Sequence[str],
    batch_capable_models: Sequence[Any],
    model_resolver: Callable[[str], Any | None],
    task_type: str,
) -> list[str]:
    """選択のうち task_type で batch 対応する litellm_model_id を返す (順序保持、#1136)。

    ``project_async_batch_dispatch`` と同じ eligibility 判定を共有し、Annotate の LEDGER
    レーンプレビュー (batch/sync 表示) を実際の振り分けと一致させる (Codex P2)。

    Args:
        selected_litellm_model_ids: 選択モデル集合。
        batch_capable_models: ``list_batch_capable_models()`` の discovery 結果。
        model_resolver: litellm_model_id → DB Model 解決 callable。
        task_type: "annotation" / "rating_preflight"。

    Returns:
        batch 対応する litellm_model_id のリスト (順序保持)。
    """
    resolved_models, _ = _partition_batch_eligibility(
        list(selected_litellm_model_ids), batch_capable_models, model_resolver, task_type
    )
    return [litellm_id for litellm_id, _model, _provider in resolved_models]


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
        task_type: dispatch する task_type ("annotation" / "rating_preflight")。

    Returns:
        batch-capable モデル1台 = 1 entry の :class:`DispatchProjection`。
        指定 task_type に対応しない / discovery 外のモデルは拒否せず
        ``ineligible_litellm_model_ids`` に載せて返す (#1133、呼び出し側が同期へ回す)。
        eligible が 0 件でも例外にせず、全モデルを ineligible として返す。

    Raises:
        DispatchProjectionError: 選択 / 画像が空の場合のみ。
    """
    selected = list(dict.fromkeys(selected_litellm_model_ids))
    if not selected:
        raise DispatchProjectionError("モデルが選択されていません。")

    ids = tuple(int(image_id) for image_id in image_ids)
    if not ids:
        raise DispatchProjectionError("対象画像がありません。")

    resolved_models, ineligible = _partition_batch_eligibility(
        selected, batch_capable_models, model_resolver, task_type
    )

    # #1133: 非対応モデルは拒否せず ineligible として返す。呼び出し側が同期へ振り分ける。
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
    return DispatchProjection(entries=entries, ineligible_litellm_model_ids=tuple(ineligible))
