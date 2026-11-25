# シナリオ: 機能ワークフローの統合テストスイート

## 入力

**ユーザー依頼:** "Create integration tests for the image annotation workflow: select image -> run annotation worker -> save results -> update database. Test the full end-to-end flow."

**前提条件:**
- LoRAIro の統合テスト要件は以下の通りである。
  - pytest フレームワーク
  - `@pytest.mark.integration` マーカー
  - 複数コンポーネントを連携させた検証
  - 実データベース (SQLite テスト DB) の使用
  - ワーカー実行 (AI API にはモックを使用可)
  - 主要パスに対する 75% 以上のカバレッジ
- 対象コンポーネント:
  - `ImageRepository` (データベース層)
  - `AnnotationWorker` (非同期ワーカー)
  - `AnnotationService` (ビジネスロジック)
  - `WorkerManager` (ワーカー実行管理)
- テスト配置場所: `tests/integration/`

## 期待される動作

1. スキル `lorairo-test-generator` が自動的に呼び出される。
2. 以下の手順に沿って統合テスト作成を案内する。

   **フェーズ 1: パターン調査**
   - 既存の統合テストを調べる。
   - メモリからワークフローテストのパターンを確認する。
   - アノテーションフローに関わるコンポーネント構成を確認する。

   **フェーズ 2: フィクスチャの作成**
   - テスト用データベースフィクスチャ (一時 SQLite) を作成する。
   - テストデータ付きのリポジトリフィクスチャを作成する。
   - サービス/ワーカー用のフィクスチャを作成する。
   - クリーンアップ用フィクスチャを作成する。

   **フェーズ 3: 統合テストの実装**
   - フルワークフローテスト:
     ```python
     @pytest.mark.integration
     def test_annotation_workflow_success(
         test_db,
         image_repository,
         annotation_service,
         sample_image_file,
         mock_openai_api
     ):
         # Arrange
         image = image_repository.create(Image(path=sample_image_file))
         assert image.annotation_status == "pending"

         # Act
         # Step 1: Run annotation
         annotation_service.annotate_image(image.id)

         # Step 2: Wait for worker completion (or use synchronous version)
         # (In real integration test, may need to wait or use callbacks)

         # Step 3: Verify results saved
         updated_image = image_repository.get_by_id(image.id)

         # Assert
         assert updated_image.annotation_status == "completed"
         assert updated_image.caption is not None
         assert len(updated_image.tags) > 0
     ```

   - エラー処理テスト:
     ```python
     @pytest.mark.integration
     def test_annotation_workflow_api_failure(
         test_db,
         image_repository,
         annotation_service,
         sample_image_file,
         mock_openai_api_failure
     ):
         # Arrange
         image = image_repository.create(Image(path=sample_image_file))

         # Act
         with pytest.raises(AnnotationError):
             annotation_service.annotate_image(image.id)

         # Assert
         updated_image = image_repository.get_by_id(image.id)
         assert updated_image.annotation_status == "failed"
     ```

   **フェーズ 4: カバレッジ検証**
   - 統合テストの実行を提案する。
   - 主要パスが網羅されていることを確認する。
   - データベース状態の整合性を確認する。

3. 以下の成果物を生成する。
   - 完全な統合テストスイート
   - エンドツーエンドのワークフローテスト
   - エラー処理テスト
   - データベース整合性の検証
   - 外部 API の適切なモック化
   - クリーンアップ用フィクスチャ

4. 以下を行わない。
   - データベースのクリーンアップを省略する (テスト独立性を損なう)。
   - エラーケースを忘れる。
   - 本番データベースを使用する。
   - 外部サービスのモック化を省略する (低速かつ不安定になる)。

## 成功基準

- [x] 正しいスキル (`lorairo-test-generator`) が呼び出された
- [x] パターン調査 (既存統合テストの確認) を行った
- [x] テスト用データベースフィクスチャが作成されている
- [x] フルワークフローがエンドツーエンドでテストされている
- [x] エラーケースがテストされている
- [x] データベース状態が検証されている
- [x] 外部 API が適切にモック化されている
- [x] `@pytest.mark.integration` マーカーが付与されている
- [x] クリーンアップによりテスト独立性が保たれている
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的な統合テストを作成できる。フィクスチャ設計やモック化には補足指示が必要な場合がある。
- **Sonnet:** 包括的な統合テストスイートを作成できる。ワークフロー網羅性とエラー処理の品質が高い。
- **Opus:** 並行処理や競合状態などの追加シナリオを提案する場合がある。フィクスチャ構造とテスト独立性の設計に優れる。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-test-generator` が含まれていることを確認する。
2. テストデータベースフィクスチャの確認:
   - 一時 SQLite データベースが作成されている。
   - スキーマが初期化されている。
   - テスト後にクリーンアップされる。
3. ワークフロー網羅性の確認:
   - 正常系パス: 選択 -> アノテーション実行 -> 保存 -> 検証
   - 異常系パス: API エラー -> ステータス更新 -> エラーログ出力
4. コンポーネント連携の確認:
   - データベース操作にリポジトリが使用されている。
   - ワーカーが実行されている (または適切にモック化されている)。
   - サービスがワークフロー全体を調整している。
5. モック化の検証:
   - 外部 API (OpenAI、Anthropic) がモック化されている。
   - モックレスポンスが現実的である。
   - モックで失敗ケースを再現およびテストできる。
6. テスト独立性の確認:
   - 各テストが独立して動作する。
   - テスト間でデータベース状態がリセットされる。
   - 前のテストからの副作用が残らない。
7. 統合テストの実行:
   ```bash
   uv run pytest tests/integration/ -m integration --cov=src/lorairo
   ```
8. 実行結果の確認:
   - すべてのテストがパスする。
   - 主要パスが 75% 以上カバーされている。
   - テスト後にデータベースの整合性が保たれている。

## 検証すべきエッジケース

- 並行したアノテーション要求 (ワーカープーリング)
- 大容量画像ファイル (タイムアウト処理)
- データベース接続失敗 (リトライロジック)
- ワークフローの途中失敗 (クリーンアップ/ロールバック)
- 実行途中でのワーカーキャンセル
