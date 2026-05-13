"""Issue #241: model_route_service の単体テスト。

route 判定、canonical key、grouping、preference 選択、API key validation を
全数テストする。pure function helper のため Mock 不要、Model は SimpleNamespace で代用。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lorairo.services.model_route_service import (
    ModelRouteCandidate,
    build_available_providers,
    build_display_options,
    canonical_key,
    detect_route,
    group_model_routes,
    required_provider_for,
    select_preferred_route,
    validate_api_keys_for_models,
)


def _fake_model(
    litellm_model_id: str,
    name: str,
    provider: str | None,
    requires_api_key: bool = True,
    capabilities: list[str] | None = None,
) -> SimpleNamespace:
    """`Model` 互換の軽量 fake。

    schema.py L145 の ``capabilities`` は @property だが、SimpleNamespace 直接代入で
    duck typing 互換にできる (build_display_options は ``tuple(model.capabilities)`` で読む)。
    """
    return SimpleNamespace(
        litellm_model_id=litellm_model_id,
        name=name,
        provider=provider,
        requires_api_key=requires_api_key,
        capabilities=capabilities or [],
    )


@pytest.mark.unit
class TestDetectRoute:
    def test_openrouter_prefix_returns_openrouter(self) -> None:
        assert detect_route("openrouter/openai/gpt-4o") == "openrouter"

    def test_no_prefix_returns_direct(self) -> None:
        assert detect_route("openai/gpt-4o") == "direct"

    def test_bare_name_returns_direct(self) -> None:
        """ローカル ML モデル (slash 無し) は direct 扱い"""
        assert detect_route("wd-v1-4-tagger") == "direct"

    def test_empty_string_returns_direct(self) -> None:
        """defensive: 空文字は direct fallback"""
        assert detect_route("") == "direct"

    def test_openrouter_substring_in_middle_is_not_route(self) -> None:
        """prefix のみ判定するため、途中の `openrouter` 部分文字列は無関係"""
        assert detect_route("openai/openrouter-experimental") == "direct"


@pytest.mark.unit
class TestCanonicalKey:
    def test_openrouter_prefix_stripped(self) -> None:
        assert canonical_key("openrouter/anthropic/claude-3-5-sonnet") == "anthropic/claude-3-5-sonnet"

    def test_no_prefix_unchanged(self) -> None:
        assert canonical_key("openai/gpt-4o") == "openai/gpt-4o"

    def test_bare_name_unchanged(self) -> None:
        assert canonical_key("wd-v1-4-tagger") == "wd-v1-4-tagger"

    def test_idempotent(self) -> None:
        """canonical_key を 2 回適用しても同じ結果"""
        assert canonical_key(canonical_key("openrouter/openai/gpt-4o")) == "openai/gpt-4o"


@pytest.mark.unit
class TestRequiredProviderFor:
    def test_provider_hint_takes_priority(self) -> None:
        """hint があれば信頼する (migration 経由で name と provider が食い違うケース)"""
        assert required_provider_for("openai/gpt-4o", "openrouter") == "openrouter"

    def test_fallback_to_prefix_when_hint_none(self) -> None:
        assert required_provider_for("openrouter/openai/gpt-4o", None) == "openrouter"

    def test_fallback_to_prefix_when_hint_unknown(self) -> None:
        """`provider="unknown"` は fallback トリガー (=信頼できない)"""
        assert required_provider_for("openai/gpt-4o", "unknown") == "openai"

    def test_fallback_to_prefix_when_hint_empty(self) -> None:
        assert required_provider_for("openai/gpt-4o", "") == "openai"

    def test_gemini_alias_maps_to_google(self) -> None:
        """LiteLLM の `gemini/` prefix は Google API key 要求"""
        assert required_provider_for("gemini/gemini-pro-vision", None) == "google"

    def test_vertex_ai_alias_maps_to_google(self) -> None:
        assert required_provider_for("vertex_ai/gemini-pro", None) == "google"

    def test_bare_name_returns_local(self) -> None:
        """slash 無し = ローカル ML モデル"""
        assert required_provider_for("wd-v1-4-tagger", None) == "local"

    def test_hint_lowercased(self) -> None:
        """大文字 provider hint は lowercase 正規化"""
        assert required_provider_for("openai/gpt-4o", "OpenAI") == "openai"


@pytest.mark.unit
class TestBuildAvailableProviders:
    def test_returns_non_empty_keys_only(self) -> None:
        api_keys = {
            "openai": "sk-...",
            "anthropic": "",
            "google": "  ",
            "openrouter": "sk-or-...",
        }
        assert build_available_providers(api_keys) == {"openai", "openrouter"}

    def test_empty_dict_returns_empty_set(self) -> None:
        assert build_available_providers({}) == set()


@pytest.mark.unit
class TestGroupModelRoutes:
    def test_direct_only(self) -> None:
        m1 = _fake_model("openai/gpt-4o", "gpt-4o", "openai")
        result = group_model_routes([m1])
        assert "openai/gpt-4o" in result
        assert len(result["openai/gpt-4o"]) == 1
        assert result["openai/gpt-4o"][0].route == "direct"
        assert result["openai/gpt-4o"][0].required_provider == "openai"

    def test_openrouter_only(self) -> None:
        m1 = _fake_model("openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter")
        result = group_model_routes([m1])
        assert "openai/gpt-4o" in result
        assert result["openai/gpt-4o"][0].route == "openrouter"
        assert result["openai/gpt-4o"][0].required_provider == "openrouter"

    def test_both_routes_grouped_under_same_canonical_key(self) -> None:
        """Issue #241 核心ケース: direct と openrouter が同一 canonical key で grouping される"""
        m_direct = _fake_model("openai/gpt-4o", "gpt-4o", "openai")
        m_router = _fake_model("openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter")
        result = group_model_routes([m_direct, m_router])

        assert list(result.keys()) == ["openai/gpt-4o"]
        candidates = result["openai/gpt-4o"]
        assert len(candidates) == 2
        # direct -> openrouter の順にソートされる
        assert [c.route for c in candidates] == ["direct", "openrouter"]

    def test_migration_path_provider_hint_respected(self) -> None:
        """migration 経由で `name='openai/gpt-4o', provider='openrouter'` の行も
        ``provider`` hint で required_provider が openrouter になる。
        """
        m = _fake_model(
            "openrouter/openai/gpt-4o",
            "openai/gpt-4o",  # name が縮退している (migration 残骸)
            "openrouter",
        )
        result = group_model_routes([m])
        candidate = result["openai/gpt-4o"][0]
        assert candidate.required_provider == "openrouter"


