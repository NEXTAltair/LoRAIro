# LoRAIro Logging Specification (Loguru Based)

## 1. 目的

このドキュメントは、LoRAIro アプリケーションにおけるログの取り扱いに関する仕様を定義します。開発者が一貫した方法でログを記録し、運用時のデバッグや問題追跡を容易にすることを目的とします。ログライブラリとして `loguru` を使用します。

## 2. 概要

ログ処理は `loguru` ライブラリによって管理されます。アプリケーション全体のログ設定は `src/lorairo/utils/log.py` 内の初期化関数 (`initialize_logging`) で行われ、各モジュールからは `from lorairo.utils.log import logger` のようにインポートしてロガーを使用します。

## 3. 設定方法

ログ設定は、`config/lorairo.toml` ファイル内の `[log]` (または `[tool.lorairo.log]`) セクションで行います。この設定情報は `src/lorairo/utils/config.py` の `get_config()` 関数によって読み込まれ、`log.py` の `initialize_logging` 関数で `loguru` に適用されます。

**設定可能なキー:**

*   `level` (文字列): アプリケーション全体のデフォルトログレベル (例: `"INFO"`, `"DEBUG"`)。指定がない場合のデフォルトは `"INFO"`。
*   `file_path` (文字列, オプション): ログファイルパス (例: `"logs/lorairo.log"`)。指定しない場合、ファイルログは無効。
*   `rotation` (文字列, オプション): ファイルローテーションの条件 (例: `"25 MB"`, `"1 week"`, `"monday at 12:00"`)。指定がない場合のデフォルトは `"25 MB"`。
*   `levels` (テーブル/辞書, オプション): モジュールプレフィックスごとのログレベルを設定します。キーはモジュール名 (例: `"lorairo.gui"`)、値はログレベル (例: `"DEBUG"`) です。
    ```toml
    [log.levels] # 省略可能
    "lorairo.gui" = "DEBUG"
    "lorairo.database" = "WARNING"
    ```

**固定設定 (コード内で設定):**

以下の項目は `config/lorairo.toml` では設定できず、`log.py` 内で固定値が設定されます。

*   **フォーマット (`LOG_FORMAT`):** `"{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}"`
*   **コンソール色付け (`colorize`):** 有効 (`True`)。
*   **拡張トレースバック (`backtrace`):** 有効 (`True`)。
*   **変数表示 (`diagnose`):** 有効 (`True`)。例外発生時に変数の値が表示されます。
*   **ログ保持数 (`retention`):** `5` ファイル (ローテーション時に古いファイルは5つまで保持)。
*   **ファイルエンコーディング (`encoding`):** `"utf-8"`。

**設定の優先順位とデフォルト:**

1.  `config/lorairo.toml` の `[log]` セクションの値が最優先されます。
2.  キーが指定されていない場合は、`log.py` 内の `log_config.get()` で指定されたデフォルト値 (`level="INFO"`, `rotation="25 MB"`) が使用されます。
3.  `[log.levels]` で指定されたモジュールレベルは、デフォルトの `level` 設定よりも優先されます。最も長く一致するプレフィックスが適用されます (例: `"lorairo.gui.widgets"` は `"lorairo.gui"` より優先)。
4.  無効なログレベル名が指定された場合、警告が出力され、デフォルト (`INFO`) または無視されます。

**例 (`config/lorairo.toml`):**

```toml
# ... other settings ...

[log]
level = "DEBUG"                # 全体をDEBUGレベルに
file_path = "logs/app.log"       # ログファイルパスを指定
rotation = "50 MB"             # ローテーションサイズを50MBに

[log.levels]                   # databaseモジュールはINFO、requestsはWARNINGに
"lorairo.database" = "INFO"
"requests" = "WARNING"
```

## 4. ログレベル

`loguru` では以下のログレベルが定義されています (重要度順)。

