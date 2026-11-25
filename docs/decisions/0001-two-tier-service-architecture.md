---
type: ADR
title: Two-Tier Service Architecture
status: Accepted
timestamp: 2025-08-16
tags: []
---
# ADR 0001: Two-Tier Service Architecture

## Context

`SearchFilterService` が 1,182 行まで膨張し、GUI ロジック、ビジネスロジック、データアクセスが密結合していた。単一責任原則に違反した状態であり、テストと保守の双方で大きな負担が生じていた。

## Decision

GUI Services と Business Logic Services の 2 層アーキテクチャを導入する。

```
GUI Services Layer
  SearchFilterService (150行) — UI入力解析・ユーザー操作・エラー表示
        ↓ Dependency Injection
Business Logic Layer
  SearchCriteriaProcessor (300行) — 純粋なビジネスロジック・DBクエリ条件
  ModelFilterService (350行) — AIモデル管理・フィルタリング
        ↓
Data Layer
  ImageDatabaseManager — リポジトリパターン・DB操作
```

## Rationale

検討した代替案と却下理由は次のとおりである。

- **完全書き換え案(却下)**: 既存機能を破壊するリスクが高く、段階的な検証が難しい。
- **小サービス多数分割案(却下)**: サービス間の境界が曖昧になり、循環依存が発生するリスクがある。
- **モノリス内部構造改善案(却下)**: 根本的なアーキテクチャ上の課題を解決できない。

既存機能を維持しながら段階的に責務を抽出し、各段階を独立して検証できる本案を採用した。

## Consequences

- `SearchFilterService` の行数を 1,182 行から 150 行へ削減した(87% 削減)。
- ビジネスロジックを GUI への依存なしでテストできるようになった。
- 新しいフィルタ種別の追加を `SearchCriteriaProcessor` に局所化できる。
- 依存性注入(DI)パターンにより、各層を独立して発展させられる。

**実装ファイル:**

- `src/lorairo/services/search_criteria_processor.py`
- `src/lorairo/services/model_filter_service.py`
- `src/lorairo/gui/services/search_filter_service.py`
- `src/lorairo/gui/widgets/custom_range_slider.py`
