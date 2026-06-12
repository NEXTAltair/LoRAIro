# tests/unit/services/test_model_registry_protocol.py

"""model_registry_protocol.py のユニットテスト

Issue #225: dict ヘルパー (`map_annotator_metadata_to_model_info`,
`_infer_capabilities_min`) を削除。Protocol と NullModelRegistry のみ残存。
"""

from unittest.mock import Mock, patch

import pytest

from lorairo.services.model_registry_protocol import (
    NullModelRegistry,
    local_ml_model_names,
    selection_includes_local_ml_model,
    selection_includes_webapi_model,
)


class TestNullModelRegistry:
    """NullModelRegistry のユニットテスト"""

    def test_get_available_models_returns_empty_list(self) -> None:
        registry = NullModelRegistry()
        assert registry.get_available_models() == []

    def test_get_available_models_logs_info(self) -> None:
        registry = NullModelRegistry()
        with patch("lorairo.services.model_registry_protocol.logger") as mock_logger:
            registry.get_available_models()
            mock_logger.info.assert_called_once()

    def test_get_available_models_with_metadata_returns_empty_list(self) -> None:
        registry = NullModelRegistry()
        assert registry.get_available_models_with_metadata() == []

    def test_get_available_models_with_metadata_logs_info(self) -> None:
        registry = NullModelRegistry()
        with patch("lorairo.services.model_registry_protocol.logger") as mock_logger:
            registry.get_available_models_with_metadata()
            mock_logger.info.assert_called_once()


