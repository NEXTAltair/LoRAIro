# シナリオ: 結合とフィルタリングを含む複雑クエリ

## 入力

**ユーザー依頼:** "I need to query images that have specific tags AND were annotated after a certain date. The query should use SQLAlchemy ORM with proper joins. Show me the repository method pattern."

**前提条件:**
- 複雑クエリの要件は以下の通りである。
  - 結合: `Images` -> `ImageTags` -> `Tags`
  - フィルタ: タグ名が指定リストに含まれること
  - フィルタ: アノテーション日時がしきい値より後であること
  - 戻り値: `Image` モデルのリスト
- 生 SQL ではなく SQLAlchemy ORM を使用する。
- 型安全な戻り値とする。
- N+1 問題を避け、適切な結合による効率的なクエリにする。

## 期待される動作

1. スキル `lorairo-repository-pattern` が自動的に呼び出される。
2. 以下の手順に沿って複雑クエリパターンを提示する。

   **フェーズ 1: パターン調査**
   - リポジトリ内の既存複雑クエリを検索する。
   - メモリから結合パターンを確認する。
   - SQLAlchemy のベストプラクティスを確認する。

   **フェーズ 2: 実装**
   - 適切なリポジトリメソッドを示す。
     ```python
     def find_by_tags_and_date(
         self,
         tag_names: list[str],
         after_date: datetime,
     ) -> list[Image]:
         """
         Find images with specific tags annotated after date.

         Args:
             tag_names: List of tag names to filter by
             after_date: Minimum annotation date

         Returns:
             List of matching Image models
         """
         return (
             self.session.query(Image)
             .join(ImageTag, Image.id == ImageTag.image_id)
             .join(Tag, ImageTag.tag_id == Tag.id)
             .filter(Tag.name.in_(tag_names))
             .filter(Image.annotated_at > after_date)
             .distinct()
             .all()
         )
     ```
   - 結合戦略を説明する。
   - 多対多リレーションにおける `.distinct()` の必要性を解説する。
   - 引数と戻り値の型ヒントを明記する。

   **フェーズ 3: 最適化の補足**
   - リレーション先データが必要な場合の Eager Loading に言及する。
   - クエリパフォーマンス上の考慮点を説明する。
   - データベースインデックスの追加を提案する。

3. 以下の成果物を生成する。
   - 完全なリポジトリメソッド
   - 適切な SQLAlchemy ORM クエリ
   - 型安全な実装
   - パフォーマンス上の考慮点
   - 避けるべきアンチパターン

4. 以下を行わない。
   - ORM ではなく生 SQL を使用する。
   - 結果リストではなくクエリオブジェクトを返す。
   - N+1 クエリ問題を引き起こす。
   - 型ヒントを省略する。

## 成功基準

- [x] 正しいスキル (`lorairo-repository-pattern`) が呼び出された
- [x] パターン調査 (既存クエリの調査) を行った
- [x] SQLAlchemy ORM クエリが正しい
- [x] 結合が適切で N+1 が発生しない
- [x] 型ヒントが付与されている
- [x] Google スタイルの docstring がある
- [x] パフォーマンス上の考慮点に言及している
- [x] エラーなく完了する

## モデル別の傾向

- **Haiku:** 基本的なクエリを作成できる。結合や `distinct()` の使い方には補足指示が必要な場合がある。
- **Sonnet:** 適切な結合を備えた完全なクエリを作成できる。型ヒントと docstring の品質が高い。
- **Opus:** クエリ最適化戦略を提案し、Eager Loading の追加やデータベースインデックスの推奨まで自発的に行う場合がある。

## テスト検証

このシナリオの実行後、以下の項目を確認する。

1. スキル呼び出しの確認: メタデータに `lorairo-repository-pattern` が含まれていることを確認する。
2. パターン調査の確認:
   - 既存の複雑クエリを調査している。
   - メモリから結合パターンを確認している。
3. クエリ構造の確認:
   - 生 SQL ではなく `self.session.query(Image)` (ORM) を使用している。
   - `Image` -> `ImageTag` -> `Tag` の結合が適切である。
   - フィルタ条件が正しい。
   - 多対多の重複排除に `.distinct()` を使用している。
   - `.all()` (`list[Image]`) を返している。
4. 型安全性の確認:
   - 引数型が `list[str]`、`datetime` である。
   - 戻り値型が `list[Image]` である。
   - `Any` 型を使用していない。
5. ドキュメントの確認:
   - Google スタイルの docstring が記述されている。
   - `Args` セクションに型と説明がある。
   - `Returns` セクションに型と説明がある。
6. クエリ正当性の検証 (可能な場合):
   - 実際のデータベースで実行できる。
   - 期待通りの結果を返す。
   - SQLAlchemy のクエリログで N+1 クエリが発生していないことを確認する。

## 検証すべきエッジケース

- `tag_names` が空リストの場合 (安全に処理できること)
- 存在しないタグが指定された場合 (空リストを返すこと)
- 複数の該当タグを持つ画像がある場合 (`distinct()` で重複を防ぐこと)
- 大規模データセットでのパフォーマンス (インデックス設計への言及)
