# LoRAIro ロギング仕様書(Loguru ベース)

## 1. 目的

本ドキュメントは、LoRAIro アプリケーションにおけるログ出力の仕様を定義する。開発者が一貫した方針でログを記録し、運用時のデバッグや問題追跡を容易にすることを目的とする。ログライブラリには `loguru` を採用する。

## 2. 概要

ログ処理は `loguru` ライブラリによって管理する。アプリケーション全体のログ設定は `src/lorairo/utils/log.py` の初期化関数(`initialize_logging`)で行い、各モジュールからは `from lorairo.utils.log import logger` でインポートしたロガーを使用する。

## 3. 設定方法

ログ設定は、`config/lorairo.toml` ファイルの `[log]`(または `[tool.lorairo.log]`)セクションに記述する。この設定は `src/lorairo/utils/config.py` の `get_config()` で読み込み、`log.py` の `initialize_logging` によって `loguru` へ適用する。

### 設定可能なキー

- `level`(文字列): アプリケーション全体のデフォルトログレベル(例:`"INFO"`、`"DEBUG"`)。未指定時のデフォルトは `"INFO"` である。
- `file_path`(文字列、内部デフォルト): ログファイルパス。初回生成される `config/lorairo.toml` には出力せず、`DEFAULT_CONFIG` の内部デフォルトを使用する。
- `rotation`(文字列、任意): ファイルローテーションの条件(例:`"25 MB"`、`"1 week"`、`"monday at 12:00"`)。未指定時のデフォルトは `"25 MB"` である。
- `levels`(テーブル・辞書、任意): モジュールプレフィックスごとのログレベルを設定する。キーにモジュール名(例:`"lorairo.gui"`)、値にログレベル(例:`"DEBUG"`)を指定する。
  ```toml
  [log.levels] # 省略可能
  "lorairo.gui" = "DEBUG"
  "lorairo.database" = "WARNING"
  ```

### 固定設定(コード内で定義)

以下の項目は `config/lorairo.toml` からは変更できず、`log.py` 内で固定値を設定する。

- **フォーマット(`LOG_FORMAT`)**: `"{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}"`
- **コンソール色付け(`colorize`)**: 有効(`True`)
- **拡張トレースバック(`backtrace`)**: 有効(`True`)
- **変数表示(`diagnose`)**: 有効(`True`)。例外発生時に変数の値も出力する。
- **ログ保持数(`retention`)**: `5` ファイル(ローテーション時に古いファイルを最大 5 つまで保持する)
- **ファイルエンコーディング(`encoding`)**: `"utf-8"`

### 設定の優先順位とデフォルト

1. `config/lorairo.toml` の `[log]` セクションの値が最優先される。
2. キーが未指定の場合は、`log.py` 内の `log_config.get()` のデフォルト値(`level="INFO"`、`rotation="25 MB"`)を使用する。
3. `[log.levels]` で指定したモジュール別レベルは、全体の `level` 設定より優先される。最も長く一致するプレフィックスを適用する(例:`"lorairo.gui.widgets"` は `"lorairo.gui"` より優先)。
4. 無効なログレベル名が指定された場合は警告を出力し、デフォルト(`INFO`)へフォールバックするか無視する。

### 設定例(`config/lorairo.toml`)

```toml
# ... other settings ...

[log]
level = "DEBUG"                # 全体をDEBUGレベルに
rotation = "50 MB"             # ローテーションサイズを50MBに

[log.levels]                   # databaseモジュールはINFO、requestsはWARNINGに
"lorairo.database" = "INFO"
"requests" = "WARNING"
```

## 4. ログレベル

`loguru` では以下のログレベルを重要度順に定義している。

- **CRITICAL(50)**: プログラムの実行を継続できない致命的なエラー。
- **ERROR(40)**: 処理の失敗など深刻な問題が発生したが、実行は継続可能な状態。
- **WARNING(30)**: 予期しない状況や、将来問題を引き起こす可能性のある状況。
- **SUCCESS(25)**: 特定の操作が成功したことを示す(任意)。
- **INFO(20)**: プログラムの正常な動作を示す情報。主要イベントやマイルストーン。
- **DEBUG(10)**: 開発およびデバッグ時にのみ必要な詳細情報。
- **TRACE(5)**: `DEBUG` よりさらに詳細な情報(任意)。

### 用途ガイドライン

