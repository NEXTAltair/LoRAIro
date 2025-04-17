# GUIとビジネスロジック分離・リファクタリング詳細チェックリスト

## 1. 事前準備・計画

-   [x] **対象ウィジェット特定:** リファクタリング対象となるGUIウィジェットをすべて特定する。
    -   [ ] `src/lorairo/gui/window/edit.py` (`ImageEditorWidget`)
    -   [ ] `src/lorairo/gui/window/tagger.py` (`ImageTaggerWidget`)
    -   [ ] `src/lorairo/gui/window/overview.py` (`DatasetOverviewWidget`)
    -   [ ] `src/lorairo/gui/window/export.py` (`DatasetExporterWidget`)
    -   [x] `src/lorairo/gui/window/configuration_window.py` (`ConfigurationWindow`)
    -   [ ] (その他、ビジネスロジックを含む可能性のあるカスタムウィジェットがあれば追記)
-   [x] **サービス層設計:** 各ウィジェットのビジネスロジックに対応するアプリケーション/サービス層のクラスとメソッドを設計・定義する。
    -   [ ] `ImageProcessingService` (画像処理関連)
    -   [ ] `AnnotationService` (AIアノテーション関連)
    -   [ ] `DatasetManagementService` (データセット操作、エクスポート関連)
    -   [x] `ConfigurationService` (設定読み書き関連)
    -   [ ] `DatabaseService` または Repository (DB操作関連)
    -   [ ] 各サービスメソッドのインターフェース (引数、戻り値、発生しうる例外) を明確にする (`docs/specs/` 配下の関連仕様書を更新)。
-   [x] **依存関係注入 (DI) 戦略決定:** サービス層のインスタンスをどのようにGUIウィジェットに渡すか決定する (例: `MainWindow` で生成し `initialize` メソッドで渡す)。

## 2. 各ウィジェットのリファクタリング

**以下の項目を、特定した各ウィジェットに対して実施する。**

### 2.1. ビジネスロジック呼び出しの特定と置換

-   [ ] **直接呼び出し特定:** ウィジェット内で `ImageDatabaseManager`, `FileSystemManager`, `ImageProcessingManager`, `ImageAnalyzer` (またはその後継クラス) などのビジネスロジック/インフラ層クラスを直接呼び出している箇所をすべてリストアップする。
    -   各ウィジェットごとに、主要な直接呼び出し・依存箇所を列挙（詳細は元チェックリスト参照）
-   [x] **サービス層メソッド特定:** 特定した直接呼び出しに対応する、適切なサービス層のメソッドを特定する。
-   [x] **UIイベントハンドラ特定:** ボタンクリック (`on_button_clicked`)、テキスト変更 (`on_text_changed`)、選択変更 (`on_selection_changed`) など、ビジネスロジックのトリガーとなるUIイベントハンドラを特定する。
-   [x] **ロジック置換:** UIイベントハンドラ内のビジネスロジックを、特定したサービス層メソッドの呼び出しに置き換える。
    -   [x] サービス層メソッドに必要な引数を正しく渡しているか確認する。
    -   [x] 必要に応じて、ユーザー入力のバリデーションをウィジェット側で行うか、サービス層で行うか判断する。
-   [x] **不要な import 削除:** ビジネスロジック/インフラ層クラスへの不要になった `import` 文を削除する。

### 2.2. サービス層からの結果処理

-   [x] **戻り値処理実装:** サービス層メソッドからの戻り値（処理結果データ、成功/失敗ステータスなど）を受け取り、UIに反映させる処理を実装する。
    -   [ ] テーブル、リスト、テキストフィールドなどの表示を更新する。
    -   [x] ステータスバーやメッセージボックスでユーザーに進捗や結果を通知する。
    -   [ ] 処理結果に応じてUI要素の状態 (有効/無効など) を変更する。
-   [x] **例外処理実装:** サービス層メソッドが送出しうる例外を適切に捕捉し、ユーザーにエラーメッセージを表示するなどの処理を実装する。

### 2.3. 状態管理の確認 (該当する場合)

-   [ ] ウィジェットが独自に大きな状態 (例: `ImageTaggerWidget` の `all_results`) を保持している場合、リファクタリング後の状態管理方法が適切か確認する (メモリ効率、データフローの観点)。必要であれば、サービス層やDBとの連携を見直す。

### 2.4. 特殊ケース: `ConfigurationWindow`

-   [ ] APIキーと Hugging Face 設定関連のUI要素 (`QLineEdit` など) を削除する。
-   [x] 上記UI要素に関連する設定の読み込み・保存ロジックを削除する。
-   [x] 設定保存処理 (`on_buttonSave_clicked` など) を、`ConfigurationService.save_settings()` (または相当するメソッド) の呼び出しに変更する。
-   [ ] `.env` ファイルからの設定読み込みがアプリケーション全体で正しく機能していることを確認する (これは `ConfigManager` リファクタリングと連携)。

## 3. テスト

-   [x] **ウィジェット単体テスト作成/更新:** 各ウィジェットの単体テストを作成または更新する。 (`ConfigurationWindow` 分完了)
    -   [x] サービス層の依存関係をモック化 (`unittest.mock` などを使用) する。 (`ConfigurationWindow` 分完了)
    -   [x] UIイベントをシミュレートし、サービス層メソッドが期待通りに呼び出されることを確認する。 (`ConfigurationWindow` 分完了)
    -   [x] サービス層メソッドのモックが返す結果に応じて、UIが正しく更新されることを確認する。 (`ConfigurationWindow` 分完了)
-   [ ] **結合テスト検討:** GUI操作からサービス層、インフラストラクチャ層まで連携する結合テストを検討する (必要に応じて)。

## 4. ドキュメント更新

-   [ ] **コードコメント/Docstring:** ウィジェット内のコードコメントや Docstring を更新し、サービス層との連携について記述する。
-   [ ] **仕様書更新:** GUIとサービス層のインターフェースに関するドキュメント (`docs/specs/gui_interface.md` など) を更新する。
-   [ ] **リファクタリング計画書更新:** `docs/Plan/refactoring_plan.md` の関連セクションの進捗を更新する。

## 5. 確認・レビュー

-   [x] コードレビューを実施し、設計原則 (責務分離、依存関係) が守られているか確認する。
-   [x] 実際にアプリケーションを操作し、リファクタリング前と同様に機能することを確認する (リグレッションテスト)。
-   [ ] パフォーマンスに影響がないか確認する。
    - [ ] `TrainingWidget`
    - [x] `ImageEditWidget` ([#XXX] テスト作成完了)
    - [ ] `GenerationWidget`

## 6. 関連ドキュメント

-   [全体リファクタリング計画](../../refactoring_plan.md)
-   [GUIインターフェース仕様](../../../specs/interfaces/gui_interface.md)
-   [GUIリファクタリング簡易チェックリスト](gui_refactoring_checklist.md)