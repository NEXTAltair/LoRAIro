# ADR 0009: Qt Decoupling Design

- **日付**: 2026-02-16
- **ステータス**: Accepted

## Context

LoRAIro はGUI専用アプリケーションだったが、CLI ツール・サーバー環境での自動化対応（CI/CD, バッチ処理）が必要になった。コアサービスの ~90% は Qt 非依存で設計可能だが、`favorite_filters`, `signal_manager` が Qt に依存していた。

## Decision

**Adapter Pattern + DI Container** による Qt 依存除去:

```python
# ServiceContainer の signal_manager プロパティ
@property
def signal_manager(self) -> SignalManagerServiceProtocol:
    if self._cli_mode:
        return NoOpSignalManager()  # CLI: Qt非依存
    return SignalManagerService()   # GUI: QObject + Signal
```

- `FavoriteFiltersService`: QSettings ベース → JSON に自動切り替え（API シグネチャ維持）
- 環境切り替え: `LORAIRO_CLI_MODE` 環境変数 1つで制御

## Rationale

- **既存 GUI コード修正なし**: Adapter で後方互換性を完全維持
- **Protocol ベースの DI**: 呼び出し側が環境を意識しない（関心の分離）
- JSON 化による初期化コストは無視できるレベル

## Consequences

- CLI ツールが Qt インストール不要で動作可能
- テスト時に `LORAIRO_CLI_MODE=1` で Qt 非依存テストが容易
- 新サービス追加時は Qt 依存の有無を意識した設計が必要
- `NoOpSignalManager` は Signal を無視するため CLI での非同期イベントは別途対応が必要
