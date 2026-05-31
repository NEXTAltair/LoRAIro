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
from typing import Literal, cast, get_args

from ..database.schema import Model
from ..utils.log import logger

Route = Literal["direct", "openrouter"]
RoutePreference = Literal["auto", "direct", "openrouter", "all"]

_OPENROUTER_PREFIX = "openrouter/"
_DISPLAY_GATEWAY_PREFIXES = frozenset({"openrouter", "vercel_ai_gateway"})
_LOCAL_PROVIDER = "local"
_UNKNOWN_PROVIDERS = frozenset({"", "unknown"})
# Issue #249: parse_route_preference の validation 集合 (Literal 値域と完全一致)
_VALID_ROUTE_PREFERENCES: frozenset[str] = frozenset(get_args(RoutePreference))

# litellm_model_id 先頭セグメントに対する provider 別名の正規化マップ。
# 例: "gemini/..." は "google" key を要求する。
_PROVIDER_ALIAS_MAP: dict[str, str] = {
    "gemini": "google",
    "vertex_ai": "google",
}

_DISPLAY_FAMILY_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "qwen": "Qwen",
}


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


@dataclass(frozen=True)
class ModelRouteIdentity:
    """1 モデル行の route / provider / display 解釈結果。

    `litellm_model_id` の文字列解析と `Model.provider` / `requires_api_key`
    による補正を一箇所に集約し、GUI / CLI の表示判定を揃える。
    """

    litellm_model_id: str
    route: Route
    canonical_key: str
    required_provider: str
    display_name: str
    display_family: str
    is_webapi: bool


def _normalized_provider_hint(provider_hint: str | None) -> str | None:
    """信頼できる provider hint を lowercase で返す。unknown/空は None。"""
    if not isinstance(provider_hint, str):
        return None
    normalized = provider_hint.strip().lower()
    if normalized in _UNKNOWN_PROVIDERS:
        return None
    return normalized


def is_webapi_model_id(
    litellm_model_id: str,
    provider_hint: str | None = None,
    requires_api_key: bool | None = None,
) -> bool:
    """litellm_model_id が Web API 経路 ID かを判定する。

    ``requires_api_key`` が分かる caller ではそれを一次ソースにする。local model の
    ``info.name`` には slash 付き namespace が入り得るため、slash の有無だけでは判定しない。
    """
    if requires_api_key is not None:
        return requires_api_key

    normalized_provider = _normalized_provider_hint(provider_hint)
    if normalized_provider == _LOCAL_PROVIDER:
        return False
    if normalized_provider is not None:
        return True

    return "/" in litellm_model_id


def display_key_for(litellm_model_id: str) -> str:
    """UI 表示用に execution gateway prefix を除いた model key を返す。"""
    display_key = canonical_key(litellm_model_id)
    head, sep, tail = display_key.partition("/")
    if sep and head.strip().lower() in _DISPLAY_GATEWAY_PREFIXES:
        return tail
    return display_key


def display_family_name_for(provider_key: str) -> str:
    """provider key を UI 表示用 family 名へ正規化する。"""
    family_key = provider_key.strip().lower()
    if not family_key:
        return _LOCAL_PROVIDER
    return _DISPLAY_FAMILY_NAMES.get(family_key, family_key.title())


