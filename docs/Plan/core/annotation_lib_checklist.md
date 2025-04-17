# Core Layer Refactoring Checklist

## AIアノテーション機能のライブラリ委譲

-   [ ] `docs/specs/ai_annotation_interface.md` に定義されたインターフェースに基づき、`image-annotator-lib` を呼び出す処理を実装する。(主に Application 層の `AnnotationService` が担当)
-   [ ] `AnnotatorClient` (仮称) のようなラッパークラスをインフラストラクチャ層に作成し、ライブラリ呼び出しの詳細をカプセル化することを検討。
-   [ ] 現在の `ImageAnalyzer`, `APIClientFactory`, `TagCleaner` のうち、`lorairo` 本体で不要になる部分を削除または修正。(一部ロジックは `AnnotationService` に残る可能性あり)

## 関連ドキュメント

-   [全体リファクタリング計画](../../refactoring_plan.md)
-   [コア層仕様](../specs/core/) 