# Cipher Complex Analysis - APIリファレンス

## 設計知識検索ツール

### cipher_memory_search
過去の設計判断、実装パターン、技術的教訓を検索。

**パラメータ:**
- `query` (string, 必須): 検索クエリ
- `limit` (integer, オプション): 取得結果数（デフォルト: 5）

**戻り値:**
関連する過去の記憶（タイトル、コンテキスト、内容）のリスト

**使用例:**
```python
cipher_memory_search(
    query="repository pattern sqlalchemy transaction",
    limit=3
)
```

**最適な検索クエリ:**
- "widget communication pattern"
- "database transaction management"
- "async worker pattern qthread"
- "refactoring state manager"

---

### cipher_extract_entities
テキストから重要な設計要素、技術概念を抽出。

**パラメータ:**
- `text` (string, 必須): 分析対象テキスト
- `entity_types` (array[string], オプション): 抽出するエンティティタイプ

**戻り値:**
抽出されたエンティティのリスト（名前、タイプ、コンテキスト）

**使用例:**
```python
cipher_extract_entities(
    text='''
    DatasetStateManager リファクタリング計画:
    - データキャッシュ削除
    - Direct Widget Communication採用
    - ThumbnailSelectorWidget と SelectedImageDetailsWidget を直接接続
    '''
)

結果: DatasetStateManager, ThumbnailSelectorWidget,
     SelectedImageDetailsWidget, Direct Widget Communication
```

**抽出されるエンティティタイプ:**
- アーキテクチャコンポーネント
- デザインパターン
- 技術スタック
- 制約条件
- 依存関係

---

### cipher_query_graph
設計要素間の依存関係、アーキテクチャ構造を分析。

**パラメータ:**
- `query` (string, 必須): グラフクエリ
- `depth` (integer, オプション): 検索深度

**戻り値:**
ノード（要素）とエッジ（関係）のグラフ構造

**使用例:**
```python
cipher_query_graph(
    query="DatasetStateManager relationships",
    depth=2
)
```

**クエリ例:**
- "ThumbnailWidget dependencies"
- "Service layer architecture"
- "Repository pattern components"

---

## 長期記憶化ツール

### cipher_store_reasoning_memory
設計判断、実装アプローチ、技術的根拠を長期記憶として保存。

**パラメータ:**
- `title` (string, 必須): 記憶のタイトル（簡潔な要約）
- `content` (string, 必須): 記憶の内容（Markdown推奨）
- `tags` (array[string], オプション): 分類タグ
- `context` (string, オプション): 背景コンテキスト

**保存すべき内容:**
1. **判断内容**: 何を決定したか
2. **根拠**: なぜその判断をしたか
3. **アプローチ**: どのように実装したか
4. **結果**: 実装の効果・影響
5. **教訓**: 将来への知見

**使用例:**
```python
cipher_store_reasoning_memory(
    title="LoRAIro Direct Widget Communication パターン採用",
    content='''
# 設計判断: Direct Widget Communication パターン

## 背景
- DatasetStateManager経由の間接通信が複雑化
- 3段階のデータフロー（Search → State → Details）
- パフォーマンス低下とコード肥大化

## 判断内容
ThumbnailSelectorWidget → SelectedImageDetailsWidget の直接Signal/Slot接続

## 根拠
1. パフォーマンス向上: 3段階 → 1段階
2. コード簡素化: 150行削除
3. 保守性向上: 責任分離明確化

## 実装アプローチ
- ThumbnailSelectorWidget.image_metadata_selected シグナル追加
- SelectedImageDetailsWidget.connect_to_thumbnail_widget() メソッド
- DatasetStateManagerからデータキャッシュ削除

## 結果
- レスポンス大幅向上
- コードネット67行削減
- アーキテクチャ明確化

## 教訓
- 間接レイヤーは必要最小限に
- 直接通信で十分な場合は積極採用
- キャッシュ統一でメモリ効率化
''',
    tags=["architecture", "widget-communication", "performance"],
    context="LoRAIro GUI refactoring 2025-09"
)
```

---

## ライブラリ研究ツール（context7経由）

### mcp__context7__resolve-library-id
ライブラリ名からcontext7のIDを解決。

**パラメータ:**
- `library_name` (string, 必須): ライブラリ名

**戻り値:**
library_id（context7での識別子）

**対応ライブラリ例:**
- Python標準ライブラリ
- pyside6（Qt for Python）
- sqlalchemy（ORM）
- pytest（テストフレームワーク）
- pillow（画像処理）