def build_model_route_identity(
    litellm_model_id: str,
    name: str,
    provider_hint: str | None = None,
    requires_api_key: bool | None = None,
) -> ModelRouteIdentity:
    """1 モデル行の route / canonical / display identity を構築する。

    `requires_api_key` が分かる場合は local/WebAPI 判定の一次情報として扱う。
    slash の有無は WebAPI 判定には使わず、WebAPI と判定された後の表示 key
    解析にだけ使う。
    """
    route = detect_route(litellm_model_id)
    ckey = canonical_key(litellm_model_id)
    normalized_provider = _normalized_provider_hint(provider_hint)
    is_webapi = is_webapi_model_id(litellm_model_id, provider_hint, requires_api_key)

    if not is_webapi:
        return ModelRouteIdentity(
            litellm_model_id=litellm_model_id,
            route=route,
            canonical_key=ckey,
            required_provider=_LOCAL_PROVIDER,
            display_name=name,
            display_family=_LOCAL_PROVIDER,
            is_webapi=False,
        )

    required_provider = required_provider_for(litellm_model_id, provider_hint)
    display_key = display_key_for(litellm_model_id)
    provider_for_display = normalized_provider or required_provider

    if "/" not in display_key:
        display_name = name
        display_family = display_family_name_for(provider_for_display)
    else:
        family_key, _, _ = display_key.partition("/")
        _, _, model_name = display_key.rpartition("/")
        display_name = model_name or name
        display_family = display_family_name_for(family_key or provider_for_display)

    return ModelRouteIdentity(
        litellm_model_id=litellm_model_id,
        route=route,
        canonical_key=ckey,
        required_provider=required_provider,
        display_name=display_name,
        display_family=display_family,
        is_webapi=True,
    )


def display_model_name_for(
    litellm_model_id: str,
    fallback_name: str,
    provider_hint: str | None = None,
    requires_api_key: bool | None = None,
) -> str:
    """UI の primary label に使う短いモデル名を返す。

    Web API モデルは ``provider/model`` または ``gateway/provider/model`` 形式のため、
    実行経路を含む raw ID ではなく最後の segment を表示する。ローカルモデルは slash
    付き namespace を持つ可能性があるため既存表示を維持する。
    """
    return build_model_route_identity(
        litellm_model_id,
        fallback_name,
        provider_hint,
        requires_api_key,
    ).display_name


def display_family_for(
    litellm_model_id: str,
    provider_hint: str | None = None,
    requires_api_key: bool | None = None,
) -> str:
    """UI grouping/provider label に使う capability family 名を返す。

    OpenRouter / Vercel AI Gateway などの execution gateway は family には出さず、
    実モデル側の provider segment (例: ``openrouter/qwen/...`` -> ``Qwen``) を使う。
    ローカルモデルは従来どおり provider hint/local として扱う。
    """
    return build_model_route_identity(
        litellm_model_id,
        litellm_model_id,
        provider_hint,
        requires_api_key,
    ).display_family


def required_provider_for(litellm_model_id: str, provider_hint: str | None = None) -> str:
    """API key 要求 provider 名を返す。

    解決順序:
        1. ``provider_hint`` (= ``Model.provider``) が信頼できる ``str`` なら採用
        2. fallback: ``litellm_model_id`` の最初のセグメント
        3. slash 無し (= bare 名、ローカル ML モデル) なら ``"local"``

    image-annotator-lib の規約上、ローカル ML モデルの ID は bare 名 (slash 無し)
    のみで、``provider/model`` 形式は LiteLLM 経由 WebAPI / OpenRouter 経路に
    限られる。よって最初の slash セグメントは常に WebAPI provider 名として扱える。

    Args:
        litellm_model_id: 例 ``"openrouter/openai/gpt-4o"``。
        provider_hint: ``Model.provider`` の値 (任意)。型契約は ``str | None`` だが、
            テストの Mock 経由で別型が紛れ込んでもクラッシュしないよう
            ``isinstance(str)`` ガードで防御的に弾く。

    Returns:
        provider 名。``"openrouter"`` / ``"openai"`` / ``"anthropic"`` /
        ``"google"`` / ``"local"`` など。
    """
    if (
        isinstance(provider_hint, str)
        and provider_hint.strip()
        and provider_hint.strip().lower() not in _UNKNOWN_PROVIDERS
    ):
        provider_normalized = provider_hint.strip().lower()
        return _PROVIDER_ALIAS_MAP.get(provider_normalized, provider_normalized)

    head, sep, _ = litellm_model_id.partition("/")
    if sep == "":
        return _LOCAL_PROVIDER

    head_normalized = head.strip().lower()
    return _PROVIDER_ALIAS_MAP.get(head_normalized, head_normalized)


