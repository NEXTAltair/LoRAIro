Feature: LoRAIro ログ機能
  開発者または運用者として、
  設定に基づいてログシステムが正しく機能してほしい。
  これにより、アプリケーションを効果的に監視およびデバッグできる。

  Background: 背景
    Given 一時的な設定ディレクトリが存在する
    And 一時的なログディレクトリが存在する
    And デフォルトのログレベルが "INFO" の基本ログ設定が存在する

  Scenario: 基本的なログ記録 - デフォルトレベルに基づくコンソールとファイルへの出力
    Given ログ設定で一時ログディレクトリ内にログファイルパスが指定されている
    When 現在の設定でロガーが初期化される
    And モジュール "basic_log_test" からログレベル "INFO" のメッセージ "表示されるべき情報メッセージ" が出力される
    And モジュール "basic_log_test" からログレベル "DEBUG" のメッセージ "隠されるべきデバッグメッセージ" が出力される
    Then コンソール出力にログレベル "INFO" のメッセージ "表示されるべき情報メッセージ" が含まれる
    And コンソール出力にログレベル "DEBUG" のメッセージ "隠されるべきデバッグメッセージ" が含まれない
    And ログファイルの内容にログレベル "INFO" のメッセージ "表示されるべき情報メッセージ" が含まれる
    And ログファイルの内容にログレベル "DEBUG" のメッセージ "隠されるべきデバッグメッセージ" が含まれない

  Scenario Outline: ログレベル制御-設定によるデフォルトレベル
    Given ログ設定でデフォルトレベルが "<log_level>" に設定されている
    When 現在の設定でロガーが初期化される
    And モジュール "default_level_test" からログレベル "<message_level>" のメッセージ "レベル制御テスト用メッセージ" が出力される
    Then コンソール出力にメッセージ "レベル制御テスト用メッセージ" が <should_or_not>

    Examples: 設定デフォルトレベル vs メッセージレベル
      | log_level | message_level | should_or_not |
      | INFO      | INFO          | should        |
      | INFO      | DEBUG         | should not    |
      | DEBUG     | INFO          | should        |
      | DEBUG     | DEBUG         | should        |
      | WARNING   | INFO          | should not    |
      | WARNING   | WARNING       | should        |
      | ERROR     | WARNING       | should not    |
      | ERROR     | ERROR         | should        |
      | CRITICAL  | ERROR         | should not    |
      | CRITICAL  | CRITICAL      | should        |

  Scenario Outline: モジュール固有ログレベル制御デフォルト上書き
    Given ログ設定でデフォルトレベルが "INFO" に設定されている
    And ログ設定でモジュール "lorairo.module_test" のレベルが "<module_log_level>" に設定されている
    When 現在の設定でロガーが初期化される
    And モジュール "lorairo.module_test" からログレベル "<message_level>" のメッセージ "モジュール固有テストメッセージ" が出力される
    Then コンソール出力にメッセージ "モジュール固有テストメッセージ" が <should_or_not>

    Examples: モジュールレベル vs メッセージレベル (デフォルト=INFO)
      | module_log_level | message_level | should_or_not |
      | DEBUG            | DEBUG         | should        |
      | DEBUG            | INFO          | should        |
      | WARNING          | DEBUG         | should not    |
      | WARNING          | INFO          | should not    |
      | WARNING          | WARNING       | should        |
      | INFO             | DEBUG         | should not    |
      | INFO             | INFO          | should        |

  Scenario: 例外ログ記録 - メッセージ、トレースバック、変数の捕捉
    Given ログ設定で一時ログディレクトリ内にログファイルパスが指定されている
    And ログ設定でデフォルトレベルが "DEBUG" に設定されている
    When 現在の設定でロガーが初期化される
    And "ValueError" を発生させメッセージ "無効な値が検出されました" と共に logger.exception でログ記録する関数が呼び出される
    Then コンソール出力にエラーメッセージ "無効な値が検出されました" が含まれる
    And コンソール出力に "ValueError" のトレースバックが含まれる
    And ログファイルの内容にエラーメッセージ "無効な値が検出されました" が含まれる
    And ログファイルの内容に "ValueError" のトレースバックが含まれる
    # Note: Gherkin で特定の変数('diagnose=True')の検証は複雑。
    # step定義で diagnose 出力の存在を確認すべき。

  # TODO: 必要であればファイルローテーションのシナリオを追加する（より複雑なステップ定義が必要になる可能性）。