- **通常運用時**: `INFO` レベルを基本とする(`config/lorairo.toml` で `level = "INFO"` または未指定)。`SUCCESS` は必要に応じて重要な成功通知に使用する。
- **デバッグ時**: `config/lorairo.toml` や `[log.levels]` でレベルを `DEBUG` または `TRACE` へ引き上げ、問題箇所の特定に必要な情報を記録する。
- **エラーハンドリング**: `try...except` で捕捉した例外は、深刻度に応じて `ERROR` または `CRITICAL` で記録する。`logger.exception()` を使用するとトレースバックが自動で記録される。注意喚起が必要な状況には `WARNING` を用いる。

## 5. 出力先(シンク)

ログ出力は `loguru` のシンク(sink)で管理し、`log.py` の `initialize_logging` 内で `logger.add()` により登録する。

1. **コンソール(`sys.stderr`)**: 必須。リアルタイムな動作確認用であり、色付け(`colorize=True`)を有効にする。
2. **ファイル(任意)**: `config/lorairo.toml` で `file_path` が指定されている場合のみ登録する。永続的なログ記録用であり、`rotation` と `retention=5` を適用する。

各シンク自体は内部的にレベル `0` で登録し、実際の出力可否は `initialize_logging` 内で定義するカスタムフィルタ関数(`level_filter`)が制御する。`level_filter` は全体のデフォルトレベル(`level`)とモジュール別レベル(`levels`)に基づき、各ログレコードの出力有無を判定する。例外発生時は拡張トレースバック(`backtrace=True`)と変数情報(`diagnose=True`)を出力する。

## 6. ログフォーマット

`loguru` のフォーマット機能を用い、可読性を確保するため以下のカスタムフォーマットを `log.py` 内で固定設定する(`config/lorairo.toml` からは変更不可)。

```
{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}
```

- `{time:YYYY-MM-DD HH:mm:ss.SSS}`: 日時(ミリ秒まで)
- `{level: <8}`: ログレベル(`INFO`、`DEBUG` など。8 文字幅で左揃え)
- `{name}:{function}`: ログを出力したモジュール名と関数名
- `{message}`: ログメッセージ本体

## 7. ファイルローテーション

ログファイルのローテーションは `loguru` によって自動管理する。

- `rotation`: ローテーションのトリガー条件を `config/lorairo.toml` で指定する。ファイルサイズ(例:`"25 MB"`)または時間(例:`"1 week"`)で指定できる。未指定時のデフォルトは `"25 MB"` である。
- `retention`: 保持する古いログファイル数は `5` に固定されており、設定ファイルからは変更できない。ローテーション発生時、古いログファイルは 5 つまで保持し、それより古いものは削除する。

## 8. エンコーディング

`loguru` は既定で UTF-8 を適切に扱う。さらに、`log.py` でコンソールおよびファイル出力の双方に `encoding="utf-8"` を明示指定しているため、OS 依存のエンコーディング問題は発生しない。

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

### フロー概要

1. アプリ起動時に設定ファイル(`config/lorairo.toml`)を読み込み、ログ設定部分を抽出する。
2. `log.initialize_logging` を呼び出す。
3. 内部ヘルパー `_parse_log_levels` がログレベル設定を解析して数値レベルへ変換する。無効な設定がある場合は警告を表示する。
4. 既存の `loguru` ハンドラを削除する。
5. 内部フィルタ関数 `level_filter` を定義する。`level_filter` は、各ログレコードのモジュール名とレベルを解析済み設定(デフォルトレベル・モジュール別レベル)と比較し、出力可否を判定する。
6. コンソールシンクを `level=0` と `level_filter` で追加し、フォーマットや色付けを設定する。
7. 設定に `file_path` がある場合は、ファイルシンクも同様に `level=0` と `level_filter` で追加し、ローテーション(`rotation`、`retention=5`)とエンコーディングを設定する。
8. 初期化を完了する。
9. 各モジュールは `from lorairo.utils.log import logger` でロガーをインポートし、`logger.info` などのログメソッドを呼び出す。
10. `loguru` がログレコードを生成し、登録されたシンク(コンソール・ファイル)へ渡す。
11. 各シンクの `level_filter` がレコードを評価し、設定レベルを満たせばフォーマットして出力し、満たさなければ破棄する。

## 10. 使用方法

各モジュールでログを記録するには、`loguru` のロガーをインポートする。

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

例外発生時は `logger.exception("エラーメッセージ")` の使用を強く推奨する。エラーメッセージに加えて拡張トレースバックと関連変数の値が自動記録されるため、デバッグが大幅に容易になる。
