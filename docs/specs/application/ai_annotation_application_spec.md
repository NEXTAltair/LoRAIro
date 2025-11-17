# AIアノテーション Application層仕様書（AnnotationService設計）

> **⚠️ DEPRECATED**: このドキュメントは旧アーキテクチャ（AnnotationService）を記述しています。
> 現在は `WorkerService` (`src/lorairo/gui/services/worker_service.py`) が非同期処理を統一的に管理しています。
> 最新の仕様は `docs/specs/application/worker_service.md` を参照してください。

## 1. 目的

画像アノテーション（タグ・キャプション・スコア生成）を外部ライブラリ `image-annotator-lib` に委譲し、結果をDB保存・UI連携するApplication層サービスの設計仕様を定義する。

## 2. サービス責務

- Interface層からの指示に基づき、画像リスト・pHashリスト・モデル名リストを受け取る。
- **非同期処理の管理:** `QThread` を利用してアノテーション処理（`image-annotator-lib` 呼び出し、結果パース、DB保存）をバックグラウンドで実行する責務を持つ。
- `image_annotator_lib.api.annotate` の呼び出し。
- 結果辞書のパース（tags, formatted_output からキャプション・スコア抽出）。
- DB保存用データ整形・DB Manager等への保存依頼。
- エラー処理・ロギング。
- **Interface層への通知:** シグナル・スロット機構を用いて、処理の進捗、完了（結果）、エラーをInterface層に通知する。

## 3. 主なクラス・メソッド

- `AnnotationService` クラス (`QObject` を継承)
  - **シグナル:**
    - `progressUpdated = pyqtSignal(int)` # 進捗率 (0-100)
    - `annotationFinished = pyqtSignal(dict)` # 完了通知（整形済み結果データなど）
    - `errorOccurred = pyqtSignal(str)` # エラー通知
  - **メソッド:**
    - `start_annotation(images: list[Image.Image], models: list[str], phashes: list[str]|None) -> None`:
      - アノテーション処理を開始する。内部で `QThread` とワーカーオブジェクトを準備し、スレッドを開始する。このメソッド自体はすぐにリターンする。
    - (内部メソッド: 例: `_create_worker`, `_handle_finished`, `_handle_error` など)

## 4. 非同期処理・進捗通知

- **実装:** `QThread` とワーカーオブジェクトパターンを使用する。
  - `AnnotationService` が `QThread` を管理する。
  - 実際の処理（ライブラリ呼び出し、パース、DB保存）は `QObject` を継承したワーカークラスで行い、`moveToThread` でワーカースレッドに移動させる。
- **通知:** ワーカーオブジェクトは処理の節目で進捗・完了・エラーに対応するシグナルを発行し、`AnnotationService` がこれを中継するか、Interface層が直接接続する。

## 5. DB保存・データ整形

- 結果辞書からtags, caption, score等を抽出し、DB保存用の形式に整形する
- DB保存はImageDatabaseManager等の専用クラスを利用

## 6. エラー処理

- 予期されるエラー（APIエラー・データ不整合等）は個別にハンドリングし、詳細なエラーメッセージを記録・通知
- 予期しない例外はロギングし、上位に伝播

## 7. Interface層との連携

- **指示:** Interface層は `AnnotationService.start_annotation` を呼び出す。
- **通知:** Interface層は `AnnotationService` が発行する `progressUpdated`, `annotationFinished`, `errorOccurred` シグナルをスロットに接続し、UIを更新する。

---

（本ドキュメントはApplication層観点のAIアノテーションサービス設計仕様です） 