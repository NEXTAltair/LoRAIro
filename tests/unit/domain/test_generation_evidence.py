"""AI 生成の判定条件 (ADR 0105 / 0107, Issue #1396)。

`ai generated` の自動付与は、この条件が True の画像だけに行う。誤判定を避けるため、
全ての (生成ツール, 解析状態) の組み合わせで結果を固定する。
"""

from __future__ import annotations

import pytest

from lorairo.domain.generation_metadata import (
    GenerationEvidence,
    GenerationMetadataStatus,
    is_ai_generation_evidence,
)

pytestmark = pytest.mark.unit

S = GenerationMetadataStatus


@pytest.mark.parametrize(
    ("tool", "status", "expected"),
    [
        # 生成ツールが特定できた形式だけを根拠にする
        ("sd_webui", S.PARSED, True),
        ("sd_webui", S.PARTIAL, True),
        ("comfyui", S.PARTIAL, True),
        ("comfyui", S.UNSUPPORTED, True),  # ノードグラフの判定だけで項目は未抽出
        # 生成ツールが特定できないものは、どの状態でも根拠にしない
        (None, S.PARSED, False),
        (None, S.PARTIAL, False),
        (None, S.UNSUPPORTED, False),  # parameters の汎用テキスト・カメラの UserComment
        (None, S.NO_METADATA, False),  # メタデータが無いことは非 AI 生成の証明でもない
        (None, S.FAILED, False),
        # 読み取りに失敗した結果は根拠にしない
        ("sd_webui", S.FAILED, False),
        ("sd_webui", S.NO_METADATA, False),
    ],
)
def test_ai_generation_evidence_matrix(
    tool: str | None, status: GenerationMetadataStatus, expected: bool
) -> None:
    assert is_ai_generation_evidence(tool, status) is expected
    assert GenerationEvidence(tool=tool, status=status).is_ai_generated is expected
