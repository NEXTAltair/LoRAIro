---
type: ADR
title: GUI Compound Widget 分割方針
status: Accepted
timestamp: 2026-05-25
tags: []
---
# ADR 0036: GUI Compound Widget 分割方針

- **関連 Issue**: #427(ADR 起票)、#420(実装:`FilterSearchPanel`)

## Context

`src/lorairo/gui/widgets/filter_search_panel.py` は、**1,682 行・64 メソッド・5 つのサブシステムが同居する巨大ウィジェット**へと肥大化した。テストカバレッジは 57% にとどまり、476 行目から 1628 行目にかけて広い未カバー帯が存在する。未カバー箇所は、単一画面からは到達しにくい条件分岐(お気に入りフィルタの保存・削除、同期検索フォールバック、パイプラインのエラーハンドラなど)に集中している。

同様の肥大化が将来のウィジェットへ波及するのを防ぐため、**分割の基準、構造、シグナル流通、テスト戦略**を本 ADR として確定する。

本方針は、以下の既存パターンと整合させる。

- Qt-Free Core Pattern(`CLAUDE.md`・ADR 0009):コアサービスは Qt に依存しない。
- Two-Tier Service Architecture(ADR 0001):GUI サービスとビジネスロジックサービスを分離する。

## Decision

### 1. 分割トリガー基準

以下のいずれかの条件を満たしたウィジェットは、分割対象とする。

| 条件 | 閾値 |
|---|---|
| ソース行数 | **500 行超** |
| 独立した責務の数 | **3 責務以上**の同居 |
| ウィジェット専用の `QRunnable` クラスの数 | **2 個以上** |

ここでの「責務」とは、独立して有効化・無効化・テストが可能な UI 機能単位を指す(例:タグオートコンプリート、お気に入りフィルタ管理、件数見積もり、Pipeline State Machine)。

### 2. 構造パターン:Composition + Mediator

複合ウィジェットは、コンポジションとメディエーターの組み合わせで構成する。

```
ParentWidget (mediator)
  ├── SubWidgetA (QWidget subclass, 独立 qtbot テスト可能)
  ├── SubWidgetB (QWidget subclass)
  └── SubWidgetC (QWidget subclass)
```

- **親ウィジェットはサブウィジェットをコンポジションで保持する**。継承や Mixin による合成は禁止する。
- **サブウィジェットは親ウィジェットを知らない**。サブウィジェットは自身のシグナルを emit するだけに徹する。
- **親ウィジェットがメディエーターを担う**。サブウィジェットのシグナルを受け取り、他のサブウィジェットの更新やサービス呼び出しを仲介する。

### 3. Signal/Slot の流通ルール

シグナルとスロットの接続経路は、次のように親ウィジェットを経由させる。

```
SubWidgetA.some_signal
    → ParentWidget._on_some_signal()   # mediator ハンドラ
        → SubWidgetB.update(...)       # 他 sub-widget 更新
        → service.do_something(...)    # service 呼び出し
```

- **サブウィジェット同士の直接接続は禁止する**。サブウィジェットは互いを参照しない。
- **Service からサブウィジェットへの通知**:サービスのシグナルは親ウィジェットを経由してサブウィジェットへ届ける。
- **サブウィジェットから親ウィジェットへの通知**:`target_fixture` パターンに相当するシグナルを用いて状態を通知する。

### 4. `QRunnable`(バックグラウンドタスク)の配置先

バックグラウンドタスクは、利用範囲に応じて配置先を分ける。

| 種別 | 配置先 |
|---|---|
| 単一サブウィジェット専用(他から使われない) | `src/lorairo/gui/widgets/<feature>/tasks.py` |
| 複数ウィジェット・サービスから共用 | `src/lorairo/gui/workers/` |

ウィジェット専用のタスクは、サブウィジェットと同じサブディレクトリに配置し、`from .tasks import XxxTask` としてインポートする。

### 5. テスト要件

- 各サブウィジェットは、**親ウィジェットなしで `qtbot` から単独インスタンス化できる**構造にする。
- 親ウィジェット(メディエーター)のテストは、サブウィジェットをモック注入して実施する。
- `QRunnable` タスクは、Qt に依存しない場合はユニットテストとして、Qt に依存する場合は `@pytest.mark.gui` を付与してテストする。

### 6. `FilterSearchPanel` の分割案(#420 向け参考)

現状の 5 つの責務を、以下のコンポーネントへ切り出す。

| コンポーネント | 種別 | 責務 |
|---|---|---|
| `TagSuggestionWidget` | `QWidget` サブクラス | タグオートコンプリートと `_TagSuggestionTask` |
| `FavoriteFilterPanel` | `QWidget` サブクラス | お気に入りフィルタの保存・読込・削除 |
| `CountEstimateWidget` | `QWidget` サブクラス | デバウンス付き件数見積もりと `_CountEstimateTask` |
| `PipelineStateMachine` | Qt 非依存クラス | 6 状態の Enum と状態遷移ロジック |
| `FilterSearchPanel`(残存) | メディエーター | 日付・解像度・レーティング UI と上記 4 コンポーネントの協調 |

`PipelineStateMachine` は Qt 非依存のクラスとして切り出し、`services/` 相当の扱いでテストする。

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

以下の 3 案を比較検討した。

- **Mixin 案(却下)**:Mixin はクラス間で状態を共有しやすく、テスト時の分離が困難になる。サブウィジェットごとの独立したインスタンス化も難しくなる。
- **Controller 分離のみ案(却下)**:非 Qt ロジックだけを分離しても、`QRunnable` や Qt シグナルを含む UI 部分の肥大化は解消されない。
- **Composition + Mediator 案(採用)**:各サブウィジェットを独立してテストでき、親ウィジェットを変更してもサブウィジェットのテストが壊れにくい。Qt-Free Core Pattern(ADR 0009)とも整合する。

## Consequences

### 良い点

- サブウィジェットごとに独立したユニットテストや GUI テストを書けるようになり、カバレッジが向上する。
- 責務が明確になり、機能追加や変更の影響範囲が局所化される。
- `PipelineStateMachine` が Qt 非依存となり、ユニットテストで完全に検証できる。

### 悪い点

- 親ウィジェット(メディエーター)のテストで、複数のサブウィジェットをモック化する必要が生じる。
- 既存の `filter_search_panel.py` からのインポート互換を保つため、再エクスポートが必要になる。

### 適用対象

- 即時適用:`FilterSearchPanel`(#420)
- 将来適用:500 行を超えた任意のウィジェット

## Related

- #420(実装:`FilterSearchPanel` の分割)
- #416(BDD テスト追加 — 分割後に本格追加)
- ADR 0001(Two-Tier Service Architecture)
- ADR 0009(Qt Decoupling Design — Qt-Free Core Pattern)
