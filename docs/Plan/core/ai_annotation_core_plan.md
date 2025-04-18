# AIアノテーション Core層計画書・統合チェックリスト

## 1. 目的
- 画像アノテーション機能の外部委譲（image-annotator-lib）とlorairo本体の責務分離を徹底する。
- AIアノテーション機能（タグ、キャプション、スコア生成）を外部ライブラリ `image-annotator-lib` に完全に委譲し、lorairo本体はデータセット管理と画像処理に集中させる。

## 2. 設計方針
- APIインターフェース仕様の明確化
- データ構造・型定義の標準化
- 外部ライブラリとの連携ポイントの明示
- 設定ファイル・モデル管理の一元化
- 既存コードの整理・不要部分の削除

## 3. マイルストーン
- [ ] APIインターフェース仕様の確定
- [ ] 型定義・データ構造の標準化
- [ ] 外部ライブラリ連携テスト
- [ ] 設定ファイル管理方式の確立
- [ ] エラー・例外設計のレビュー
- [ ] 既存コードの整理・不要部分の削除

## 4. 主要タスク
- [ ] **ライブラリ呼び出しクライアント作成**（Infrastructure / AnnotatorClient新規）
    - `image-annotator-lib` API呼び出し、エラーハンドリング
- [ ] **アノテーションサービス実装/修正**（Application / AnnotationService新規/修正）
    - AnnotatorClient利用、結果パースロジック（formatted_output）、DB連携、エラーハンドリング
- [ ] **GUI連携実装/修正**（Interface / ImageEditWidget, MainWindow等）
    - AnnotationService利用、モデル選択UI、非同期処理、進捗・結果・エラー表示
- [ ] **既存コード整理**（Core / ImageAnalyzer, APIClientFactory, TagCleaner等）
    - 仕様書に基づき不要なコードを削除・修正
- [ ] **image-annotator-lib 設定管理**（Infrastructure / ConfigurationService?）
    - lorairo/config内の設定ファイル形式定義、GUIからの設定変更要否検討
- [ ] **結果パースロジック実装**（Application / AnnotationService）
    - image-annotator-libのformatted_outputの具体的な形式確認（キャプション、スコア抽出）
- [ ] **テストコード作成/更新**（Tests / 各層に対応するテストクラス）
    - AnnotatorClient, AnnotationService, GUI連携部分のユニットテスト・結合テスト
- [ ] **ドキュメント更新**（Docs / 本計画書・仕様書）
    - 計画の変更点、実装の詳細、設定ファイル形式などを反映

## 5. 詳細チェックリスト

### API設計
- [ ] `image_annotator_lib.api.annotate` のインターフェース仕様が明確か
- [ ] 型定義（ModelResultDict, PHashAnnotationResults, AnnotationResult等）が統一されているか
- [ ] 返却値の構造（pHash→モデル名→結果）がドキュメント通りか

### 責務分離
- [ ] core層は「連携仕様・型定義・責務分離」のみを担い、実装詳細は他層に委譲しているか
- [ ] 外部ライブラリとの境界が明確か

### 設定管理
- [ ] annotator_config.toml等の設定ファイル仕様が明確か
- [ ] モデル追加・変更時の手順が明文化されているか
- [ ] デバイス・パス・クラス指定等の必須項目が網羅されているか

### 例外・エラー設計
- [ ] 主要な例外（ApiKeyMissingError, WebApiError等）が定義されているか
- [ ] エラー発生時の返却値仕様が明確か
- [ ] ロギング・トレースバックの方針が明文化されているか

### 外部連携
- [ ] WebAPI/ローカルモデル等、各種アノテーターの連携方式が統一されているか
- [ ] モデルごとの初期化・推論・後処理の流れが標準化されているか

### ドキュメント・テスト
- [ ] 仕様変更時にドキュメントが必ず更新されているか
- [ ] 主要API・型定義にdocstringが付与されているか
- [ ] 連携テスト・型チェックが自動化されているか

## 6. 考慮事項
- 非同期処理：アノテーションは時間がかかるため、GUIがフリーズしないよう必ず非同期で実行し、進捗をユーザーにフィードバックする。
- エラーハンドリング：ライブラリ呼び出し時、モデルごとの処理、結果パース時など、各段階でのエラーを適切にハンドリングし、ユーザーに分かりやすく伝える。
- 設定管理：image-annotator-lib の設定ファイル（APIキー、プロンプト等）の形式を明確にし、lorairo からどのように管理・参照するかを決定する（例：GUIから設定可能にするか）。
- 結果パース：image-annotator-lib が返す formatted_output の具体的なデータ構造を確認し、キャプションやスコアを安定して抽出できるロジックを実装する。

## 7. 参考
- image-annotator-lib: api.py, core/base.py, model_class/annotator_webapi.py, resources/system/annotator_config.toml
- [全体リファクタリング計画](../../refactoring_plan.md)
- [コア層仕様](../../specs/core/)

---

（本ドキュメントはcore層観点のAIアノテーション統合計画・チェックリストの統合版です） 