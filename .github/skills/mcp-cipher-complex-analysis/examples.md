# Cipher Complex Analysis - 使用例

## Example 1: 設計前の過去事例調査

### シナリオ
新しいGUIウィジェット間通信機能を設計する前に、過去の類似実装パターンを調査したい。

### 手順
```
1. 過去の設計パターンを検索:
   cipher_memory_search(
     query="widget communication pattern direct signal slot"
   )

   結果: 過去の「Direct Widget Communication」パターンの設計判断が見つかる
   - DatasetStateManager経由の間接通信から直接Signal/Slot接続への移行
   - パフォーマンス向上（3段階→1段階）
   - コード簡素化（150行削減）

2. 設計要素を抽出:
   cipher_extract_entities(
     text="[過去の設計ドキュメント]"
   )

   結果: ThumbnailSelectorWidget, SelectedImageDetailsWidget,
        image_metadata_selected シグナル などの重要要素を特定

3. 依存関係を分析:
   cipher_query_graph(
     query="ThumbnailSelectorWidget dependencies"
   )

   結果: 関連コンポーネントと影響範囲が明確化
```

## Example 2: ライブラリ調査（context7経由）

### シナリオ
PySide6のQThreadとQRunnableの違いを理解し、LoRAIroでの最適な使い方を決定したい。

### 手順
```
1. ライブラリIDを解決:
   mcp__context7__resolve-library-id(
     library_name="pyside6"
   )

   結果: library_id="pyside6_6_8"

2. 公式ドキュメントを取得:
   mcp__context7__get-library-docs(
     library_id="pyside6_6_8",
     section="threading"
   )

   結果: QThread vs QRunnable の公式ガイド
   - QThread: 長時間実行タスク、状態管理が必要
   - QRunnable: 軽量タスク、QThreadPoolで管理

3. ベストプラクティスを検索:
   WebSearch(
     query="pyside6 qrunnable qthreadpool best practices 2025"
   )

   結果: 最新の実装例とパターン

4. 判断を長期記憶化:
   cipher_store_reasoning_memory(
     title="LoRAIro非同期処理パターン選択",
     content='''
## 判断内容
QRunnableとQThreadPoolを採用

## 根拠
- 軽量タスクが多い（画像処理、DB操作）
- PoolによるリソーHumanagement
- LoRAIroWorkerBaseパターンとの統合容易

## 実装結果
- WorkerManagerでQThreadPool管理
- 各WorkerはQRunnable継承
- プログレス通知はSignalで実装

## 教訓
- QThreadは状態管理が複雑
- QRunnableで十分な性能
'''
   )
```

## Example 3: SQLAlchemyリポジトリパターン調査

### シナリオ
データベースアクセス層の最適な設計パターンを調査したい。

### 手順
```
1. 過去の実装を検索:
   cipher_memory_search(
     query="repository pattern sqlalchemy transaction management"
   )

   結果: 既存のImageRepositoryパターンが見つかる

2. SQLAlchemyのベストプラクティスを調査:
   mcp__context7__resolve-library-id(library_name="sqlalchemy")
   → library_id="sqlalchemy_2_0"

   mcp__context7__get-library-docs(
     library_id="sqlalchemy_2_0",
     section="orm/session"
   )

   結果: Session管理、トランザクション、コンテキストマネージャーの使い方

3. 設計判断を記録:
   cipher_store_reasoning_memory(
     title="LoRAIro Repository Pattern設計",
     content='''
## アプローチ
- リポジトリパターンでデータアクセス抽象化
- session_factory()でSession管理
- with文によるトランザクション自動管理

## 技術選定
- SQLAlchemy 2.0 ORM
- コンテキストマネージャーでSession制御
- 型ヒントによる安全性確保

## 実装例
class ImageRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_images_by_criteria(self, criteria):
        with self.session_factory() as session:
            # トランザクション自動管理
            return session.query(Image).filter(...).all()

## 効果
- ビジネスロジックとデータアクセスの分離
- テスタビリティ向上（モックRepository作成容易）
- トランザクション管理の一元化
'''
   )
```

## Example 4: 複数ライブラリの比較調査

### シナリオ
画像品質評価ライブラリの選定（CLIP vs MUSIQ）を行いたい。