**使用例:**
```python
mcp__context7__resolve-library-id(library_name="pyside6")
→ library_id="pyside6_6_8"

mcp__context7__resolve-library-id(library_name="sqlalchemy")
→ library_id="sqlalchemy_2_0"
```

---

### mcp__context7__get-library-docs
context7経由で公式ドキュメント、APIリファレンスを取得。

**パラメータ:**
- `library_id` (string, 必須): resolve-library-idで取得したID
- `section` (string, オプション): ドキュメントセクション

**戻り値:**
公式ドキュメントの内容

**取得可能な情報:**
- 公式APIリファレンス
- ベストプラクティスガイド
- チュートリアル
- アーキテクチャ設計ガイド
- サンプルコード

**使用例:**
```python
# PySide6のスレッディングガイド
mcp__context7__get-library-docs(
    library_id="pyside6_6_8",
    section="threading"
)

# SQLAlchemyのORMセッション管理
mcp__context7__get-library-docs(
    library_id="sqlalchemy_2_0",
    section="orm/session"
)

# pytest のフィクスチャガイド
mcp__context7__get-library-docs(
    library_id="pytest_8_0",
    section="fixtures"
)
```

---

## Web検索ツール

### WebSearch
最新情報、ブログ記事、事例研究を検索。

**パラメータ:**
- `query` (string, 必須): 検索クエリ
- `allowed_domains` (array[string], オプション): 検索対象ドメイン
- `blocked_domains` (array[string], オプション): 除外ドメイン

**使用例:**
```python
WebSearch(
    query="pyside6 qrunnable best practices 2025"
)
```

**context7に無い情報の検索:**
- 最新の技術動向
- ブログ記事・チュートリアル
- GitHub事例・サンプルコード
- コミュニティのベストプラクティス

---

### WebFetch
特定URLの詳細内容を取得。

**パラメータ:**
- `url` (string, 必須): 取得するURL
- `prompt` (string, 必須): 抽出する情報の指示

**使用例:**
```python
WebFetch(
    url="https://doc.qt.io/qtforpython-6/tutorials/threading.html",
    prompt="Extract QRunnable and QThreadPool usage examples"
)
```

---

## パフォーマンス特性

### 実行時間の目安
- **cipher_memory_search**: 10-20秒
- **cipher_extract_entities**: 5-10秒
- **cipher_query_graph**: 10-20秒
- **cipher_store_reasoning_memory**: 5-15秒
- **context7 resolve-library-id**: 3-5秒
- **context7 get-library-docs**: 10-30秒
- **WebSearch**: 5-10秒
- **WebFetch**: 5-15秒

### タイムアウト対策
1. **検索範囲絞り込み**: 具体的なクエリで検索
2. **並行実行回避**: Cipher操作を順次実行
3. **段階的アプローチ**: 操作を小さく分割
4. **Serenaフォールバック**: タイムアウト時はSerena + WebSearch

---

## SerenaとCipherの使い分け

### Serena Fast Ops（1-3秒）
**用途:**
- コード検索・編集
- 短期メモリ操作
- ファイル構造把握

**ツール:**
- find_symbol, get_symbols_overview
- read_memory, write_memory
- replace_symbol_body, insert_after_symbol

---

### Cipher Complex Analysis（10-30秒）
**用途:**
- 設計パターン検索
- ライブラリ研究
- 長期記憶化
- 依存関係分析

**ツール:**
- cipher_memory_search
- context7 ライブラリドキュメント
- cipher_store_reasoning_memory
- cipher_query_graph

---

## LoRAIro固有ガイドライン

### 記憶化すべき設計判断
- アーキテクチャパターン選択（Repository, Service, Direct Communication）
- 技術スタック選定理由
- パフォーマンス改善アプローチ
- リファクタリング判断と効果

### context7調査対象ライブラリ
- **PySide6**: Signal/Slot, QThread, Qt Designer
- **SQLAlchemy**: ORM, Session, Transaction
- **pytest**: Fixture, Mock, Parametrize
- **Pillow**: Image processing, Metadata

### 検索クエリベストプラクティス
- 具体的キーワード使用
- "pattern", "best practice" を含める
- LoRAIro固有用語を追加

### タグ推奨値
- `architecture`, `design-pattern`, `performance`
- `database`, `gui`, `testing`, `ai-integration`
- `refactoring`, `optimization`, `best-practice`
