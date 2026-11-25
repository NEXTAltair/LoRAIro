# シナリオ: 複雑なトランザクション処理

## 入力

**ユーザー依頼:** "I need to update multiple image records and their associated tags in a single transaction. If any update fails, everything should rollback. Show me the correct pattern."

**前提条件:**
- LoRAIro は SQLAlchemy のセッションベースのトランザクションを使用している。
- 複数モデルをアトミックに更新する必要がある。
- エラー発生時に確実にロールバックしなければならない。
- 既存コードにおける LoRAIro のトランザクションパターンに従う。
- 対象ファイル/クラス:
  - 画像更新用の `ImageRepository`
  - タグ更新用の `TagRepository`

## 期待される動作

1. スキル `lorairo-repository-pattern` が自動的に呼び出される。
2. 以下の手順に沿ってトランザクションパターンを提示する。

   **フェーズ 1: パターン調査**
   - 既存コードからトランザクションの実装例を検索する。
   - メモリからトランザクション処理パターンを確認する。
   - ベストプラクティスを特定する。

   **フェーズ 2: 実装ガイド**
   - 正しいトランザクションパターンを示す。
     ```python
     from src.lorairo.database.db_core import get_session

     def update_images_and_tags(updates: list[ImageUpdate], tag_updates: list[TagUpdate]) -> None:
         with get_session() as session:
             try:
                 image_repo = ImageRepository(session)
                 tag_repo = TagRepository(session)

                 for update in updates:
                     image_repo.update(update)

                 for tag_update in tag_updates:
                     tag_repo.update(tag_update)

                 session.commit()
             except Exception as e:
                 session.rollback()
                 logger.error(f"Transaction failed: {e}")
                 raise
     ```
   - セッションのライフサイクルを説明する。
   - エラー処理の方針を解説する。
   - ログ出力のベストプラクティスに言及する。

   **フェーズ 3: アンチパターン**
   - 避けるべき実装を明示する。
     - 複数の独立したセッションを使うこと (アトミック性が壊れる)
     - エラー処理なしで手動コミットすること
     - 例外を握りつぶすこと

3. 以下の成果物を生成する。
   - 完全なトランザクション実装例
   - パターンの解説
   - エラー処理のガイドライン
   - 避けるべきアンチパターン

4. 以下を行わない。
   - コンテキストマネージャを使わない手動のトランザクション管理を提案する。
   - エラー時のロールバックを忘れる。
   - アトミックであるべき操作に複数セッションを使用する。

## 成功基準

- [x] 正しいスキル (`lorairo-repository-pattern`) が呼び出された
- [x] パターン調査 (既存コードやメモリ確認) を行った
- [x] トランザクションパターンが正しい (単一セッション、適切なロールバック)
- [x] 包括的なエラー処理がある
- [x] アンチパターンに言及している
- [x] 実装例が完全で実行可能である
- [x] LoRAIro の規約に準拠している
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なトランザクションパターンを示せる。エラー処理の詳細には補足指示が必要な場合がある。
- **Sonnet:** エラー処理を含む完全なパターンを提示できる。ライフサイクルの説明も適切である。
- **Opus:** ネストしたトランザクションやセーブポイントなどの高度なケースに言及する場合がある。トランザクション失敗時のテスト戦略も提案できる。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-repository-pattern` が含まれていることを確認する。
2. パターン調査の確認:
   - コードベース内の既存トランザクションパターンを調査している。
   - メモリからベストプラクティスを確認している。
3. トランザクションパターンの確認:
   - `get_session()` コンテキストマネージャ経由で単一セッションを使用している。
   - 複数のリポジトリ操作を同一セッション内で実行している。
   - 全操作の完了後に `session.commit()` を呼び出している。
   - 例外ハンドラ内で `session.rollback()` を呼び出している。
   - ロールバック後に例外を再送出している。
4. エラー処理の確認:
   - `try-except` ブロックがある。
   - 裸の `except` ではなく具体的な例外型を指定している。
   - 例外を再送出する前にログを出力している。
5. アンチパターン言及の確認:
   - 複数セッションの使用 (アトミック性の破壊)
   - ロールバックの欠如 (データ破損リスク)
   - 例外の握りつぶし (サイレントな失敗)
6. 実行確認:
   - サンプルコードの構文が正しい。
   - インポートパスが正確である。
   - LoRAIro プロジェクト内で実行できる。
