# ADR 0036: GUI Compound Widget 分割方針

- **日付**: 2026-05-25
- **ステータス**: Accepted
- **関連 Issue**: #427 (ADR起票), #420 (実装: FilterSearchPanel)

## Context

`src/lorairo/gui/widgets/filter_search_panel.py` が **1,682 行・64 メソッド・5 サブシステム同居**の
God Widget に成長した。coverage 57% で未カバー帯 (476-1628) が広く、単一画面では到達困難な
条件分岐（お気に入りフィルタ保存・削除・同期検索フォールバック・pipeline error handler）に集中している。

同様の問題が将来の widget にも波及しないよう、**分割の基準・構造・シグナル流通・テスト戦略**を ADR として確定する。

既存パターン:
- Qt-Free Core Pattern (CLAUDE.md・ADR 0009): コアサービスは Qt 非依存
- Two-Tier Service Architecture (ADR 0001): GUI Services と Business Logic Services を分離

## Decision

### 1. 分割トリガー基準

以下のいずれかを満たした widget は分割対象とする:

| 条件 | 閾値 |
|---|---|
| ソース行数 | **500 行超** |
| 独立した責務の数 | **3 責務以上**の同居 |
| widget-private QRunnable クラスの数 | **2 個以上** |

「責務」の定義: 独立して有効化・無効化・テスト可能な UI 機能単位。
（例: タグオートコンプリート・お気に入りフィルタ管理・件数見積もり・Pipeline State Machine）

### 2. 構造パターン: Composition + Mediator

```
ParentWidget (mediator)
  ├── SubWidgetA (QWidget subclass, 独立 qtbot テスト可能)
  ├── SubWidgetB (QWidget subclass)
  └── SubWidgetC (QWidget subclass)
```

- **Parent は sub-widget を composition で保持**する (継承・mixin 禁止)
- **Sub-widget は parent を知らない**。sub-widget は自分のシグナルを emit するだけ
- **Parent が mediator**: sub-widget シグナルを受け取り、他の sub-widget や Service を呼ぶ

### 3. Signal/Slot 流通ルール

```
SubWidgetA.some_signal
    → ParentWidget._on_some_signal()   # mediator ハンドラ
        → SubWidgetB.update(...)       # 他 sub-widget 更新
        → service.do_something(...)    # service 呼び出し
```

- **Sub-widget 同士の直接接続禁止**: sub-widget は互いを参照しない
- **Service → Sub-widget**: Service シグナルは Parent 経由で sub-widget に届ける
- **Sub-widget → Parent**: `target_fixture` パターン相当の signal で状態を通知

### 4. QRunnable (バックグラウンドタスク) の置き場

| 種別 | 配置先 |
|---|---|
| 単一 sub-widget 専用 (他から使われない) | `src/lorairo/gui/widgets/<feature>/tasks.py` |
| 複数 widget・service から共用 | `src/lorairo/gui/workers/` |

Widget-private task は sub-widget と同じサブディレクトリに置き、`from .tasks import XxxTask` でインポートする。

### 5. テスト要件

- 各 sub-widget は **`qtbot` で親なしで単独インスタンス化可能**な構造とする
- Parent (mediator) のテストは sub-widget をモック注入して実施
- QRunnable task は Qt 非依存な場合は unit test として、Qt 依存は `@pytest.mark.gui` で実施

### 6. FilterSearchPanel の分割案 (#420 向け参考)

現状の 5 責務を以下のコンポーネントに切り出す:

| コンポーネント | 種別 | 責務 |
|---|---|---|
| `TagSuggestionWidget` | QWidget subclass | タグオートコンプリート + `_TagSuggestionTask` |
| `FavoriteFilterPanel` | QWidget subclass | お気に入りフィルタ保存・読込・削除 |
| `CountEstimateWidget` | QWidget subclass | デバウンス件数見積もり + `_CountEstimateTask` |
| `PipelineStateMachine` | Qt-Free class | 6 状態 Enum + 状態遷移ロジック |
| `FilterSearchPanel` (残存) | Mediator | 日付・解像度・レーティング UI + 上記 4 コンポーネントの協調 |

`PipelineStateMachine` は Qt 非依存クラスとして `services/` 相当の扱いでテストする。

### 7. ディレクトリ構成例

```
src/lorairo/gui/widgets/
├── filter_search/
│   ├── __init__.py
│   ├── tag_suggestion.py      # TagSuggestionWidget + tasks
│   ├── favorite_filter.py     # FavoriteFilterPanel
│   ├── count_estimate.py      # CountEstimateWidget + tasks
│   └── pipeline_state.py      # PipelineStateMachine (Qt-free)
└── filter_search_panel.py     # FilterSearchPanel (mediator、import compat)
```

## Rationale

**Mixin 案（却下）**: mixin は状態を共有しやすく、テスト時の分離が困難。
sub-widget ごとの独立インスタンス化が難しくなる。

**Controller 分離のみ案（却下）**: 非 Qt ロジックだけ分離しても、
QRunnable や Qt シグナルを含む UI 部分の肥大化は解消されない。

**Composition + Mediator 案（採用）**: 各 sub-widget が独立テスト可能で、
parent を変更しても sub-widget の test が壊れない。Qt-Free Core Pattern (ADR 0009) と整合する。

## Consequences

**良い点:**
- Sub-widget ごとに独立した unit/gui test が書ける → カバレッジ向上
- 責務が明確になり、機能追加・変更が局所化される
- `PipelineStateMachine` が Qt 非依存になり、unit test で完全検証可能

**悪い点:**
- Parent (mediator) のテストで複数 sub-widget のモックが必要になる
- 既存の `filter_search_panel.py` からの import を壊さないよう re-export が必要

**適用対象:**
- 即時: `FilterSearchPanel` (#420)
- 将来: 500行超になった任意の widget

## Related

- #420 (実装: FilterSearchPanel 分割)
- #416 (BDD テスト追加 — 分割後に本格追加)
- ADR 0001 (Two-Tier Service Architecture)
- ADR 0009 (Qt Decoupling Design — Qt-Free Core Pattern)
