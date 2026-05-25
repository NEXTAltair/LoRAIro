"""AnnotatorLibraryAdapter model registry tests."""

from unittest.mock import MagicMock, patch
from PIL import Image

import pytest
from image_annotator_lib import AnnotatorInfo
from image_annotator_lib.core.types import TaskCapability

from lorairo.annotations.annotator_adapter import AnnotatorLibraryAdapter


def _make_info(
    name: str,
    *,
    is_api: bool,
    model_type: str = "vision",
    capabilities: set[TaskCapability] | None = None,
    provider: str | None = None,
    estimated_size_gb: float | None = None,
    litellm_model_id: str | None = None,
) -> AnnotatorInfo:
    return AnnotatorInfo(
        name=name,
        model_type=model_type,  # type: ignore[arg-type]
        capabilities=frozenset(capabilities or {TaskCapability.TAGS}),
        is_local=not is_api,
        is_api=is_api,
        device=None if is_api else "cuda",
        provider=provider,
        estimated_size_gb=estimated_size_gb,
        litellm_model_id=litellm_model_id,
    )


@pytest.mark.unit
def test_refresh_available_models_returns_discovered_models() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        return_value={"models": ["openai/gpt-4.1-mini"], "metadata": {}},
    ) as mock_discover:
        result = adapter.refresh_available_models()

    assert result == ["openai/gpt-4.1-mini"]
    mock_discover.assert_called_once_with()


@pytest.mark.unit
def test_refresh_available_models_raises_on_discovery_error() -> None:
    """ADR 0023 Phase 1: 旧 API の `{"error": ...}` 戻り値経路は廃止された。

    新 `discover_available_vision_models()` は例外を内部で catch せず raise するため、
    adapter の `except Exception:` で受け再 raise されることを検証する。
    """
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.discover_available_vision_models",
        side_effect=RuntimeError("network unavailable"),
    ):
        with pytest.raises(RuntimeError, match="network unavailable"):
            adapter.refresh_available_models()


@pytest.mark.unit
def test_list_available_models_switches_active_and_all() -> None:
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with (
        patch("lorairo.annotations.annotator_adapter.get_available_models", return_value=["active"]),
        patch("lorairo.annotations.annotator_adapter.list_all_models", return_value=["active", "old"]),
    ):
        assert adapter.list_available_models() == ["active"]
        assert adapter.list_available_models(include_deprecated=True) == ["active", "old"]


@pytest.mark.unit
def test_list_annotator_info_passes_through_library_result() -> None:
    """adapter.list_annotator_info() がライブラリ戻り値をそのまま返すことを検証する (Issue #220)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info("wd-v1-4-tagger", is_api=False, model_type="tagger"),
        _make_info("gpt-4o", is_api=True, model_type="vision"),
    ]

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        return_value=fake_infos,
    ) as mock_lib:
        result = adapter.list_annotator_info()

    assert result == fake_infos
    mock_lib.assert_called_once_with()


@pytest.mark.unit
def test_list_annotator_info_propagates_library_exception() -> None:
    """ライブラリ例外は呼び出し元に伝播することを検証する (Issue #220)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        side_effect=RuntimeError("registry not initialized"),
    ):
        with pytest.raises(RuntimeError, match="registry not initialized"):
            adapter.list_annotator_info()


# ---- Issue #225 follow-up: get_available_models のテスト ----


@pytest.mark.unit
def test_get_available_models_builds_model_info_with_provider() -> None:
    """登録済みモデルは AnnotatorInfo.provider から ModelInfo を組み立てる (Phase 2)"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "wd-v1-4-tagger",
            is_api=False,
            model_type="tagger",
            capabilities={TaskCapability.TAGS},
            provider="smilingwolf",
            estimated_size_gb=1.2,
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    info = models[0]
    assert info.name == "wd-v1-4-tagger"
    assert info.provider == "smilingwolf"
    assert info.capabilities == ["tags"]
    assert info.requires_api_key is False
    assert info.estimated_size_gb == 1.2


@pytest.mark.unit
def test_get_available_models_unknown_provider_falls_back_to_unknown() -> None:
    """provider が未設定の API モデルは 'unknown' にフォールバック"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "google/gemini-2.5-pro",
            is_api=True,
            model_type="vision",
            capabilities={TaskCapability.TAGS, TaskCapability.CAPTIONS},
            # provider=None (未設定) → "unknown" にフォールバック
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    assert models[0].provider == "unknown"
    assert models[0].requires_api_key is True
    assert set(models[0].capabilities) == {"tags", "captions"}