@pytest.mark.unit
class TestSelectPreferredRoute:
    def _candidates(self, *configs: tuple[str, str, str]) -> list[ModelRouteCandidate]:
        return [
            ModelRouteCandidate(
                litellm_model_id=lid,
                route=r,
                required_provider=p,
                model=_fake_model(lid, "x", p),
            )
            for lid, r, p in configs
        ]

    def test_auto_picks_direct_when_available(self) -> None:
        cands = self._candidates(
            ("openai/gpt-4o", "direct", "openai"),
            ("openrouter/openai/gpt-4o", "openrouter", "openrouter"),
        )
        preferred = select_preferred_route(cands, {"openai", "openrouter"}, "auto")
        assert preferred is not None
        assert preferred.route == "direct"

    def test_auto_falls_back_to_openrouter_when_direct_unavailable(self) -> None:
        cands = self._candidates(
            ("openai/gpt-4o", "direct", "openai"),
            ("openrouter/openai/gpt-4o", "openrouter", "openrouter"),
        )
        preferred = select_preferred_route(cands, {"openrouter"}, "auto")
        assert preferred is not None
        assert preferred.route == "openrouter"

    def test_auto_returns_direct_disabled_when_neither_available(self) -> None:
        """両方 unavailable: direct を disabled 表示用に返す"""
        cands = self._candidates(
            ("openai/gpt-4o", "direct", "openai"),
            ("openrouter/openai/gpt-4o", "openrouter", "openrouter"),
        )
        preferred = select_preferred_route(cands, set(), "auto")
        assert preferred is not None
        assert preferred.route == "direct"

    def test_direct_pref_returns_none_if_no_direct_route(self) -> None:
        cands = self._candidates(
            ("openrouter/openai/gpt-4o", "openrouter", "openrouter"),
        )
        assert select_preferred_route(cands, {"openrouter"}, "direct") is None

    def test_openrouter_pref_returns_none_if_no_openrouter_route(self) -> None:
        cands = self._candidates(
            ("openai/gpt-4o", "direct", "openai"),
        )
        assert select_preferred_route(cands, {"openai"}, "openrouter") is None

    def test_empty_candidates_returns_none(self) -> None:
        assert select_preferred_route([], {"openai"}, "auto") is None