*   **CRITICAL (50):** プログラムの実行を継続できない致命的なエラー。
*   **ERROR (40):** 処理の失敗など、深刻な問題が発生したが、実行は継続可能。
*   **WARNING (30):** 予期しない状況や、将来問題を引き起こす可能性のある状況。
*   **SUCCESS (25):** 特定の操作が成功したことを示す (オプション)。
*   **INFO (20):** プログラムの正常な動作を示す情報。主要イベントやマイルストーン。
*   **DEBUG (10):** 開発およびデバッグ中にのみ関心のある詳細情報。
*   **TRACE (5):** `DEBUG` よりさらに詳細な情報 (オプション)。

**用途ガイドライン:**

*   **通常運用時:** `INFO` レベルを基本とします (`config/lorairo.toml` で `level = "INFO"` または未指定)。`SUCCESS` は必要に応じて重要な成功通知に使用します。
*   **デバッグ時:** 設定レベルを `DEBUG` や `TRACE` に変更し、問題箇所の特定に必要な情報を記録します (`config/lorairo.toml` や `[log.levels]` で変更)。
*   **エラーハンドリング:** `try...except` で捕捉した例外は、深刻度に応じて `ERROR` または `CRITICAL` で記録します。`logger.exception()` を使うとトレースバックが自動で記録されます。`WARNING` は注意が必要な状況で使用します。

## 5. 出力先 (シンク)

ログは `loguru` のシンク (sink) によって管理され、`log.py` の `initialize_logging` 関数内で `logger.add()` によって設定されます。以下のシンクが設定されます。

1.  **コンソール (`sys.stderr`):** 必須。リアルタイムな動作確認用。色付け (`colorize=True`) されます。
2.  **ファイル (オプション):** `config/lorairo.toml` で `file_path` が指定されている場合のみ設定されます。永続的なログ記録用。`rotation` と `retention=5` 設定が適用されます。

各シンクは、内部的にレベル `0` で設定されます。実際のログ出力は、`initialize_logging` 内で定義されるカスタムフィルタ関数 (`level_filter`) によって制御されます。このフィルタは、設定されたデフォルトレベル (`level`) およびモジュール別レベル (`levels`) に基づいて、各ログレコードを出力するかどうかを判断します。例外発生時は拡張トレースバック (`backtrace=True`) と変数情報 (`diagnose=True`) が出力されます。

## 6. ログフォーマット

`loguru` の強力なフォーマット機能を利用しつつ、可読性のために以下のカスタムフォーマットが `log.py` 内で固定設定されています (`config/lorairo.toml` での変更は不可)。

```
{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}
```

*   `{time:YYYY-MM-DD HH:mm:ss.SSS}`: 日時 (ミリ秒まで)
*   `{level: <8}`: ログレベル (INFO, DEBUG など、8文字幅で左揃え)
*   `{name}:{function}`: ログを出力したモジュール名と関数名
*   `{message}`: ログメッセージ本体

## 7. ファイルローテーション

ログファイルのローテーションは `loguru` によって自動的に管理されます。

*   `rotation`: ローテーションのトリガー条件を `config/lorairo.toml` で指定します。ファイルサイズ (例: `"25 MB"`) または時間 (例: `"1 week"`) で指定可能です。指定がない場合のデフォルトは `"25 MB"` です。
*   `retention`: 保持する古いログファイルの数は `5` に固定され、設定ファイルでの変更はできません。ローテーションが発生すると、最も古いログファイル5つが保持され、それより古いものは削除されます。

## 8. エンコーディング

`loguru` はデフォルトで UTF-8 を適切に扱います。コンソールおよびファイル出力ともに UTF-8 (`encoding="utf-8"`) が `log.py` で明示的に指定されるため、OS 依存のエンコーディング問題は発生しません。

## 9. ログ処理フロー

