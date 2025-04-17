# AI アノテーション連携 仕様書 (image-annotator-lib 委譲)

## 1. 概要

本ドキュメントは、`lorairo` が外部ライブラリ `image-annotator-lib` を利用してAIによる画像アノテーション（タグ、キャプション、スコア生成）を行う際のインターフェースと処理フローを定義する。`lorairo` 本体にはAIモデルとの直接的な通信ロジックは含めず、アノテーション処理は `image-annotator-lib` に完全に委譲する。

```mermaid
graph TD
    subgraph LoRAIro
        A[画像リスト] --> B(アノテーション実行指示);
        A1[pHashリスト (Optional)] --> B;
        C[GUI/設定ファイル] --> D(モデル名リスト選択);
        D --> B;
        B -- 画像リスト, モデル名リスト, pHashリスト? --> E{image_annotator_lib.api.annotate};
        E -- 結果辞書 (pHash -> Model -> Result) --> F(結果ハンドリング);
        F --> G[DB保存/GUI表示];
        F -- エラー情報 --> H[エラー処理];
        I[lorairo/config 内設定ファイル] --> J(image-annotator-lib 設定);
    end

    subgraph image-annotator-lib
        K(ライブラリ エントリポイント: annotate);
        E --> K;
        J --> K; // 設定読み込み
        K -- pHash提供時 --> L[pHash計算スキップ];
        K -- pHash未提供時 --> M[pHash計算];
        L & M --> N[内部処理 (モデルインスタンス管理, APIコール, 結果整形)];
        N --> E;
    end

    style E fill:#f9f,stroke:#333,stroke-width:2px
```

## 2. インターフェース仕様

### 2.1. `lorairo` から `image-annotator-lib` への入力

-   **呼び出し関数:** `image_annotator_lib.api.annotate`
-   **引数:**
    -   `images_list` (`list[Image.Image]`): アノテーション対象の PIL Image オブジェクトのリスト。
    -   `model_name_list` (`list[str]`): 使用するAIモデル名のリスト (例: `["gpt-4o", "claude-3-sonnet"]`)。
    -   `phash_list` (`Optional[list[str]] = None`): **(追加)** 各画像に対応するpHash文字列のリスト。`None` の場合、ライブラリ内部で計算される。`images_list` と同じ長さである必要がある。
-   **前提条件:**
    -   **ライブラリ設定:** `image-annotator-lib` は、`lorairo/config` ディレクトリ内に配置されるユーザー設定ファイル（ファイル名は別途定義）を読み込んで設定を行う。このファイルが存在しない場合は、ライブラリ内部のデフォルト値が使用される。APIキーやプロンプトなどの設定は、このファイルを通じてライブラリ内部で管理されるため、`annotate` 関数呼び出し時には渡さない。(確認事項2 回答反映)

### 2.2. `image-annotator-lib` から `lorairo` への出力

-   **戻り値:** `PHashAnnotationResults` 型 (型エイリアス: `dict[str, dict[str, ModelResultDict]]`)
    -   最上位キー: 画像の pHash 文字列 (または代替キー "unknown_image_{index}")。
    -   中間キー: アノテーションに使用されたモデル名文字列。
    -   値 (`ModelResultDict` 型): 各モデルによるアノテーション結果。
        ```python
        # ModelResultDict の型定義 (image_annotator_lib.api より)
        class ModelResultDict(TypedDict, total=False):
            tags: list[str] | None  # 抽出・整形されたタグリスト (エラー時はNone)
            formatted_output: Any | None # モデルからの生出力に近い整形済みデータ？ (型はAny)
            error: str | None      # エラーメッセージ (成功時はNone)
        ```
-   **注意点:**
    -   **キャプションとスコアは `formatted_output` フィールド内に含まれる想定。`lorairo` 側でこのフィールドをパースして必要な情報を抽出する必要がある。** (確認事項1 回答反映)

## 3. `lorairo` 内部処理

### 3.1. ライブラリ呼び出し

-   担当モジュール: (例: `src/lorairo/annotator_manager.py` の `AnnotatorManager` クラス)
-   処理フロー:
    1.  処理対象の画像リスト (`list[Image.Image]`) を準備。
    2.  **(オプション)** 必要に応じて、各画像のpHashリスト (`list[str]`) を準備。
    3.  GUIまたは設定ファイルからユーザーが選択したモデル名のリスト (`list[str]`) を取得。
    4.  `image_annotator_lib.api.annotate(images_list, model_name_list, phash_list=prepared_phashes)` を呼び出す。 (ライブラリ設定は内部で行われるため、ここでは渡さない)

### 3.2. 結果ハンドリング

-   担当モジュール: (例: `AnnotatorManager` または呼び出し元のデータ処理モジュール)
-   処理フロー:
    1.  ライブラリからの戻り値 (`PHashAnnotationResults` 辞書) を受け取る。
    2.  辞書をイテレートし、各画像のpHashを取得。
    3.  各pHashに対応する内部辞書をイテレートし、各モデル名とその結果 (`ModelResultDict`) を取得。
    4.  各 `ModelResultDict` について:
        a.  `error` フィールドを確認。エラーがあればログ記録、ユーザー通知等の処理を行う。
        b.  エラーがない場合:
            i.  `tags` フィールドからタグリストを取得。
            ii. **`formatted_output` フィールドをパースし、キャプションとスコアを抽出する。** (パースロジックは別途定義が必要)
            iii. 取得したタグ、キャプション、スコア、モデル名、pHash、(pHashから紐づけた)画像パスなどをDB保存用の形式に整形。
            iv. データベースマネージャ等にデータを渡して保存。
            v.  必要に応じてGUIに結果を表示。

## 4. 依存関係

-   `lorairo` は `image-annotator-lib` に依存する。
-   `image-annotator-lib` は各種AI APIライブラリ (`openai`, `anthropic`, `google-generativeai` 等) や `genai-tag-db-tools` に依存する (ライブラリ内部で管理)。(確認事項3 回答反映)

---