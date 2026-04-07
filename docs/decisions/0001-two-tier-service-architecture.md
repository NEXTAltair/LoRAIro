# ADR 0001: Two-Tier Service Architecture

- **日付**: 2025-08-16
- **ステータス**: Accepted

## Context

`SearchFilterService` が 1,182 行に膨張し、GUI ロジック・ビジネスロジック・データアクセスが密結合していた。単一責任原則違反によりテスト困難・保守困難な状態。

## Decision

GUI Services と Business Logic Services の 2 層アーキテクチャを実装する。

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

- **完全書き換え案（却下）**: 既存機能破壊リスクが高く段階的検証が困難
- **小サービス多数分割案（却下）**: サービス境界が不明確・循環依存リスク
- **モノリス内部構造改善案（却下）**: 根本的なアーキテクチャ問題を解決できない

段階的な抽出アプローチで既存機能を保ちながら各段階を独立検証できる本案を選択。

## Consequences

- SearchFilterService: 1,182 → 150 行（87% 削減）
- ビジネスロジックが GUI 依存なしでテスト可能
- 新フィルタタイプの追加が SearchCriteriaProcessor に局所化
- DIパターンにより各層が独立して進化可能

**実装ファイル:**
- `src/lorairo/services/search_criteria_processor.py`
- `src/lorairo/services/model_filter_service.py`
- `src/lorairo/gui/services/search_filter_service.py`
- `src/lorairo/gui/widgets/custom_range_slider.py`
