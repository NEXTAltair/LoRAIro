"""Provider Batch capability helper (Qt-free).

ADR 0041: provider_batch_job_widget.py に散在していた pure ロジックを
Qt 依存なしのモジュールに集約し、ModelSelectionWidget と将来の D Wave が
重複実装なく再利用できるようにする。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lorairo.services.provider_batch_workflow_service import TASK_TYPE_ENDPOINTS

_DIRECT_PROVIDERS = frozenset({"openai", "anthropic"})
_OMNI_MODERATION_PREFIX = "omni-moderation-"


class MixedBatchTaskTypeError(ValueError):
    """moderation (rating確定) モデルと通常モデルが混在して task_type を確定できない (#1098)。"""


def direct_provider_for_model(model: Any) -> str | None:
    """モデルオブジェクトから direct provider 名を解決する。

    provider フィールドが直接 provider の場合はそのまま使い、
    litellm_model_id のルートプレフィックスを補助判断として使う。
    OpenRouter など direct でないプロバイダは None を返す。

    Args:
        model: provider と litellm_model_id 属性を持つモデルオブジェクト。

    Returns:
        "openai" / "anthropic" のいずれか、または None (direct 判定不可)。
    """
    provider = str(getattr(model, "provider", "") or "").lower()
    litellm_id = str(getattr(model, "litellm_model_id", "") or "")
    route_prefix = litellm_id.split("/", 1)[0].lower() if "/" in litellm_id else ""
    direct = provider if provider in _DIRECT_PROVIDERS else route_prefix
    return direct if direct in _DIRECT_PROVIDERS else None


def litellm_id_from_batch_model(raw: Any) -> str | None:
    """バッチ対応モデルの raw エントリから litellm_model_id を抽出する。

    Args:
        raw: str、または litellm_model_id / model_id / name 属性を持つオブジェクト。

    Returns:
        litellm_model_id 文字列、または解決できない場合 None。
    """
    if isinstance(raw, str):
        return raw
    value = (
        getattr(raw, "litellm_model_id", None)
        or getattr(raw, "model_id", None)
        or getattr(raw, "name", None)
    )
    return str(value) if value else None


def endpoint_for_task(provider: str, task_type: str) -> str:
    """provider と task_type からエンドポイントパスを返す。

    TASK_TYPE_ENDPOINTS (SSoT) から解決し、未対応の組み合わせには ValueError。

    Args:
        provider: "openai" または "anthropic"。
        task_type: "annotation" または "rating_preflight"。

    Returns:
        エンドポイントパス文字列 (例: "/v1/chat/completions")。

    Raises:
        ValueError: provider / task_type の組み合わせがサポートされていない場合。
    """
    provider_tasks = TASK_TYPE_ENDPOINTS.get(task_type)
    if provider_tasks is None:
        raise ValueError(f"task_type '{task_type}' はサポートされていません。")
    endpoint = provider_tasks.get(provider)
    if endpoint is None:
        raise ValueError(f"Provider '{provider}' は task_type '{task_type}' をサポートしていません。")
    return endpoint


def _model_has_model_type(model: Any, model_type: str) -> bool:
    """モデルが指定した model_type を持つか確認する。

    Args:
        model: model_types 属性 (iterable) を持つオブジェクト。
        model_type: 検索する model_type 名。

    Returns:
        一致する model_type が存在する場合 True。
    """
    model_types = getattr(model, "model_types", ())
    return any(getattr(item, "name", None) == model_type for item in model_types)


def model_supports_task_type(model: Any, provider: str, task_type: str) -> bool:
    """モデルが指定 task_type をサポートするか判定する。

    ADR 0041 修正: annotation は openai / anthropic 両方を許可する
    (旧 GUI は anthropic 限定だったが、service+CLI は openai annotation を既サポート)。
    rating_preflight は openai かつ litellm_model_id が openai/omni-moderation-* のみ。

    annotation submit は /v1/chat/completions を使うため、moderation 専用の
    openai/omni-moderation-* は annotation 候補から除外する (ADR 0038)。
    batch-capable source は task 非依存で moderation モデルも含むため、
    UI 側で弾かないと submit 時に失敗するモデルを露出してしまう。

    Args:
        model: litellm_model_id と model_types 属性を持つモデルオブジェクト。
        provider: "openai" または "anthropic"。
        task_type: "annotation" または "rating_preflight"。

    Returns:
        task_type / provider の組み合わせが有効なら True。
    """
    if task_type == "annotation":
        if provider not in _DIRECT_PROVIDERS:
            return False
        # moderation 専用モデルは annotation (/v1/chat/completions) では使えない
        return not _is_omni_moderation_model(model)
    if task_type == "rating_preflight":
        if provider != "openai":
            return False
        return _is_omni_moderation_model(model)
    return False


def _is_omni_moderation_model(model: Any) -> bool:
    """モデルが openai/omni-moderation-* (moderation 専用) か判定する。

    Args:
        model: litellm_model_id 属性を持つモデルオブジェクト。

    Returns:
        bare モデル名が omni-moderation- で始まる単一セグメントなら True。
    """
    litellm_id = str(getattr(model, "litellm_model_id", "") or "").lower()
    # openai/ プレフィックスを除去して bare モデル名を確認
    bare = litellm_id.removeprefix("openai/")
    return bare.startswith(_OMNI_MODERATION_PREFIX) and "/" not in bare


def is_omni_moderation_model(model: Any) -> bool:
    """モデルが openai/omni-moderation-* (moderation 専用) か判定する (public、#1098)。

    :func:`_is_omni_moderation_model` の公開ラッパー。GUI 配線から moderation モデルの
    rating確定用途を判別するために使う。

    Args:
        model: litellm_model_id 属性を持つモデルオブジェクト。

    Returns:
        moderation 専用モデルなら True。
    """
    return _is_omni_moderation_model(model)


def resolve_batch_task_type(models: Sequence[Any]) -> str:
    """選択モデル集合から async batch dispatch の task_type を決定する (#1098)。

    全モデルが omni-moderation (rating確定用途) なら ``"rating_preflight"``、
    全モデルが非 moderation なら ``"annotation"`` を返す。両者が混在する場合は
    「非 batch 混在は拒否」原則 (ADR 0076 §2) に従い送出する。

    OpenAI 公式 Batch API は ``/v1/moderations`` を提供するため、moderation モデル
    のみの選択は正当な Batch API 送信 (task_type=rating_preflight) として扱う。

    Args:
        models: 選択された (解決済み) モデルオブジェクト集合。空集合は "annotation"。

    Returns:
        "annotation" または "rating_preflight"。

    Raises:
        MixedBatchTaskTypeError: moderation モデルと通常モデルが混在する場合。
    """
    resolved = list(models)
    moderation_count = sum(1 for model in resolved if _is_omni_moderation_model(model))
    if moderation_count == 0:
        return "annotation"
    if moderation_count == len(resolved):
        return "rating_preflight"
    raise MixedBatchTaskTypeError(
        "モデレーション (rating 確定) モデルと通常モデルは同時に Batch API 送信できません。\n"
        "いずれか一方のみを選択してください。"
    )
