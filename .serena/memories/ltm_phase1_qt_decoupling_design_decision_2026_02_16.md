# OpenClaw LTM: Phase 1 Qt依存除去 設計決定

## 設計タイトル
**Qt-Free Core Pattern: ServiceContainer 環境自動切り替え設計**

## 概要
LoRAIro のコア機能（favorite_filters, signal_manager）から Qt 依存を除去し、Adapter Pattern + DI Container により GUI/CLI 環境を透過的に切り替える設計。

## 問題背景

### 初期状態
- LoRAIro はGUI専用アプリケーション
- コア機能の ~90% は Qt非依存で設計可能
- しかし、外部インターフェースがないためサーバー環境での自動化不可

### 要件
- CLI ツール群による自動化対応（CI/CD, バッチ処理）
- サーバー環境での無人運用対応
- 既存 GUI の機能破壊なし

## 採用した設計パターン

### 1. Adapter Pattern による後方互換性確保

```python
# 既存（GUI用）
from .favorite_filters_service import FavoriteFiltersService
service = FavoriteFiltersService()  # QSettings ベースから JSON に自動切り替え

# 呼び出し側の修正不要！
```

**メリット**:
- 既存 GUI コード修正なし
- API シグネチャ 100% 維持
- 移行コスト最小化

**デメリット（なし）**: 
- JSON 化による初期化コストは無視できるレベル

### 2. Protocol-Based DI による環境自動切り替え

```python
# ServiceContainer の signal_manager プロパティ
@property
def signal_manager(self) -> SignalManagerServiceProtocol:
    if self._signal_manager is None:
        if self._cli_mode:
            # CLI環境: Qt非依存
            self._signal_manager = NoOpSignalManager()
        else:
            # GUI環境: QObject + Signal
            self._signal_manager = SignalManagerService()
    return self._signal_manager
```

**メリット**:
- 環境変数 1つで切り替え（`LORAIRO_CLI_MODE`）
- 呼び出し側は環境を意識しない（関心の分離）
- テスト時の環境別テストが容易

**技術的背景**:
- `SignalManagerServiceProtocol` (Protocol) で interface 定義
- `SignalManagerService` (QObject継承)
- `NoOpSignalManager` (Pure Python)
- いずれも Protocol 準拠 → DI で透過的に選択可能

### 3. NoOp パターンによる Qt 依存完全排除

```python
class NoOpSignalManager:
    """CLI用 No-Operation Signal Manager"""
    def connect_widget_signals(self, widget, signal_mapping):
        logger.debug("NoOp: connect_widget_signals called")
        return True  # 常に成功（副作用なし）
```

**メリット**:
- PySide6 import なし
- Qt library に依存しない pure Python 実装
- ロギングで操作追跡可能（デバッグ対応）

**教訓**:
- CLI 環境では Signal 処理が不要 → NoOp で十分
- ただし Protocol 準拠で既存コード互換性保持

## 検討した代替案と却下理由

### 代替案 1: Protocol-Based 継承（すべてに Protocol を強制）

**概要**: 既存 `FavoriteFiltersService` を Protocol 化し、`JsonFavoriteFiltersService` と `QSettingsFavoriteFiltersService` の 2実装を用意

**却下理由**:
- 既存 GUI コードの修正が必要（import 変更）
- `FavoriteFiltersService` 使用箇所が全体に散在するため、移行コスト大
- 本当は後方互換性が必要な要件と矛盾

### 代替案 2: 環境検出を呼び出し側で実施

**概要**: `get_favorite_filters_service()` ユーティリティ関数で環境検出して返す

```python
def get_favorite_filters_service():
    if os.environ.get("LORAIRO_CLI_MODE") == "true":
        return JsonFavoriteFiltersService()
    else:
        return FavoriteFiltersService()  # QSettings ベース
```

**却下理由**:
- ServiceContainer の責務が不明確化
- 環境検出ロジックが分散
- DI パターンの一貫性が損なわれる

### 代替案 3: NoOp ではなく実装を省略

**概要**: CLI 環境では signal_manager を None にして処理をスキップ

```python
if service_container._cli_mode:
    signal_manager = None
```