```mermaid
graph TD
    A[Application Start] --> B(Load Config via config.get_config());
    B --> C{Extract log settings dict (log_config)};
    C --> D(Call log.initialize_logging(log_config));
    subgraph Initialization [log.initialize_logging]
        D --> D1(Call _parse_log_levels(log_config));
        D1 -- Parsed levels --> D2{Get default_level_no, module_level_nos};
        D2 & C -- file_path, rotation --> E[logger.remove() - Remove existing handlers];
        E --> F{Define level_filter function};
        F -- Uses default_level_no, module_level_nos --> G{Setup Console Sink};
        G -- filter=level_filter, fixed(format, color, backtrace, diagnose), level=0 --> H[logger.add(sys.stderr, ...)];
        F --> I{Check if file_path exists};
        I -- Yes --> J{Setup File Sink};
        J -- filter=level_filter, fixed(format, backtrace, diagnose, retention=5, encoding), level=0 --> K[logger.add(file_path, rotation=..., ...)];
        I -- No --> L[File logging skipped];
        H & K & L --> M[Initialization Complete];
    end
    N[Module Code] --> O{Import logger};
    subgraph Usage [Logging in Module]
        O --> P[from lorairo.utils.log import logger];
        P --> Q[Call logger methods (info, debug, error, exception etc.)];
        Q -- log record --> R((Loguru Core));
        R -- level_filter decides --> S{Output?};
        S -- Yes --> T((Output to Console Sink));
        S -- Yes --> U((Output to File Sink (if enabled)));
        S -- No --> V((Discard Log Record));
    end
```

**フロー概要:**

1.  アプリ起動時に設定ファイル (`config/lorairo.toml`) を読み込み、ログ設定部分を抽出します。
2.  `log.initialize_logging` が呼び出されます。
3.  内部ヘルパー `_parse_log_levels` がログレベル設定を解析し、数値レベルに変換します。無効な設定は警告を表示します。
4.  既存の `loguru` ハンドラが削除されます。
5.  内部フィルタ関数 `level_filter` が定義されます。これは、各ログレコードのモジュール名とレベルを、解析済みの設定（デフォルトレベル、モジュール別レベル）と比較して出力可否を判断します。
6.  コンソールシンクが `level=0` と `level_filter` を使って追加されます。フォーマットや色付けなども設定されます。
7.  設定に `file_path` があれば、ファイルシンクも同様に `level=0`, `level_filter` を使って追加されます。ローテーション (`rotation`, `retention=5`) やエンコーディングも設定されます。
8.  初期化が完了します。
9.  各モジュールは `from lorairo.utils.log import logger` でロガーをインポートし、ログメソッド (`logger.info` など) を呼び出します。
10. `loguru` はログレコードを生成し、設定されたシンク（コンソール、ファイル）に渡します。
11. 各シンクにアタッチされた `level_filter` がレコードを評価し、設定レベルを満たしていればフォーマットして出力します。満たさなければ破棄します。

## 10. 使用方法

各モジュールでログを記録するには、`loguru` のロガーをインポートします。

```python
from lorairo.utils.log import logger # log.py から logger をインポート

def my_function(data):
    logger.info(f"処理を開始します: データ={data}") # INFOレベルで主要な動作を記録

    if data < 0:
        logger.warning(f"負の値が入力されました: {data}") # 注意喚起にWARNING

    logger.debug(f"データ型: {type(data)}") # デバッグ時に役立つ詳細情報

    try:
        # ... 何らかの処理 ...
        result = 10 / data # ここで ZeroDivisionError が発生する可能性
        logger.debug(f"中間結果: {result}")
        logger.success("処理が正常に完了しました。") # 成功を示す場合にSUCCESS
        return result
    except ZeroDivisionError as e:
        # logger.error(f"ゼロ除算エラーが発生しました: {e}") # トレースバックなしのエラーログ
        logger.exception("処理中に予期せぬエラーが発生しました") # 推奨: エラーメッセージと共にトレースバックと変数を記録
        raise # 必要に応じて例外を再送出
    except Exception as e:
        logger.exception("処理中に予期せぬエラーが発生しました") # その他の予期せぬ例外も記録
        raise

# 特定のコンテキストでログに追加情報を付与する場合 (オプション)
# logger_gui = logger.bind(module_context="GUI")
# logger_gui.info("GUI関連のメッセージ")
```

例外発生時は `logger.exception("エラーメッセージ")` を使用することを強く推奨します。これにより、エラーメッセージ、拡張トレースバック、および関連する変数の値が自動的にログに記録され、デバッグが大幅に容易になります。