class TestSelectionIncludesWebApiModel:
    """`selection_includes_webapi_model()` の単体テスト。

    ADR 0023 Phase 1.5 (Issue #42) / Codex P1 (PR #233 r3208397315):
    refusal 送信前 filter は WebAPI モデル選択時のみ適用すべきという contract を
    回帰テストで保証する。Codex P2 (PR #233 r3209342204) の Worker 移動に伴い、
    helper 自体は services/ 層 (Qt-free) に移設された。
    """

    @staticmethod
    def _model_info(name: str, requires_api_key: bool, litellm_model_id: str | None = None):
        """`ModelInfo` 互換 Mock。

        Issue #245 PR #246 review: lookup map のキーは
        `info.litellm_model_id or info.name` (registry key SSoT)。デフォルトでは
        Phase 1.10 の WebAPI 規約 (`name == litellm_model_id`) を再現するため
        `litellm_model_id` を `name` と同値にする。`name != litellm_model_id` の
        ケースを意図的にテストする場合は明示的に異なる値を渡す。
        """
        info = Mock()
        info.name = name
        info.requires_api_key = requires_api_key
        info.litellm_model_id = litellm_model_id if litellm_model_id is not None else name
        return info

    def _registry(self, models):
        registry = Mock()
        registry.get_available_models.return_value = list(models)
        return registry

    def test_returns_true_when_webapi_model_selected(self) -> None:
        """少なくとも 1 つ requires_api_key=True のモデルが選択されていれば True。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["openai/gpt-4o"], registry) is True

    def test_returns_false_when_only_local_models_selected(self) -> None:
        """ローカルモデル単独選択時は False (Codex P1 回帰防止: filter 適用しない)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
                self._model_info("aesthetic-predictor", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["wd-v1-4-tagger", "aesthetic-predictor"], registry) is False

    def test_returns_true_with_mixed_selection(self) -> None:
        """ローカル + WebAPI の混在選択時は True (1 つでも WebAPI なら filter 適用)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", requires_api_key=True),
                self._model_info("wd-v1-4-tagger", requires_api_key=False),
            ]
        )
        assert selection_includes_webapi_model(["wd-v1-4-tagger", "openai/gpt-4o"], registry) is True

    def test_returns_false_for_unknown_model_name(self) -> None:
        """registry に未登録のモデル名は WebAPI 扱いしない (defensive default)。"""
        registry = self._registry([self._model_info("openai/gpt-4o", requires_api_key=True)])
        assert selection_includes_webapi_model(["unknown-model"], registry) is False

    def test_returns_false_for_empty_selection(self) -> None:
        """空リストは False (early return、registry を引かない)。"""
        registry = self._registry([self._model_info("openai/gpt-4o", requires_api_key=True)])
        assert selection_includes_webapi_model([], registry) is False
        registry.get_available_models.assert_not_called()

    def test_propagates_registry_exception(self) -> None:
        """registry が例外を raise した場合は呼び出し元で吸収する契約。

        本 helper は pure な分類関数で、例外吸収は caller (`AnnotationWorker._apply_refusal_prefilter`)
        の責務 (Codex P2: PR #233 r3208793528)。
        """
        registry = Mock()
        registry.get_available_models.side_effect = RuntimeError("registry unavailable")
        with pytest.raises(RuntimeError, match="registry unavailable"):
            selection_includes_webapi_model(["openai/gpt-4o"], registry)

    def test_lookup_uses_litellm_model_id_not_name(self) -> None:
        """Issue #245 PR #246 review (P1): lookup map のキーは `litellm_model_id`。

        `info.name != info.litellm_model_id` のケースで、caller (`litellm_model_id`
        を渡す側) と registry 内の info を正しく結びつけられることを保証する。
        旧実装 (`{info.name: info}` でキー化) では `litellm_model_id` で引いて
        miss し、WebAPI モデルが検出されず refusal filter が誤って skip されていた。
        """
        # `name` は表示用短縮形、`litellm_model_id` が registry key SSoT
        webapi_info = self._model_info(
            name="gpt-4o",
            requires_api_key=True,
            litellm_model_id="openai/gpt-4o",
        )
        registry = self._registry([webapi_info])

        # 呼び出し側は litellm_model_id を渡す (新 contract)
        assert selection_includes_webapi_model(["openai/gpt-4o"], registry) is True
        # 旧 `name` 経由では引けない (これは正しい振る舞い: SSoT は litellm_model_id)
        assert selection_includes_webapi_model(["gpt-4o"], registry) is False

    def test_lookup_falls_back_to_name_when_litellm_id_is_none(self) -> None:
        """ローカル ML モデルのように `info.litellm_model_id is None` の場合は
        `info.name` を fallback キーとして使う。`Model.litellm_model_id` 側は
        Phase 1.11 の `info.litellm_model_id or info.name` 規約で bare 名が入る。
        """
        local_info = self._model_info(
            name="wd-v1-4-tagger",
            requires_api_key=False,
            litellm_model_id=None,
        )
        registry = self._registry([local_info])
        # ローカルなので requires_api_key=False で False を返すが、lookup 自体は hit する
        # (= info が available に居る) ことを registry mock call で間接確認
        assert selection_includes_webapi_model(["wd-v1-4-tagger"], registry) is False
        registry.get_available_models.assert_called_once()


class TestSelectionIncludesLocalMlModel:
    """`selection_includes_local_ml_model()` の単体テスト (ADR 0066 §6)。

    ローカル GPU 推論ジョブの直列キュー判定に使う pure helper。
    provider が空文字または "local" のモデルをローカル ML として検出する。
    """

    @staticmethod
    def _model_info(name: str, provider: str, litellm_model_id: str | None = None):
        """`ModelInfo` 互換 Mock (lookup キーは litellm_model_id with name fallback)。"""
        info = Mock()
        info.name = name
        info.provider = provider
        info.litellm_model_id = litellm_model_id
        return info

    def _registry(self, models):
        registry = Mock()
        registry.get_available_models.return_value = list(models)
        return registry

    def test_returns_true_for_local_provider(self) -> None:
        """provider="local" のモデル選択時は True (GPU 直列化対象)。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert selection_includes_local_ml_model(["wd-v1-4-tagger"], registry) is True

    def test_returns_true_for_empty_provider(self) -> None:
        """provider が空文字のモデルもローカル ML として扱う (ADR 0066 §6)。"""
        registry = self._registry([self._model_info("aesthetic-predictor", provider="")])
        assert selection_includes_local_ml_model(["aesthetic-predictor"], registry) is True

    def test_returns_false_for_api_only_selection(self) -> None:
        """API 系のみの選択は False (並列許容)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", provider="openai", litellm_model_id="openai/gpt-4o"),
                self._model_info("wd-v1-4-tagger", provider="local"),
            ]
        )
        assert selection_includes_local_ml_model(["openai/gpt-4o"], registry) is False

    def test_returns_true_with_mixed_selection(self) -> None:
        """ローカル + API の混在選択は True (1 つでもローカルなら直列化)。"""
        registry = self._registry(
            [
                self._model_info("openai/gpt-4o", provider="openai", litellm_model_id="openai/gpt-4o"),
                self._model_info("wd-v1-4-tagger", provider="local"),
            ]
        )
        assert selection_includes_local_ml_model(["openai/gpt-4o", "wd-v1-4-tagger"], registry) is True

    def test_returns_false_for_unknown_model_name(self) -> None:
        """registry 未登録のモデルはローカル扱いしない (実行経路に乗らないため)。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert selection_includes_local_ml_model(["unknown-model"], registry) is False

    def test_returns_false_for_empty_selection(self) -> None:
        """空リストは False (early return、registry を引かない)。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert selection_includes_local_ml_model([], registry) is False
        registry.get_available_models.assert_not_called()

    def test_returns_false_for_unknown_provider(self) -> None:
        """provider="unknown" はローカル ML ではない (API フォールバック表記)。"""
        registry = self._registry([self._model_info("mystery-model", provider="unknown")])
        assert selection_includes_local_ml_model(["mystery-model"], registry) is False

    def test_lookup_falls_back_to_name_when_litellm_id_is_none(self) -> None:
        """ローカル ML の `litellm_model_id is None` は bare 名 fallback で hit する。"""
        registry = self._registry(
            [self._model_info("wd-v1-4-tagger", provider="local", litellm_model_id=None)]
        )
        assert selection_includes_local_ml_model(["wd-v1-4-tagger"], registry) is True


class TestLocalMlModelNames:
    """`local_ml_model_names()` の単体テスト (Issue #754)。

    model_install ジョブ対象の検出に使う pure helper。選択順を保持し、
    ローカル ML モデルの `ModelInfo.name` (= iam-lib モデル名) を返す。
    """

    @staticmethod
    def _model_info(name: str, provider: str, litellm_model_id: str | None = None):
        info = Mock()
        info.name = name
        info.provider = provider
        info.litellm_model_id = litellm_model_id
        return info

    def _registry(self, models):
        registry = Mock()
        registry.get_available_models.return_value = list(models)
        return registry

    def test_returns_local_models_in_selection_order(self) -> None:
        """選択順を保持してローカル ML モデル名のみを返す。"""
        registry = self._registry(
            [
                self._model_info("wd-v1-4-tagger", provider="local"),
                self._model_info("aesthetic-predictor", provider=""),
                self._model_info("openai/gpt-4o", provider="openai", litellm_model_id="openai/gpt-4o"),
            ]
        )
        names = local_ml_model_names(["openai/gpt-4o", "aesthetic-predictor", "wd-v1-4-tagger"], registry)
        assert names == ["aesthetic-predictor", "wd-v1-4-tagger"]

    def test_deduplicates_names(self) -> None:
        """重複選択でもモデル名は一意に返す。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert local_ml_model_names(["wd-v1-4-tagger", "wd-v1-4-tagger"], registry) == ["wd-v1-4-tagger"]

    def test_unknown_ids_are_not_local(self) -> None:
        """registry 未登録のモデルはローカル扱いしない。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert local_ml_model_names(["unknown-model"], registry) == []

    def test_empty_selection_returns_empty_without_registry_call(self) -> None:
        """空リストは early return で registry を引かない。"""
        registry = self._registry([self._model_info("wd-v1-4-tagger", provider="local")])
        assert local_ml_model_names([], registry) == []
        registry.get_available_models.assert_not_called()