**却下理由**:
- 呼び出し側が None チェックを強いられる
- Protocol 非準拠 → 型チェッカーエラー
- RuntimeError の可能性

## 設計上の注意点

### 1. Qt インポートの最小化

**実装方針**:
- ServiceContainer の signal_manager プロパティ内でのみ条件分岐
- CLI 実行時には `from PySide6 import ...` が実行されない
- 本体ロジックに Qt への依存が漏れない

### 2. 環境変数による制御

**推奨値**:
```bash
# CLI モード有効化
export LORAIRO_CLI_MODE=true
export LORAIRO_CLI_MODE=1

# デフォルト（未設定）= GUI モード
```

**理由**: 
- デフォルトが GUI モード（既存動作維持）
- 明示的な環境変数設定でのみ CLI 切り替え
- 予期しない CLI 実行を防止

### 3. Protocol 準拠による型安全性

**効果**:
```python
def some_function(signal_manager: SignalManagerServiceProtocol):
    # 型チェッカーが両実装の互換性を確認
    signal_manager.emit_application_signal("test")
```

- MyPy/Pyright で静的検証可能
- IDE の type hint サポート活用
- テスト時の mock 作成が容易

## パフォーマンス考慮

### 初期化オーバーヘッド

**favorite_filters_service**:
- QSettings: OS の設定ストレージアクセス
- JSON: ファイル読み込み（`~/.config/lorairo/favorite_filters.json`）
- **影響**: 無視できるレベル（数ms）

**signal_manager**:
- GUI: SignalManagerService 初期化（遅延初期化で問題なし）
- CLI: NoOpSignalManager 初期化（軽量）
- **影響**: 実質的に無視（NoOp の場合）

## テスト対応

### 環境ごとのテスト実行

```bash
# GUI 環境テスト（デフォルト）
uv run pytest tests/ -m gui

# CLI 環境テスト
LORAIRO_CLI_MODE=true uv run pytest tests/ -m cli
```

### テスト隔離

```python
# 環境変数をテスト内で設定
def test_cli_mode(monkeypatch):
    monkeypatch.setenv("LORAIRO_CLI_MODE", "true")
    container = ServiceContainer()
    # CLI 環境でのテスト
```

## 再利用可能なパターン

### Qt 非依存化の一般的アプローチ

1. **接触面を Protocol で定義** → Signal, QSettings など
2. **Pure Python 実装を作成** → NoOp または代替実装
3. **DI Container で自動選択** → 環境変数で制御
4. **既存コード修正最小化** → Adapter Pattern で互換性確保

## 教訓・次回への提言

### ✅ 上手くいったこと
- ServiceContainer による一元管理で環境切り替えが透過的
- テストが環境ごとに分かれていない（両環境で動作）
- Protocol 準拠により型安全性を確保

### ⚠️ 注意点
- 環境変数の命名規則を明確に（チーム内で周知が必要）
- CLI 環境でのログレベル設定（DEBUG で操作追跡可能）
- NoOp 実装のテスト漏れ防止（Protocol 準拠確認テスト必須）

### 🔮 次のステップへの推奨

**Phase 2 CLI 実装時**:
1. ConfigurationService も環境に応じた実装を検討（TOML vs 環境変数）
2. logging 出力先の環境別切り替え（GUI: ファイル, CLI: stdout）
3. Exception handling の環境別対応（GUI: MessageBox, CLI: stderr）

**Phase 3 以降**:
1. API サーバー実装時に同じ Pattern を適用可能
2. 他の Qt 依存サービスの除去に同じ手法を使用

## 関連ファイル・コミット

- `src/lorairo/services/favorite_filters_service.py`: JSON 化実装
- `src/lorairo/services/noop_signal_manager.py`: NoOp 実装
- `src/lorairo/services/service_container.py`: DI 自動切り替え
- テスト: `test_noop_signal_manager.py`, `test_service_container_signal_manager.py`

---

**Information**: This design decision enables LoRAIro to run in both GUI and CLI environments without code duplication, leveraging Protocol-Based DI and Adapter Pattern for transparent environment switching.
