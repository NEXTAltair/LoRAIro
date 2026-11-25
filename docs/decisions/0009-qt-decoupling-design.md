---
type: ADR
title: Qt Decoupling Design
status: Accepted
timestamp: 2026-02-16
tags: []
---
# ADR 0009: Qt Decoupling Design

## Context

LoRAIro は従来 GUI 専用アプリケーションだったが、CLI ツールやサーバー環境での自動化(CI/CD やバッチ処理)に対応する必要が生じた。コアサービスの約 90% は Qt 非依存として設計できる一方、`favorite_filters` と `signal_manager` が Qt に依存していた。

## Decision

**Adapter パターンと DI コンテナ**を組み合わせ、Qt への直接依存を取り除く。

```python
# ServiceContainer の signal_manager プロパティ
@property
def signal_manager(self) -> SignalManagerServiceProtocol:
    if self._cli_mode:
        return NoOpSignalManager()  # CLI: Qt非依存
    return SignalManagerService()   # GUI: QObject + Signal
```

- `FavoriteFiltersService` は、API シグネチャを維持したまま `QSettings` ベースから JSON ベースへ自動で切り替える。
- 実行モードの切り替えは、環境変数 `LORAIRO_CLI_MODE` ひとつで制御する。

## Rationale

- **既存 GUI コードの修正が不要**: Adapter 層を挟むことで、既存コードとの後方互換性を完全に維持できる。
- **Protocol ベースの DI**: 呼び出し側が GUI か CLI かを意識せずに済むため、関心の分離を保てる。
- JSON 化に伴う初期化コストは無視できる水準である。

## Consequences

- CLI ツールが Qt をインストールしない環境でも動作できるようになった。
- テスト時に `LORAIRO_CLI_MODE=1` を設定すれば、Qt 非依存のテストを容易に実行できる。
- 新しいサービスを追加する際は、Qt への依存有無を意識した設計が求められる。
- `NoOpSignalManager` は Signal を無視するため、CLI 環境での非同期イベント処理は別途対応する必要がある。
