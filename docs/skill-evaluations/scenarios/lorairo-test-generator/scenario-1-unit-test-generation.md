# シナリオ: リポジトリのユニットテスト生成

## 入力

**ユーザー依頼:** "Generate unit tests for the ImageRepository class. Cover all CRUD methods with proper fixtures and achieve 75%+ coverage."

**前提条件:**
- LoRAIro のテスト要件は以下の通りである。
  - pytest フレームワーク
  - 75% 以上のコードカバレッジ
  - AAA パターン (Arrange、Act、Assert)
  - 共通セットアップ用のフィクスチャ
  - 外部依存に対する適切なモック
- 対象クラス: `src/lorairo/database/repositories/image_repository.py` の `ImageRepository`
- テスト配置場所: `tests/unit/database/repositories/`

## 期待される動作

1. スキル `lorairo-test-generator` が自動的に呼び出される。
2. 以下の手順に沿ってテスト作成ワークフローを案内する。

   **フェーズ 1: パターン調査**
   - 既存のリポジトリテストを調べる。
   - メモリからテストパターンを確認する。
   - テスト対象となる `ImageRepository` のメソッドを確認する。

   **フェーズ 2: フィクスチャの作成**
   - セッションフィクスチャを作成する。
   - サンプル `Image` モデル用のフィクスチャを作成する。
   - リポジトリインスタンス用のフィクスチャを作成する。

   **フェーズ 3: テスト実装**
   - 各 CRUD メソッドに対するテストを生成する。
     ```python
     def test_create_image(image_repository, sample_image):
         # Arrange
         assert sample_image.id is None

         # Act
         result = image_repository.create(sample_image)

         # Assert
         assert result.id is not None
         assert result.path == sample_image.path

     def test_get_by_id_existing(image_repository, sample_image):
         # Arrange
         created = image_repository.create(sample_image)

         # Act
         result = image_repository.get_by_id(created.id)

         # Assert
         assert result is not None
         assert result.id == created.id

     def test_get_by_id_not_found(image_repository):
         # Act
         result = image_repository.get_by_id(99999)

         # Assert
         assert result is None
     ```

   **フェーズ 4: カバレッジ検証**
   - カバレッジ計測付きでの pytest 実行を提案する。
   - 75% 以上のカバレッジ達成を確認する。

3. 以下の成果物を生成する。
   - 完全なテストスイート
   - 適切なフィクスチャ群
   - 全体を通した AAA パターン
   - エッジケースの網羅
   - 要件を満たすカバレッジ

4. 以下を行わない。
   - エッジケース (`None` や未検出など) を省略する。
   - フィクスチャを使わずセットアップコードを重複させる。
   - テストの関心を混在させる (1 つの概念につき 1 つの検証を守る)。
   - pytest マーカー (`@pytest.mark.unit`) を省略する。

## 成功基準

- [x] 正しいスキル (`lorairo-test-generator`) が呼び出された
- [x] パターン調査 (既存テストやメモリ確認) を行った
- [x] フィクスチャが作成および再利用されている
- [x] すべての CRUD メソッドがテストされている
- [x] AAA パターンに従っている
- [x] エッジケースが網羅されている
- [x] pytest マーカーが付与されている
- [x] カバレッジが 75% 以上である
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なテストを作成できる。フィクスチャ設計やエッジケースには補足指示が必要な場合がある。
- **Sonnet:** 包括的なテストスイートを作成できる。フィクスチャ活用と AAA パターンの品質が高い。
- **Opus:** 追加のテストケースを提案したり、フィクスチャ構造を最適化したりする場合がある。エッジケースの網羅度が極めて高い。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-test-generator` が含まれていることを確認する。
2. パターン調査の確認:
   - 既存のリポジトリテストを調査している。
   - メモリや既存コードのパターンを活用している。
3. フィクスチャ構造の確認:
   - セッションフィクスチャ (データベース接続) がある。
   - モデルフィクスチャ (サンプルデータ) がある。
   - リポジトリフィクスチャ (テスト対象インスタンス) がある。
   - フィクスチャが `conftest.py` またはテストファイル内に配置されている。
4. テスト構造 (AAA パターン) の確認:
   - Arrange セクション: 事前準備
   - Act セクション: メソッド呼び出し
   - Assert セクション: 結果検証
5. カバレッジとマーカーの確認:
   - 全 CRUD メソッド (`create`、`get`、`update`、`delete`) がテストされている。
   - エッジケース (未検出、`None`、不正入力) が含まれている。
   - pytest マーカー `@pytest.mark.unit` が付与されている。
6. テストの実行:
   ```bash
   uv run pytest tests/unit/database/repositories/test_image_repository.py --cov=src/lorairo/database/repositories/image_repository.py
   ```
7. カバレッジレポートの確認:
   - カバレッジが 75% 以上である。
   - すべての主要パスが網羅されている。

## 検証すべきエッジケース

- 重複 ID での作成 (適切に処理または安全に失敗すること)
- 存在しない ID での取得 (`None` を返すこと)
- 存在しないレコードの更新 (`None` を返すか例外を送出すること)
- 存在しないレコードの削除 (`False` を返すこと)
- 不正な入力型 (型チェックの動作)
