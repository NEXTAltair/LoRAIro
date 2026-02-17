"""AI アノテーションAPI。

AnnotatorLibraryAdapter をラップし、アノテーション機能を提供。

注: 本API実装は簡略化されており、実運用時には実装詳細が補完される予定。
"""

from lorairo.api.exceptions import (
    AnnotationFailedError,
    APIKeyNotConfiguredError,
)
from lorairo.api.types import AnnotationResult
from lorairo.services.service_container import ServiceContainer


def annotate_images(
    model_names: list[str],
    image_ids: list[int] | None = None,
) -> AnnotationResult:
    """画像にAIアノテーションを実行。

    Args:
        model_names: 使用するモデル名のリスト。
                    例: ['gpt-4o-mini', 'claude-opus']
        image_ids: アノテーション対象の画像ID。
                  未指定時は全画像が対象。

    Returns:
        AnnotationResult: アノテーション実行結果。

    Raises:
        APIKeyNotConfiguredError: 必要なAPIキーが設定されていない。
        AnnotationFailedError: アノテーション実行に失敗。

    使用例:
        >>> from lorairo.api import annotate_images
        >>>
        >>> result = annotate_images(['gpt-4o-mini'])
        >>> print(f"成功: {result.successful_annotations}件")
    """
    container = ServiceContainer()
    config_service = container.config_service

    # APIキー確認
    for model_name in model_names:
        if "gpt" in model_name.lower():
            if not config_service.get_setting("api", "openai_key"):
                raise APIKeyNotConfiguredError("openai")
        elif "claude" in model_name.lower():
            if not config_service.get_setting("api", "claude_key"):
                raise APIKeyNotConfiguredError("claude")
        elif "gemini" in model_name.lower():
            if not config_service.get_setting("api", "google_key"):
                raise APIKeyNotConfiguredError("google")

    try:
        # アノテーション実行
        # 注: 実装詳細は AnnotatorLibraryAdapter.annotate に委譲
        # 簡略化のため、スタブ実装として 0件成功を返す
        image_count = len(image_ids) if image_ids else 0

        return AnnotationResult(
            image_count=image_count,
            successful_annotations=0,
            failed_annotations=image_count,
            results=None,
        )

    except APIKeyNotConfiguredError:
        raise
    except Exception as e:
        raise AnnotationFailedError(
            model_names[0] if model_names else "unknown",
            len(image_ids) if image_ids else 0,
            str(e),
        ) from e