@dataclass(frozen=True)
class ModelRouteCandidate:
    """同一 canonical key に属する 1 つの route candidate。"""

    litellm_model_id: str
    route: Route
    required_provider: str
    identity: ModelRouteIdentity
    model: Model


@dataclass(frozen=True)
class DisplayModelOption:
    """GUI / CLI 表示用に 1 モデル 1 行に畳み込んだ view model。"""

    canonical_key: str
    display_name: str
    display_family: str
    capabilities: tuple[str, ...]
    preferred: ModelRouteCandidate
    alternatives: tuple[ModelRouteCandidate, ...] = field(default_factory=tuple)
    # Issue #249: preferred の required_provider が API key 未設定で disabled
    # fallback として返された場合は False。CLI `--show-unavailable` で活用。
    # default True は既存呼び出し元 (preference="all" や key 状況非考慮) の後方互換。
    available: bool = True

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
        identity = build_model_route_identity(
            model.litellm_model_id,
            model.name,
            model.provider,
            model.requires_api_key,
        )
        candidate = ModelRouteCandidate(
            litellm_model_id=model.litellm_model_id,
            route=identity.route,
            required_provider=identity.required_provider,
            identity=identity,
            model=model,
        )
        grouped.setdefault(identity.canonical_key, []).append(candidate)

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
                    "capabilities mismatch between routes: canonical_key={}, "
                    "preferred={} caps={}, alternative={} caps={}",
                    ckey,
                    preferred.litellm_model_id,
                    preferred_caps,
                    alt.litellm_model_id,
                    tuple(alt.model.capabilities),
                )

        # Issue #249: preferred の required_provider が API key 設定済みかで available 判定。
        # ローカル ML モデルは API key 不要のため常に available。
        # caller が available_providers を渡さない場合 (= treat_all_available)
        # は全 candidate を available 扱い (従来挙動と同等)。
        if treat_all_available or preferred.required_provider == _LOCAL_PROVIDER:
            is_available = True
        else:
            is_available = preferred.required_provider in available_providers

        options.append(
            DisplayModelOption(
                canonical_key=ckey,
                display_name=preferred.identity.display_name,
                display_family=preferred.identity.display_family,
                capabilities=preferred_caps,
                preferred=preferred,
                alternatives=alternatives,
                available=is_available,
            )
        )

    options.sort(key=lambda o: o.display_name.lower())
    return options


def parse_route_preference(raw: str | None) -> RoutePreference:
    """config から取得した raw 値を ``RoutePreference`` Literal に正規化。

    Issue #249: GUI / CLI の双方が config 由来 default を扱うため、不正値・None・
    空文字を ``"auto"`` に安全 fallback する共通 helper。不正値は warning log。

    Args:
        raw: ``ConfigurationService.get_setting("model_selection", "route_preference", ...)``
            の戻り値。型契約は ``str | None`` だが、Mock 経由など想定外の型が
            紛れ込んでもクラッシュしないよう ``isinstance(str)`` ガードで弾く。

    Returns:
        正規化された ``RoutePreference``。値域は
        ``Literal["auto", "direct", "openrouter", "all"]`` と完全一致。
    """
    if not isinstance(raw, str):
        return "auto"
    normalized = raw.strip().lower()
    if normalized == "":
        return "auto"
    if normalized in _VALID_ROUTE_PREFERENCES:
        return cast(RoutePreference, normalized)
    logger.warning(
        "Invalid route_preference value {!r}, falling back to 'auto'. Valid values: {}",
        raw,
        sorted(_VALID_ROUTE_PREFERENCES),
    )
    return "auto"


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
    "ModelRouteIdentity",
    "Route",
    "RoutePreference",
    "build_available_providers",
    "build_display_options",
    "build_model_route_identity",
    "canonical_key",
    "detect_route",
    "display_family_for",
    "display_model_name_for",
    "group_model_routes",
    "is_webapi_model_id",
    "parse_route_preference",
    "required_provider_for",
    "select_preferred_route",
    "validate_api_keys_for_models",
]
