"""アノテーターメタデータ型定義

Issue #225: `AnnotatorExtras` を独立モジュールに配置し、`annotator_adapter` と
`services/model_sync_service` の循環 import を回避する。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class AnnotatorExtras:
    """`AnnotatorInfo` に含まれない追加メタデータ。

    image-annotator-lib の `config_registry` から取得する。PydanticAI 直接モデル
    (config_registry 未登録) では全フィールドが None になる。

    ADR 0021 (LiteLLM 駆動 model registry) で取得経路が変わっても境界が
    `AnnotatorLibraryAdapter.get_model_extras()` に閉じる。
    """

    provider: str | None
    class_name: str | None
    api_model_id: str | None
    estimated_size_gb: float | None
    discontinued_at: datetime.datetime | None
    max_output_tokens: int | None