@pytest.mark.unit
def test_get_available_models_with_metadata_alias() -> None:
    """get_available_models_with_metadata は get_available_models と同じ結果を返す"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=[]):
        assert adapter.get_available_models_with_metadata() == adapter.get_available_models()


# ---- Issue #366 regression: TaskCapability.RATINGS mapping ----


@pytest.mark.unit
def test_capability_values_includes_ratings() -> None:
    """`_CAPABILITY_VALUES` に `TaskCapability.RATINGS` mapping が存在することを保証する。

    Issue #366 回帰防止: ratings capability を宣言するモデル (canonical rater 等) で
    `_to_model_info()` が KeyError を投げ、`get_available_models()` が落ちて
    annotation 全体が degraded mode に入る事象を防ぐ。
    """
    from lorairo.annotations.annotator_adapter import _CAPABILITY_VALUES

    assert _CAPABILITY_VALUES[TaskCapability.RATINGS] == "ratings"


@pytest.mark.unit
def test_get_available_models_includes_ratings_capability() -> None:
    """ratings capability を含む AnnotatorInfo が KeyError なく ModelInfo へ変換される。

    Issue #366 回帰防止: `AnnotatorInfo.capabilities = {RATINGS, TAGS}` の
    フィクスチャを与え、`get_available_models()` が例外を出さず
    `ModelInfo.capabilities` に `"ratings"` を含むことを assert する。
    """
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "wd-rating-v3",
            is_api=False,
            model_type="tagger",
            capabilities={TaskCapability.RATINGS, TaskCapability.TAGS},
            provider="smilingwolf",
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    assert set(models[0].capabilities) == {"ratings", "tags"}


# ---- _to_model_info: provider=None の local モデル → "local" フォールバック ----


@pytest.mark.unit
def test_to_model_info_local_model_without_provider_falls_back_to_local() -> None:
    """provider が未設定のローカルモデルは 'local' にフォールバックする。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    fake_infos = [
        _make_info(
            "some-local-tagger",
            is_api=False,
            model_type="tagger",
            capabilities={TaskCapability.TAGS},
            # provider=None (未設定) + is_api=False → "local" にフォールバック
        )
    ]

    with patch("lorairo.annotations.annotator_adapter.list_annotator_info", return_value=fake_infos):
        models = adapter.get_available_models()

    assert len(models) == 1
    assert models[0].provider == "local"
    assert models[0].requires_api_key is False


# ---- list_annotator_info: Exception → エラーログ + 再 raise ----


@pytest.mark.unit
def test_list_annotator_info_logs_error_and_reraises_exception() -> None:
    """list_annotator_info() が Exception を raise すると re-raise されることを確認する。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.list_annotator_info",
        side_effect=ValueError("registry corrupt"),
    ):
        with pytest.raises(ValueError, match="registry corrupt"):
            adapter.list_annotator_info()


# ---- is_model_deprecated ----


@pytest.mark.unit
def test_is_model_deprecated_returns_true_for_deprecated_model() -> None:
    """is_model_deprecated() が deprecated なモデルで True を返すことを確認する。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.is_model_deprecated",
        return_value=True,
    ):
        assert adapter.is_model_deprecated("old-model-v1") is True


@pytest.mark.unit
def test_is_model_deprecated_returns_false_for_active_model() -> None:
    """is_model_deprecated() がアクティブなモデルで False を返すことを確認する。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())

    with patch(
        "lorairo.annotations.annotator_adapter.is_model_deprecated",
        return_value=False,
    ):
        assert adapter.is_model_deprecated("active-model") is False


# ---- get_adapter_info ----


@pytest.mark.unit
def test_get_adapter_info_returns_expected_fields() -> None:
    """get_adapter_info() が必要なフィールドを含む辞書を返すことを確認する。"""
    mock_config = MagicMock()
    type(mock_config).__name__ = "ConfigurationService"
    adapter = AnnotatorLibraryAdapter(mock_config)

    info = adapter.get_adapter_info()

    assert info["adapter_type"] == "AnnotatorLibraryAdapter"
    assert info["library"] == "image-annotator-lib"
    assert info["mode"] == "production"


# ---- _mask_key ----


@pytest.mark.unit
def test_mask_key_returns_asterisks_for_short_key() -> None:
    """_mask_key() が8文字未満のキーで '***' を返すことを確認する。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    assert adapter._mask_key("short") == "***"
    assert adapter._mask_key("") == "***"


