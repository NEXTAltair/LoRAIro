"""モデルの route 判定・畳み込み・API key validation helper (Issue #241)。

image-annotator-lib の registry には同一モデルが「直接プロバイダー経路」と
「OpenRouter 経由経路」の 2 経路で別エントリとして登録される。本モジュールは
`litellm_model_id` の prefix を見て route を判定し、canonical key で 1 モデル
1 行に畳み込んだ表示用 view model を構築する。実行直前の API key 不足検出も
担当する。

設計判断:
    - route 判定は LoRAIro 側で持つ (image-annotator-lib の private helper
      `_split_litellm_id` を import せず独立)。判定ロジックは prefix
      `openrouter/` の単純 whitelist マッチで、5 行未満で完結する。
    - `Route` whitelist: `{"openrouter"}` のみ "openrouter" 扱い、それ以外は
      "direct"。lib 側 dispatch に新 provider が追加されても fallback は
      "direct" のまま安全。
    - `required_provider` 解決: `Model.provider` を一次ソースとし、未設定
      (None/"unknown") の場合のみ `litellm_model_id` の最初のセグメントから
      推定する。

参照:
    - Issue #241
    - ADR 0023 Phase 1.9 / 1.10 / 1.11
    - Plan: docs/plans/...
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from ..database.schema import Model
from ..utils.log import logger

Route = Literal["direct", "openrouter"]
RoutePreference = Literal["auto", "direct", "openrouter", "all"]

_OPENROUTER_PREFIX = "openrouter/"
_LOCAL_PROVIDER = "local"
_UNKNOWN_PROVIDERS = frozenset({"", "unknown"})

# litellm_model_id 先頭セグメントに対する provider 別名の正規化マップ。
# 例: "gemini/..." は "google" key を要求する。
_PROVIDER_ALIAS_MAP: dict[str, str] = {
    "gemini": "google",
    "vertex_ai": "google",
}

# 既知 WebAPI provider whitelist。
# ローカル ML モデルでも namespaced な ID (例: ``some/very/deep/local-tagger``) を
# 持ちうるため、prefix から無条件に provider を抽出すると "some" key を要求する誤判定
# になる (Codex P2: PR #248 r3230850133)。whitelist に含まれる prefix のみ WebAPI
# provider として扱い、それ以外は ``"local"`` に倒して validation を skip する。
# 新しい WebAPI provider を追加するときは alias map (gemini -> google など) と
# 併せてここに追記する。
_WEBAPI_PROVIDERS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google",
        "openrouter",
    }
)


def detect_route(litellm_model_id: str) -> Route:
    """litellm_model_id の prefix から route を判定。

    Args:
        litellm_model_id: 例 ``"openrouter/openai/gpt-4o"`` / ``"openai/gpt-4o"``。

    Returns:
        "openrouter" prefix なら "openrouter"、それ以外は "direct"。
    """
    return "openrouter" if litellm_model_id.startswith(_OPENROUTER_PREFIX) else "direct"


def canonical_key(litellm_model_id: str) -> str:
    """同一モデル判定用の canonical key を返す。

    ``openrouter/`` prefix を剥がし、direct route との比較を可能にする。

    Args:
        litellm_model_id: 例 ``"openrouter/anthropic/claude-3-5-sonnet"``。

    Returns:
        prefix を除去した文字列。例 ``"anthropic/claude-3-5-sonnet"``。
    """
    return litellm_model_id.removeprefix(_OPENROUTER_PREFIX)


def required_provider_for(litellm_model_id: str, provider_hint: str | None = None) -> str:
    """API key 要求 provider 名を返す。

    解決順序:
        1. ``provider_hint`` (= ``Model.provider``) が信頼できる ``str`` なら採用
           (ただし WebAPI provider whitelist または ``"local"`` のみ受け入れる)
        2. fallback: ``litellm_model_id`` の最初のセグメントが WebAPI provider
           whitelist に該当する場合のみ provider 名を返す
        3. それ以外 (slash 無し bare 名 / 未知の namespaced ID) は ``"local"``

    Codex P2 (PR #248 r3230850133): ローカル ML モデルでも namespaced ID
    (例: ``"some/very/deep/local-tagger"``) を持ちうる。prefix を無条件に
    provider として採用すると、存在しない provider key を要求して validation
    abort してしまうため、whitelist 照合で defensive に弾く。

    Args:
        litellm_model_id: 例 ``"openrouter/openai/gpt-4o"`` /
            ``"some/very/deep/local-tagger"``。
        provider_hint: ``Model.provider`` の値 (任意)。型契約は ``str | None`` だが、
            テストの Mock 経由で別型が紛れ込んでもクラッシュしないよう
            ``isinstance(str)`` ガードで防御的に弾く。

    Returns:
        provider 名。``"openrouter"`` / ``"openai"`` / ``"anthropic"`` /
        ``"google"`` / ``"local"`` のいずれか。
    """
    if isinstance(provider_hint, str) and provider_hint.strip():
        p_normalized = provider_hint.strip().lower()
        if p_normalized not in _UNKNOWN_PROVIDERS:
            canonical = _PROVIDER_ALIAS_MAP.get(p_normalized, p_normalized)
            # 既知 WebAPI provider または local のみ採用、それ以外は fallback へ
            if canonical in _WEBAPI_PROVIDERS or canonical == _LOCAL_PROVIDER:
                return canonical

    head, sep, _ = litellm_model_id.partition("/")
    if sep == "":
        return _LOCAL_PROVIDER

    head_normalized = head.strip().lower()
    canonical = _PROVIDER_ALIAS_MAP.get(head_normalized, head_normalized)
    # 既知 WebAPI provider のみ採用、未知 prefix は local 扱い (namespaced local model 対応)
    if canonical in _WEBAPI_PROVIDERS:
        return canonical
    return _LOCAL_PROVIDER


@dataclass(frozen=True)
class ModelRouteCandidate:
    """同一 canonical key に属する 1 つの route candidate。"""

    litellm_model_id: str
    route: Route
    required_provider: str
    model: Model


@dataclass(frozen=True)
class DisplayModelOption:
    """GUI / CLI 表示用に 1 モデル 1 行に畳み込んだ view model。"""

    canonical_key: str
    display_name: str
    capabilities: tuple[str, ...]
    preferred: ModelRouteCandidate
    alternatives: tuple[ModelRouteCandidate, ...] = field(default_factory=tuple)

    @property
    def all_candidates(self) -> tuple[ModelRouteCandidate, ...]:
        """preferred + alternatives を route 順 (direct -> openrouter) で返す。"""
        return (self.preferred, *self.alternatives)


def build_available_providers(api_keys: dict[str, str]) -> set[str]:
    """API key 辞書から「key が設定されている」provider 集合を返す。

    空文字や空白のみのキーは「未設定」扱いとして除外する。

    Args:
        api_keys: provider 名 -> API key 文字列。

    Returns:
        非空 key を持つ provider 名集合。
    """
    return {provider for provider, key in api_keys.items() if key and key.strip()}


def group_model_routes(models: Iterable[Model]) -> dict[str, list[ModelRouteCandidate]]:
    """canonical_key で grouping した candidate dict を返す。

    Args:
        models: DB ``Model`` のリスト/イテラブル。

    Returns:
        canonical_key -> ``[ModelRouteCandidate, ...]`` の dict。
        各リストは direct -> openrouter の順にソート済み。
    """
    grouped: dict[str, list[ModelRouteCandidate]] = {}
    for model in models:
        route = detect_route(model.litellm_model_id)
        required = required_provider_for(model.litellm_model_id, model.provider)
        candidate = ModelRouteCandidate(
            litellm_model_id=model.litellm_model_id,
            route=route,
            required_provider=required,
            model=model,
        )
        grouped.setdefault(canonical_key(model.litellm_model_id), []).append(candidate)

    # direct -> openrouter の順に並べる (UI 表示と select_preferred_route の挙動を安定させる)
    for candidates in grouped.values():
        candidates.sort(key=lambda c: 0 if c.route == "direct" else 1)
    return grouped


def select_preferred_route(
    candidates: list[ModelRouteCandidate],
    available_providers: set[str],
    preference: RoutePreference = "auto",
) -> ModelRouteCandidate | None:
    """available_providers を考慮して preferred route を 1 つ選ぶ。

    Args:
        candidates: 同一 canonical_key の candidate 群 (direct / openrouter)。
        available_providers: API key 設定済みの provider 名集合
            (``build_available_providers()`` の戻り値を想定)。
        preference: ``"auto"`` / ``"direct"`` / ``"openrouter"`` / ``"all"``。
            ``"all"`` は preferred 単体としては ``"auto"`` と同じ挙動 (caller が
            ``DisplayModelOption.alternatives`` を含めて全 candidate を展開する想定)。

    Returns:
        preferred candidate。``preference="direct"`` で direct candidate が無い、
        など見つからない場合は None。
    """
    if not candidates:
        return None

    by_route: dict[Route, ModelRouteCandidate] = {c.route: c for c in candidates}
    direct = by_route.get("direct")
    openrouter = by_route.get("openrouter")

    if preference == "direct":
        return direct
    if preference == "openrouter":
        return openrouter

    # auto / all: direct を優先しつつ available_providers を考慮
    if direct is not None and direct.required_provider in available_providers:
        return direct
    if openrouter is not None and openrouter.required_provider in available_providers:
        return openrouter
    # どちらの provider key も未設定: direct 優先で disabled 表示用に返す
    return direct or openrouter


def build_display_options(
    models: Iterable[Model],
    available_providers: set[str] | None = None,
    preference: RoutePreference = "auto",
) -> list[DisplayModelOption]:
    """Model リストから DisplayModelOption リストを構築。

    canonical_key で grouping し、preferred route を 1 つ選んで残りを
    alternatives に格納する。``preference="all"`` の場合は alternatives に全
    候補が残るため、caller (CLI ``models list --route all``) は各 candidate を
    1 行ずつ展開する。

    Args:
        models: フィルタ済みの DB Model リスト。
        available_providers: API key 設定済み provider 集合。None の場合は全
            provider を available 扱い (= 従来の畳み込み挙動と同等)。
        preference: route 優先順位。

    Returns:
        DisplayModelOption リスト。display_name はソート安定性のため
        ``preferred.model.name`` を昇順ソート。
    """
    if available_providers is None:
        available_providers = set()
        treat_all_available = True
    else:
        treat_all_available = False

    grouped = group_model_routes(models)
    options: list[DisplayModelOption] = []

    for ckey, candidates in grouped.items():
        effective_available = (
            {c.required_provider for c in candidates} if treat_all_available else available_providers
        )
        preferred = select_preferred_route(candidates, effective_available, preference)
        if preferred is None:
            continue
        alternatives = tuple(c for c in candidates if c.litellm_model_id != preferred.litellm_model_id)

        # preferred と alternatives で capabilities が食い違う場合は preferred 側を採用、警告ログを残す
        preferred_caps = tuple(preferred.model.capabilities)
        for alt in alternatives:
            if tuple(alt.model.capabilities) != preferred_caps:
                logger.warning(
                    "capabilities mismatch between routes: canonical_key=%s, "
                    "preferred=%s caps=%s, alternative=%s caps=%s",
                    ckey,
                    preferred.litellm_model_id,
                    preferred_caps,
                    alt.litellm_model_id,
                    tuple(alt.model.capabilities),
                )

        options.append(
            DisplayModelOption(
                canonical_key=ckey,
                display_name=preferred.model.name,
                capabilities=preferred_caps,
                preferred=preferred,
                alternatives=alternatives,
            )
        )

    options.sort(key=lambda o: o.display_name.lower())
    return options


def validate_api_keys_for_models(
    litellm_model_ids: list[str],
    api_keys: dict[str, str],
    provider_hints: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """選択モデルが要求する provider key の不足を返す。

    LoRAIro 側で実行直前にこの検証を呼び、不足があれば image-annotator-lib に
    渡す前にユーザーに通知して abort する。ローカル ML モデル
    (``required_provider == "local"``) は API key を要求しないため skip。

    Args:
        litellm_model_ids: 検証対象の ``litellm_model_id`` リスト (重複可)。
        api_keys: provider 名 -> API key 文字列。空文字は「未設定」扱い。
        provider_hints: ``litellm_model_id`` -> ``Model.provider`` の hint map。
            DB から既に Model を引いている場合は渡すと判定精度が上がる
            (None/"unknown" 時は内部 fallback)。

    Returns:
        不足の ``(litellm_model_id, missing_provider)`` ペア。空なら問題なし。
        重複する litellm_model_id は最初の検出時のみ報告する。
    """
    available = build_available_providers(api_keys)
    missing: list[tuple[str, str]] = []
    seen: set[str] = set()
    for litellm_id in litellm_model_ids:
        if litellm_id in seen:
            continue
        seen.add(litellm_id)
        hint = provider_hints.get(litellm_id) if provider_hints else None
        required = required_provider_for(litellm_id, hint)
        if required == _LOCAL_PROVIDER:
            continue
        if required not in available:
            missing.append((litellm_id, required))
    return missing


__all__ = [
    "DisplayModelOption",
    "ModelRouteCandidate",
    "Route",
    "RoutePreference",
    "build_available_providers",
    "build_display_options",
    "canonical_key",
    "detect_route",
    "group_model_routes",
    "required_provider_for",
    "select_preferred_route",
    "validate_api_keys_for_models",
]
