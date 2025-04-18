# AIアノテーション Core層仕様書（image-annotator-lib連携・全体設計）

## 1. 目的

AIアノテーション（タグ・キャプション・スコア生成）機能を外部ライブラリ `image-annotator-lib` に委譲し、`lorairo` 本体はデータセット管理・画像処理に集中する。

## 2. 全体像

`lorairo` はAIアノテーション処理を `image-annotator-lib` に委譲します。

```mermaid
graph TD
    subgraph LoRAIro - Interface Layer (GUI)
        A[GUI (例: ImageEditWidget)] -- 1. アノテーション実行指示 (画像リスト, 選択モデル) --> B(AnnotationService);
        B -- 6. 結果/エラー表示 --> A;
    end

    subgraph LoRAIro - Application Layer
        B -- 2. アノテーション実行 (画像リスト, モデルリスト, pHash?) --> C{AnnotatorClient};
        C -- 5. 結果辞書/エラー --> B;
        B -- 7. 整形済みデータ --> D[Database Manager];
    end

    subgraph LoRAIro - Infrastructure Layer
        C -- 3. annotate 呼び出し --> E[image-annotator-lib];
        F[Config Files (lorairo/config)] --> E;
    end

    subgraph External Library
        E -- 4. 結果辞書/エラー --> C;
    end

    style E fill:#f9f,stroke:#333,stroke-width:2px
```

## 3. インターフェース仕様

### 3.1. `lorairo` から `image-annotator-lib` への入力

- **呼び出し関数:** `image_annotator_lib.api.annotate`
- **引数:**
    - `images_list` (`list[Image.Image]`): アノテーション対象の PIL Image オブジェクトのリスト。
    - `model_name_list` (`list[str]`): 使用するAIモデル名のリスト (例: `["gpt-4o", "claude-3-sonnet"]`)。
    - `phash_list` (`Optional[list[str]] = None`): 各画像に対応するpHash文字列のリスト。`None` の場合、ライブラリ内部で計算される。`images_list` と同じ長さである必要がある。
- **前提条件:**
    - **ライブラリ設定:**
      - **APIキー:** `image-annotator-lib` は、APIキーを環境変数（通常はプロジェクトルートの `.env` ファイル経由）から読み込みます。そのため、`annotate` 関数呼び出し時にAPIキーを渡す必要はありません。
      - **その他設定（プロンプト等）:** モデルごとのプロンプトなどの設定は、`image-annotator-lib` 内部のデフォルト値、またはライブラリが独自に読み込む設定ファイル（存在する場合）に基づいて決定されます。`lorairo` 側からこれらの設定を `annotate` 関数を通じて渡す必要はありません。

### 3.2. `image-annotator-lib` から `lorairo` への出力

- **戻り値:** `image_annotator_lib.typing.PHashAnnotationResults` 型
    - この型は `image-annotator-lib` からインポートして使用します。
    - 型定義のイメージ: `dict[str, dict[str, ModelResultDict]]`
    - 最上位キー: 画像の pHash 文字列 (または代替キー "unknown_image_{index}")。
    - 中間キー: アノテーションに使用されたモデル名文字列。
    - 値 (`image_annotator_lib.typing.ModelResultDict` 型): 各モデルによるアノテーション結果。
        ```python
        # ModelResultDict の型定義 (image_annotator_lib.typing よりインポートして使用)
        class ModelResultDict(TypedDict, total=False):
            tags: list[str] | None  # 抽出・整形されたタグリスト (エラー時はNone)
            formatted_output: Any | None # モデルからの生出力に近い整形済みデータ（キャプション・スコア含む）
            error: str | None      # エラーメッセージ (成功時はNone)
        ```
- **注意点:**
    - **キャプションとスコアは `formatted_output` フィールド内に含まれる想定。`lorairo` 側でこのフィールドをパースして必要な情報を抽出する必要がある。**

## 4. 保存先ディレクトリ

- **Interface層:**
  - `src/lorairo/gui/widgets/annotation_widget.py`
- **Application層:**
  - `src/lorairo/services/annotation_service.py`
- **Infrastructure層 (外部ライブラリ連携):**
  - `src/lorairo/annotations/ai_annotator.py` (新規作成)

## 5. 考慮事項

- **エラーハンドリング:** ライブラリ呼び出し時、モデルごとの処理、結果パース時など、各段階でのエラーを適切にハンドリングし、ユーザーに分かりやすく伝える必要がある (例: エラーダイアログ、ログ出力)。
- **設定管理:** `image-annotator-lib` の設定ファイル (API キー、プロンプト等) の形式を明確にし、`lorairo` からどのように管理・参照するかを決定する必要がある (例: GUI から設定可能にするか、設定ファイル直編集か)。