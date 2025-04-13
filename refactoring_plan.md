# src/lorairo/annotations および src/lorairo/score_module リファクタリング計画 (v3 - 最終版)

## 目的

タグ付け機能および主要なスコアリング機能が `local_packages/image-annotator-lib` に分離されたことに伴い、`src/lorairo/annotations` および `src/lorairo/score_module` ディレクトリ内の **不要になったコードを削除・修正** する。

**注意:** このタスクのスコープは **不要コードの削除のみ** とする。`image-annotator-lib` の呼び出しと戻り値処理の実装は、**別の新しいタスク** として扱う。

## 背景

*   `image-annotator-lib` は、外部 Vision API (OpenAI, Google, Claude) との連携機能、および主要なスコアリング機能 (CLIP美的スコア、LAION/CAFE美的スコアなど) を担当する。
*   タグ・キャプションの整形機能 (`cleanup_txt.py`) および既存アノテーションファイル (`.txt`, `.caption`) の読み込み機能 (`caption_tags.py` 内) は、引き続き `src/lorairo/annotations` で管理する必要がある。
*   `score_module` 内の MUSIQ および RewardFunction スコアリング機能は、現時点では不要と判断し、削除する。

## 最終計画概要

1.  **`src/lorairo/annotations/api_utils.py` の削除:** API 連携機能が不要になるため、ファイル全体を削除する。
2.  **`src/lorairo/annotations/caption_tags.py` の修正:** 不要になった API 連携関連のコード（メソッド、属性、インポート）を削除する。既存アノテーション読み込みと整形機能の呼び出しは維持する。**（注意: この段階では `image-annotator-lib` の呼び出しは実装しないため、ファイルは機能しない状態になります）**
3.  **`src/lorairo/annotations/cleanup_txt.py` の維持:** 整形機能は引き続き必要となるため、変更しない。
4.  **`src/lorairo/score_module/` ディレクトリの削除:** スコアリング機能が `image-annotator-lib` に集約されるため、ディレクトリ全体を削除する。

## 最終計画フロー

```mermaid
graph TD
    A[開始] --> B(情報収集: annotations);
    B --> C(ユーザー確認: image-annotator-lib 機能範囲);
    C -- API連携のみ代替 --> D(計画立案 v1);
    D --> D1(annotations 修正計画);
    D1 --> E(ユーザーフィードバック: score_module も確認);
    E --> F(情報収集: score_module);
    F --> G(ユーザー確認: score_module の扱い);
    G -- 全削除 --> H(計画更新 v2);
    H --> H1(ユーザーフィードバック: タスク分割);
    H1 --> I(計画更新 v3 - 最終版);
    I --> J[1. annotations/api_utils.py を削除];
    I --> K[2. annotations/caption_tags.py を修正 (不要コード削除のみ)];
    K --> K1[API連携メソッド/属性を削除];
    K --> K2[API関連インポートを削除];
    K --> K3[既存アノテーション/整形初期化は維持];
    I --> L[3. annotations/cleanup_txt.py は維持];
    I --> M[4. score_module/ ディレクトリを削除];
    J & K & L & M --> N(計画確認);
    N --> O(Markdown 更新);
    O --> P(Codeモードへ移行依頼);
    P --> Q[完了 (不要コード削除)];
```

## 具体的な手順 (今回のタスク範囲)

### 1. `src/lorairo/annotations/api_utils.py` の削除

*   `src/lorairo/annotations/api_utils.py` ファイルを削除する。

### 2. `src/lorairo/annotations/caption_tags.py` の修正 (不要コード削除のみ)

*   以下のインポート文を削除する:
    ```python
    from annotations.api_utils import APIClientFactory, APIError
    ```
*   `ImageAnalyzer` クラスから以下のメソッドを削除またはコメントアウトする (次のタスクで実装するため):
    *   `initialize` (API関連部分)
    *   `analyze_image`
    *   `_process_response`
    *   `_extract_tags_and_caption`
    *   `create_batch_request`
    *   `get_batch_analysis`
*   `ImageAnalyzer` クラスから以下の属性を削除する:
    *   `api_client_factory`
    *   `vision_models`
    *   `score_models`
*   `ImageAnalyzer.__init__` 内の `self.tag_cleaner = initialize_tag_cleaner()` は維持する。
*   `ImageAnalyzer.get_existing_annotations` および `ImageAnalyzer._read_annotations` は維持する。

### 3. `src/lorairo/annotations/cleanup_txt.py` の維持

*   このファイルには変更を加えない。

### 4. `src/lorairo/score_module/` ディレクトリの削除

*   `src/lorairo/score_module/` ディレクトリ全体を削除する。

## 次のステップ

この最終計画に基づいて、Code モードで **不要コードの削除作業のみ** を行う。
ライブラリ連携の実装は、このタスク完了後に別途依頼する。