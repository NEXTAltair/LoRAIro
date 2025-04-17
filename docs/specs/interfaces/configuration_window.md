# Configuration Window 仕様書

## 1. 概要

本ドキュメントは、`lorairo` アプリケーションの設定画面 (`ConfigurationWindow`) の仕様を定義する。このウィンドウは、ユーザーがアプリケーションの各種設定を確認・変更するためのインターフェースを提供する。

## 2. 責務

-   **設定項目の表示:** `ConfigurationService` から現在の設定値を取得し、対応するUIウィジェット（ディレクトリピッカー、ラインエディット、コンボボックスなど）に表示する。
-   **ユーザー入力の受付:** ユーザーがUIウィジェットを通じて設定値を変更した際に、その入力を受け付ける。
-   **設定の更新依頼:** ユーザーによる設定値の変更を検知し、`ConfigurationService` の更新メソッド (`update_setting` など) を呼び出して、サービスが保持する設定値を更新するよう依頼する。
-   **設定の保存依頼:** 「保存」または「名前を付けて保存」ボタンがクリックされた際に、`ConfigurationService` の保存メソッド (`save_settings`) を呼び出して、現在の設定をファイルに保存するよう依頼する。
-   **ユーザーへのフィードバック:** 設定の保存結果（成功または失敗）をメッセージボックスなどでユーザーに通知する。

## 3. 主要コンポーネント (例)

-   **ディレクトリピッカー (`dirPickerOutput`, `dirPickerResponse`, etc.):** 各種出力ディレクトリのパスを設定するためのカスタムウィジェット。変更時に `ConfigurationService.update_setting("directories", ...)` を呼び出す。
-   **APIキー入力 (`lineEditOpenAiKey`, `lineEditGoogleVisionKey`, etc.):** 外部APIのキーを入力するためのラインエディット。編集完了時に `ConfigurationService.update_setting("api", ...)` を呼び出す。
-   **ログレベル選択 (`comboBoxLogLevel`):** ログレベルを選択するためのコンボボックス。選択変更時に `ConfigurationService.update_setting("log", "level", ...)` を呼び出す。
-   **ログファイルピッカー (`filePickerLogFile`):** ログファイルのパスを設定するためのカスタムウィジェット。変更時に `ConfigurationService.update_setting("log", "file_path", ...)` を呼び出す。
-   **保存ボタン (`buttonSave`, `buttonSaveAs`):** 設定をファイルに保存するためのボタン。クリック時に `ConfigurationService.save_settings()` を呼び出す。

(注: 上記は `src/lorairo/gui/window/configuration_window.py` の実装に基づく例であり、UIの変更に応じて更新が必要)

## 4. 依存関係

-   `ConfigurationService`: 設定値の取得、更新、保存を行うアプリケーションサービス。
-   `PySide6`: GUIフレームワーク。
-   各種カスタムUIウィジェット (例: `DirectoryPickerWidget`, `FilePickerWidget`)

## 5. 初期化 (`initialize`)

-   `ConfigurationService` のインスタンスを受け取り、内部に保持する。
-   受け取った `ConfigurationService` を使用して、現在の設定値をUIウィジェットにロードする。

## 6. 関連ドキュメント

-   GUI全体の構成: [gui_interface.md](interfaces/gui_interface.md)
-   設定サービスの仕様: [configuration_service.md](../application/configuration_service.md)