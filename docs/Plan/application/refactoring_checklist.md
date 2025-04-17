# Application Layer Refactoring Checklist

## アプリケーション/サービス層の設計と実装

-   [ ] 各GUIウィジェットの直接呼び出しに対応するアプリケーション/サービス層のメソッドを特定または設計する。 (進捗: `ConfigurationService`, `ImageProcessingService`, `ImageTextFileReader` 新設・設計完了)
-   [ ] 設計に基づき、アプリケーション/サービス層のクラス (`ImageProcessingService`, `ImageTextFileReader`, `DatasetManagementService`, `AnnotationService` など) を実装する。(進捗あり)

## 設定管理 (`ConfigurationService`)

-   [x] (旧`ConfigManager`の)クラス名を役割に合わせて変更する (実施せず、`ConfigurationService` を新設)
-   [x] クラスの docstring を更新し、責務を明確化する (`ConfigurationService`)
-   [x] (旧`ConfigManager`の)インスタンス管理方法を見直す (シングルトン廃止、DI導入)。
-   [x] `MainWindow` でインスタンスを生成し、DI を行うように `initialize` メソッド等を修正する。
-   [x] 各ページウィジェットが DI されたインスタンスを使用するように修正する (`ConfigurationWindow` 分完了)。
-   [x] `ConfigurationService` の初期化処理を修正し、`get_config()` の結果を内部状態として保持するようにする。
-   [x] `ConfigurationWindow` で設定変更時に `ConfigurationService` の状態を更新する処理を実装する。
-   [ ] 他のウィジェットが必要な設定値を (旧`ConfigManager` の代わりに) `ConfigurationService` から取得するように修正する。(今後のタスク)
-   [x] `ConfigurationService` に設定をファイルに保存するメソッド (`save_settings()`) を追加する。
-   [x] `ConfigurationWindow` の保存ボタンクリック時の処理 (`on_buttonSave_clicked`) を修正し、`ConfigurationService` の `save_settings()` メソッドを呼び出すように変更する。

## 状態管理の見直し

-   [x] (旧`ConfigManager` から) `dataset_image_paths` 関連のコードを削除する。
-   [x] `dataset_image_paths` の管理・更新ロジックを `MainWindow` に実装する。
-   [ ] 明確なデータフロー(例: `MainWindow` が保持し、各ページに渡す)を定義・実装する。
-   [ ] `ImageTaggerWidget` の `all_results` のような大きな状態保持について、メモリ効率を考慮した代替案(例: 処理結果を都度DBに書き込む、必要なデータのみ保持するなど)を検討・実装する。

## アノテーション処理

-   [ ] `ImageTextFileReader` にファイルベース (.txt/.json) のアノテーション読み込みロジック (`caption_tags.py`, `cleanup_txt.py` の既存機能) を統合する。
-   [ ] `AnnotationService` (仮称) をアプリケーション/サービス層に作成し、ライブラリ呼び出しの準備、結果の整形(`formatted_output` のパース含む)、DB保存指示を行うように実装する。

## 関連ドキュメント

-   [全体リファクタリング計画](../../refactoring_plan.md)
-   [アプリケーション層仕様](../specs/application/) 