@pytest.mark.unit
def test_mask_key_returns_masked_string_for_long_key() -> None:
    """_mask_key() が8文字以上のキーで先頭4文字+***+末尾4文字形式を返すことを確認する。"""
    adapter = AnnotatorLibraryAdapter(MagicMock())
    result = adapter._mask_key("sk-abcdef1234567890")
    assert result == "sk-a***7890"


# ---- _prepare_api_keys ----


@pytest.mark.unit
def test_prepare_api_keys_excludes_empty_keys() -> None:
    """_prepare_api_keys() が空文字列のキーを除外することを確認する。"""
    mock_config = MagicMock()
    mock_config.get_setting.side_effect = lambda section, key, default="": {
        ("api", "openai_key", ""): "sk-validkey1234",
        ("api", "claude_key", ""): "",
        ("api", "google_key", ""): "   ",  # 空白のみ → 除外
        ("api", "openrouter_key", ""): "",
    }.get((section, key, default), default)

    adapter = AnnotatorLibraryAdapter(mock_config)
    api_keys = adapter._prepare_api_keys()

    assert "openai" in api_keys
    assert api_keys["openai"] == "sk-validkey1234"
    assert "anthropic" not in api_keys
    assert "google" not in api_keys
    assert "openrouter" not in api_keys


@pytest.mark.unit
def test_prepare_api_keys_returns_empty_dict_when_no_keys_configured() -> None:
    """全APIキーが未設定の場合 _prepare_api_keys() が空辞書を返すことを確認する。"""
    mock_config = MagicMock()
    mock_config.get_setting.return_value = ""

    adapter = AnnotatorLibraryAdapter(mock_config)
    api_keys = adapter._prepare_api_keys()

    assert api_keys == {}


# ---- annotate ----


@pytest.mark.unit
def test_annotate_calls_library_annotate_with_correct_args() -> None:
    """annotate() が image-annotator-lib の annotate() を正しい引数で呼ぶことを確認する。

    annotator_adapter.py の annotate() メソッドは `from image_annotator_lib import annotate`
    をメソッド内でレイジーインポートするため、sys.modules の image_annotator_lib モジュールの
    annotate 属性をパッチする。
    """
    import sys

    mock_config = MagicMock()
    mock_config.get_setting.return_value = ""
    adapter = AnnotatorLibraryAdapter(mock_config)

    fake_image = MagicMock(spec=Image.Image)
    expected_result = {"hash001": {"tags": ["dog"]}}

    mock_lib_annotate = MagicMock(return_value=expected_result)
    original_annotate = sys.modules["image_annotator_lib"].annotate
    sys.modules["image_annotator_lib"].annotate = mock_lib_annotate
    try:
        result = adapter.annotate(
            images=[fake_image],
            litellm_model_ids=["openai/gpt-4o"],
            phash_list=["hash001"],
        )
    finally:
        sys.modules["image_annotator_lib"].annotate = original_annotate

    assert result == expected_result
    mock_lib_annotate.assert_called_once_with(
        images_list=[fake_image],
        model_name_list=["openai/gpt-4o"],
        phash_list=["hash001"],
        api_keys={},
    )


@pytest.mark.unit
def test_annotate_reraises_exception_from_library() -> None:
    """annotate() がライブラリ例外を re-raise することを確認する。"""
    import sys

    mock_config = MagicMock()
    mock_config.get_setting.return_value = ""
    adapter = AnnotatorLibraryAdapter(mock_config)

    original_annotate = sys.modules["image_annotator_lib"].annotate
    sys.modules["image_annotator_lib"].annotate = MagicMock(side_effect=RuntimeError("inference failed"))
    try:
        with pytest.raises(RuntimeError, match="inference failed"):
            adapter.annotate(images=[], litellm_model_ids=["some-model"])
    finally:
        sys.modules["image_annotator_lib"].annotate = original_annotate
