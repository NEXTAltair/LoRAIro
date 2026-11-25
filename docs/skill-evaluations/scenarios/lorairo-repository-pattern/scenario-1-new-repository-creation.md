# シナリオ: パターンに沿った新規リポジトリ作成

## 入力

**ユーザー依頼:** "Create a new ExportConfigRepository for managing export configuration settings. Follow the LoRAIro repository pattern like ImageRepository and TagRepository."

**前提条件:**
- LoRAIro はデータアクセス層にリポジトリパターンを採用している。
- 既存の実装パターン: `src/lorairo/database/repositories/` 配下の `ImageRepository`、`TagRepository`
- 使用すべき技術と方針は以下の通りである。
  - SQLAlchemy ORM
  - 型安全なトランザクション
  - `db_core` 経由のセッション管理
  - 一貫したエラー処理
- 対象: `ExportConfig` モデル用の新規リポジトリ

## 期待される動作

1. スキル `lorairo-repository-pattern` が自動的に呼び出される。
2. 以下の手順に沿ってリポジトリ作成ワークフローを案内する。

   **フェーズ 1: 既存パターンの調査**
   - `Grep` を使用して `ImageRepository` または `TagRepository` を検索する。
   - 構造、メソッド構成、セッション管理の実装を分析する。
   - 踏襲すべき共通パターンを特定する。

   **フェーズ 2: パターンに沿った実装**
   - `ExportConfigRepository` クラスを作成する。
   - CRUD メソッド (`create`、`get_by_id`、`update`、`delete`) を実装する。
   - セッション管理を組み込む。
   - すべてのメソッドに型ヒントを付与する。
   - 適切なエラー処理を実装する。

   **フェーズ 3: テスト作成**
   - 既存パターンに沿ったテストの作成を提案する。
   - 既存リポジトリテストの pytest フィクスチャを参照する。

3. 以下の成果物を生成する。
   - 完全なリポジトリ実装
   - LoRAIro のパターンと一貫した設計
   - 型安全でドキュメントが整備されたコード
   - テスト作成の推奨事項

4. 以下を行わない。
   - 既存リポジトリと異なる独自パターンを作る。
   - ORM ではなく生 SQL を使用する。
   - エラー処理を省略する。
   - 型ヒントを付け忘れる。

## 成功基準

- [x] 正しいスキル (`lorairo-repository-pattern`) が呼び出された
- [x] 実装前に既存リポジトリを調査した
- [x] 実装が LoRAIro の規約に準拠している
- [x] すべての CRUD メソッドが含まれている
- [x] 型ヒントが付与されている
- [x] エラー処理が既存コードと一貫している
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なリポジトリを作成できる。セッション管理やエラー処理には補足指示が必要な場合がある。
- **Sonnet:** すべてのパターンに従った完全なリポジトリを作成できる。既存コードとの一貫性が高い。
- **Opus:** CRUD 以外の追加メソッドを提案したり、クエリパターンを最適化したりする場合がある。パターン準拠度が極めて高い。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-repository-pattern` が含まれていることを確認する。
2. 調査フェーズの確認:
   - `find_symbol` を使用して `ImageRepository` または `TagRepository` を調べている。
   - 実装前に既存パターンを分析している。
3. リポジトリ構造の確認:
   ```python
   class ExportConfigRepository:
       def __init__(self, session: Session): ...
       def create(self, config: ExportConfig) -> ExportConfig: ...
       def get_by_id(self, config_id: int) -> ExportConfig | None: ...
       def update(self, config: ExportConfig) -> ExportConfig: ...
       def delete(self, config_id: int) -> bool: ...
   ```
4. 既存リポジトリとの一貫性の確認:
   - セッション管理が `ImageRepository` と同じである。
   - エラー処理が `TagRepository` と同じである。
   - 型ヒントがプロジェクト規約に合致している。
5. コード品質の確認:
   - `# type: ignore` コメントがない。
   - 適切な docstring (Google スタイル) が記述されている。
   - 適切な箇所でログ出力を行っている。
