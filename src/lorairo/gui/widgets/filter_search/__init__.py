# src/lorairo/gui/widgets/filter_search/__init__.py
"""FilterSearchPanel を構成するサブコンポーネント (ADR 0036)。

このパッケージは `FilterSearchPanel` を以下の責務に分割した結果:

- `pipeline_state`: Qt 非依存の Pipeline State Machine
- `tag_suggestion`: タグオートコンプリート UI + 非同期タスク
- `favorite_filter`: お気に入りフィルタ UI
- `count_estimate`: 件数見積もり UI + 非同期タスク

`FilterSearchPanel` (mediator) はこれらを composition で保持し、
sub-widget 同士は直接接続せず Parent を経由してシグナルを流通させる
(ADR 0036 §3)。
"""

from .pipeline_state import PipelineState, PipelineStateMachine

__all__ = [
    "PipelineState",
    "PipelineStateMachine",
]
