# ログモジュール改善チェックリスト (Loguru導入後)

LoRAIroのログモジュールに `loguru` を導入したことに伴い、リファクタリング・改善項目を更新します。

---

## ✅ チェックリスト

- [x] **`loguru` の導入**
  - 標準 `logging` から `loguru` へ移行。
  - 依存関係に `loguru` を追加。
- [x] **設定ファイル主導のロギング運用 (`config/lorairo.toml`)**
  - `loguru` の設定 (レベル、ファイルパス、ローテーション等) を `config/lorairo.toml` の `[log]` セクションで管理。
  - `src/lorairo/utils/config.py` で設定を読み込み、`src/lorairo/utils/log.py` の初期化関数で適用。
- [x] **モジュールごとのログレベル制御**
  - `config/lorairo.toml` の `[log.levels]` セクションでモジュールごとのログレベルを指定可能に。
  - `log.py` の初期化時にカスタムフィルタ (`level_filter`) を適用。
- [x] **`setup_logger` の多重初期化防止 → 不要に**
  - `loguru` では `logger.remove()` で初期化前に既存ハンドラを削除するため問題ない。
- [x] **OS/ロケール依存処理の整理 → 不要に**
  - `loguru` が UTF-8 エンコーディング (`encoding="utf-8"`) を標準で適切に処理するため不要に。
- [x] **トレースバック表示の改善・確認**
  - `loguru` の `backtrace=True` および `diagnose=True` オプションにより、例外発生時のトレースバックが改善された。
- [-] **~~`get_logger` などラッパー関数のdocstring充実~~ → 不要に**
  - `from lorairo.utils.log import logger` で直接 `loguru` のロガーを使用するため不要。
- [x] **テスト・運用時のログ出力の一貫性確認**
  - BDDテスト (`tests/features/logging.feature`) を実装し、基本的なレベル制御、モジュール固有レベル制御、例外ログ記録が仕様通り動作することを確認。
  - テスト実装時、`logger.bind(name=...)` でモジュール名を指定してログを出力した場合、デフォルトのフィルタ (`_level_filter`) が `record['name']` (呼び出し元モジュール名) を見てしまうため、モジュール固有レベルが適用されない問題が発生。
  - 解決策として、テスト用シンク (`collecting_sink`) 専用のカスタムフィルタ (`_test_sink_level_filter`) を `tests/step_defs/test_logging_steps.py` に定義。このフィルタは `record['extra'].get('name')` を優先的に参照することで、テストシナリオにおけるモジュール固有レベルの検証を可能にした。
  - `pytest` の `caplog` フィクスチャは使用せず、テスト用シンクと収集リスト (`log_records_list`) でログレコードを直接検証する方式を採用。
- [-] **~~将来的な外部ライブラリ (structlog等) への移行検討~~ → 完了 (loguru採用)**
  - `loguru` を採用したため、この項目は完了。

---

## 参考: Loguru ベースのロギング構成イメージ

```mermaid
graph TD
    A[config/lorairo.toml] -->|log settings dict| B(config.get_config());
    B --> C{log.initialize_logging()};
    subgraph Initialization [log.initialize_logging]
        C --> D(_parse_log_levels)
        D -- Parsed levels --> E[logger.remove()];
        E --> F{Define level_filter};
        F -- Uses levels --> G{Setup Console Sink};
        G -- filter, fixed opts --> H[logger.add(sys.stderr, ...)];
        F -- Uses levels --> I{Check file_path};
        I -- Yes --> J{Setup File Sink};
        J -- filter, fixed opts --> K[logger.add(file_path, ...)];
        I -- No --> L[Skip File Sink];
    end
    M[Module Code] --> N{Import logger};
    subgraph Usage [Logging in Module]
        N --> O[from lorairo.utils.log import logger];
        O --> P[Call logger methods];
        P -- log record --> Q((Loguru Core));
        Q -- level_filter --> R{Output?};
        R -- Yes --> S((Output to Console Sink));
        R -- Yes --> T((Output to File Sink (if enabled)));
    end
```

---

**このチェックリストは随時アップデートし、進捗や決定事項は Memory Bank の decisionLog.md にも記録してください。**
