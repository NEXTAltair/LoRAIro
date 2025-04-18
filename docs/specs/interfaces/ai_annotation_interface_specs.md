# AIアノテーション Interface層 仕様書

## 1. 目的

AIアノテーション機能（`image-annotator-lib` 連携）におけるユーザーインターフェース（GUI）部分の仕様を定義する。

## 2. 対象コンポーネント（案）

- `src/lorairo/gui/widgets/annotation_widget.py` の `AnnotationWidget` クラス（仮）

## 3. UI仕様

-   **(必須)** 画像リスト表示: アノテーション対象となる画像の一覧を表示する機能。
-   **(必須)** モデル選択UI: アノテーションに使用するAIモデルを選択するUI（例: チェックボックスリスト、ドロップダウン）。
-   **(必須)** アノテーション実行ボタン: 選択された画像とモデルでアノテーション処理を開始するボタン。
-   **(推奨)** 進捗表示: アノテーション処理中の進捗状況を表示する機能（例: プログレスバー、ステータスメッセージ）。
-   **(必須)** 結果表示エリア: アノテーション結果（タグ、キャプション、スコア）を表示するエリア。モデルごとの結果を表示できるように考慮する。
-   **(必須)** エラー表示: アノテーション処理中にエラーが発生した場合に、ユーザーに分かりやすく通知する機能（例: ダイアログ、ステータスバー）。

## 4. ユーザーインタラクションと責務

-   ユーザーは画像リストから対象を選択し、使用するモデルを選んで「実行」ボタンを押す。
-   **責務:**
    -   ユーザーからの入力（画像選択、モデル選択）を受け付ける。
    -   「実行」ボタン押下時に、選択された画像リストとモデルリストを Application 層のサービス (`AnnotationService` など) に渡して処理を依頼する。
    -   Application 層からの進捗、結果、エラー通知を受け取り、UIに反映する。

## 5. Application層との連携

-   `AnnotationService` (仮) のメソッドを呼び出してアノテーション処理を開始する。
    -   例: `annotation_service.run_annotation(selected_images, selected_models)`
-   非同期処理に対応し、サービスからのシグナルやコールバックを受け取ってUIを更新する。

## 6. 関連ドキュメント

-   AIアノテーションCore仕様: [ai_annotation_core_spec.md](../core/ai_annotation_core_spec.md)
-   AIアノテーションApplication層仕様: [ai_annotation_application_spec.md](../application/ai_annotation_application_spec.md)

---

(本ドキュメントはInterface層観点のAIアノテーションGUI設計仕様です) 