### 手順
```
1. 両ライブラリの調査:
   WebSearch(query="CLIP aesthetic scoring vs MUSIQ image quality 2025")
   WebFetch(url="[検索結果の詳細記事]")

2. 設計要素を抽出:
   cipher_extract_entities(
     text="[取得した技術記事]"
   )

   結果: CLIP（美的スコア）、MUSIQ（技術品質）の違いを特定

3. 選定判断を記録:
   cipher_store_reasoning_memory(
     title="画像品質評価ライブラリ選定",
     content='''
## 評価結果
- CLIP: 美的感覚（構図、色彩、魅力度）
- MUSIQ: 技術品質（解像度、ノイズ、歪み）

## 判断
両方を採用し、目的に応じて使い分け

## 実装
- CLIPスコア: ユーザー選好予測
- MUSIQスコア: 技術的品質フィルタリング
- スコアリングモジュール: src/lorairo/score_module/

## 教訓
- 単一スコアでは不十分
- 多面的評価でより正確な判断
'''
   )
```

## Example 5: アーキテクチャ影響分析

### シナリオ
DatasetStateManagerの大規模リファクタリング前に影響範囲を分析したい。

### 手順
```
1. 設計要素を抽出:
   cipher_extract_entities(
     text="DatasetStateManager リファクタリング計画:
           - データキャッシュ機能削除
           - UI状態管理のみに特化
           - Direct Widget Communication採用"
   )

   結果: DatasetStateManager, ThumbnailSelectorWidget,
        SelectedImageDetailsWidget などを特定

2. 依存関係を分析:
   cipher_query_graph(
     query="DatasetStateManager relationships"
   )

   結果: 依存コンポーネントと影響範囲の可視化

3. 過去の類似リファクタリングを検索:
   cipher_memory_search(
     query="refactoring state manager cache removal"
   )

   結果: 過去の類似変更での課題と解決策

4. リファクタリング判断を記録:
   cipher_store_reasoning_memory(
     title="DatasetStateManager簡素化リファクタリング",
     content='''
## 課題
- データキャッシュ重複（3箇所）
- 複雑な間接フロー（3段階）
- レスポンス低下

## アプローチ
- キャッシュ統一: ThumbnailSelectorWidgetのimage_metadataに一本化
- Direct Communication: Signal/Slot直接接続
- 責任分離: DatasetStateManagerはUI状態のみ

## 影響範囲
- DatasetStateManager: 150行削除
- ThumbnailSelectorWidget: image_metadata_selectedシグナル追加
- SelectedImageDetailsWidget: connect_to_thumbnail_widget()追加
- テスト: Phase 3対応に更新

## 結果
- パフォーマンス向上（3段階→1段階）
- コード削減（ネット67行）
- 保守性向上
'''
   )
```

## Example 6: Cipher + Serena併用パターン

### シナリオ
効率的な開発フローで新機能を実装したい。

### 手順
```
実装フロー:

1. [Serena] 現在状況確認:
   mcp__serena__read_memory(memory_file_name="current-project-status")

2. [Cipher] 過去事例検索:
   cipher_memory_search(query="similar feature implementation")

3. [Cipher] ライブラリ調査:
   mcp__context7__get-library-docs(library_id="pyside6_6_8")

4. [Serena] 既存コード確認:
   mcp__serena__find_symbol(name_path="TargetClass")

5. [Serena] コード実装:
   mcp__serena__replace_symbol_body(...)

6. [Serena] 進捗記録:
   mcp__serena__write_memory(memory_name="active-development-tasks")

7. [Cipher] 長期記憶化:
   cipher_store_reasoning_memory(title="実装パターンと判断")

結果: 高速操作と戦略的分析の最適な組み合わせ
```

## ベストプラクティス

### 効率的な Cipher 使用
1. **具体的クエリ**: 検索は具体的なキーワードで（"pattern", "best practice"等）
2. **段階的調査**: Memory → context7 → WebSearch の順で調査
3. **必ず記録**: 重要な判断は cipher_store_reasoning_memory で永続化

### タイムアウト回避
- **並行実行回避**: Cipher操作は順次実行
- **検索範囲絞り込み**: クエリを具体化
- **Serenaフォールバック**: タイムアウト時は Serena + WebSearch

### LoRAIro固有
- **アーキテクチャ判断**: 必ず cipher_store_reasoning_memory で記録
- **技術選定**: context7 で公式ドキュメント確認後に決定
- **リファクタリング**: cipher_query_graph で影響分析してから実行