@pytest.mark.unit
class TestBuildDisplayOptions:
    def test_groups_direct_and_openrouter_into_one_option(self) -> None:
        """Issue #241 主要ケース: 同一 canonical_key の 2 route が 1 option に畳まれる"""
        m_direct = _fake_model("openai/gpt-4o", "gpt-4o", "openai", capabilities=["captions"])
        m_router = _fake_model(
            "openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter", capabilities=["captions"]
        )
        options = build_display_options([m_direct, m_router], {"openai", "openrouter"}, "auto")

        assert len(options) == 1
        opt = options[0]
        assert opt.preferred.route == "direct"
        assert len(opt.alternatives) == 1
        assert opt.alternatives[0].route == "openrouter"
        assert opt.alternatives[0].litellm_model_id == "openrouter/openai/gpt-4o"

    def test_capabilities_taken_from_preferred(self) -> None:
        m = _fake_model("openai/gpt-4o", "gpt-4o", "openai", capabilities=["captions", "tags"])
        options = build_display_options([m], {"openai"}, "auto")
        assert options[0].capabilities == ("captions", "tags")

    def test_none_available_treats_all_as_available(self) -> None:
        """available_providers=None は全 provider を available 扱い (テスト用 fallback)"""
        m = _fake_model("openai/gpt-4o", "gpt-4o", "openai")
        options = build_display_options([m], None, "auto")
        assert len(options) == 1
        assert options[0].preferred.route == "direct"

    def test_sorts_by_display_name(self) -> None:
        m1 = _fake_model("openai/zebra", "zebra", "openai")
        m2 = _fake_model("openai/alpha", "alpha", "openai")
        options = build_display_options([m1, m2], None, "auto")
        assert [o.display_name for o in options] == ["alpha", "zebra"]

    def test_all_candidates_property_returns_preferred_first(self) -> None:
        m_direct = _fake_model("openai/gpt-4o", "gpt-4o", "openai")
        m_router = _fake_model("openrouter/openai/gpt-4o", "openai/gpt-4o", "openrouter")
        options = build_display_options([m_direct, m_router], {"openai", "openrouter"}, "auto")
        opt = options[0]
        all_cands = opt.all_candidates
        assert all_cands[0] is opt.preferred
        assert all_cands[1:] == opt.alternatives


@pytest.mark.unit
class TestValidateApiKeysForModels:
    def test_all_keys_present_returns_empty(self) -> None:
        api_keys = {
            "openai": "sk-1",
            "anthropic": "sk-2",
            "google": "sk-3",
            "openrouter": "sk-or",
        }
        missing = validate_api_keys_for_models(
            ["openai/gpt-4o", "openrouter/anthropic/claude-3-5"], api_keys
        )
        assert missing == []

    def test_missing_openrouter_key_reports_unique_missing(self) -> None:
        """Issue #241 主要シナリオ: openai key のみ環境で openrouter モデル選択"""
        api_keys = {"openai": "sk", "openrouter": ""}
        missing = validate_api_keys_for_models(["openai/gpt-4o", "openrouter/openai/gpt-4o"], api_keys)
        assert missing == [("openrouter/openai/gpt-4o", "openrouter")]

    def test_local_models_skipped(self) -> None:
        """ローカル ML モデルは API key を要求しないため skip"""
        missing = validate_api_keys_for_models(["wd-v1-4-tagger"], {})
        assert missing == []

    def test_duplicates_deduplicated_in_missing_list(self) -> None:
        """同一 litellm_model_id を 2 回渡しても missing には 1 回のみ"""
        missing = validate_api_keys_for_models(
            ["openrouter/openai/gpt-4o", "openrouter/openai/gpt-4o"],
            {},
        )
        assert missing == [("openrouter/openai/gpt-4o", "openrouter")]

    def test_provider_hints_take_priority_over_prefix(self) -> None:
        """hints が prefix より優先される (migration 経由ケース)"""
        # litellm_id は `openai/gpt-4o` だが hint で openrouter required と判定
        missing = validate_api_keys_for_models(
            ["openai/gpt-4o"],
            {"openrouter": "sk"},
            provider_hints={"openai/gpt-4o": "openrouter"},
        )
        # openrouter key 有り -> 不足なし
        assert missing == []

    def test_empty_input_returns_empty(self) -> None:
        missing = validate_api_keys_for_models([], {"openai": "sk"})
        assert missing == []

    def test_gemini_prefix_requires_google_key(self) -> None:
        """`gemini/` prefix は google key を要求 (alias 解決)"""
        missing = validate_api_keys_for_models(["gemini/gemini-pro"], {})
        assert missing == [("gemini/gemini-pro", "google")]
