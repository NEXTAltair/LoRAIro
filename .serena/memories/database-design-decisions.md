# データベース設計判断の記録

## スキーマ設計方針

### 履歴保持のためのUNIQUE制約廃止
**決定日**: 2025-04-16
**対象テーブル**: `tags`, `captions`, `scores`, `ratings`

**決定内容**:
`image_id`, `model_id` (およびタグ/キャプション文字列) の組み合わせに対する UNIQUE 制約は適用しない。

**理由**:
履歴保持を可能にするため。同じ画像に対して異なる時点でのアノテーション結果を全て保存できるようにする。

### tag_id の外部キー制約なし
**対象**: `tags.tag_id` カラム

**決定内容**:
`tag_id` は `genai-tag-db-tools` の `tag_db.TAGS.tag_id` を概念的に参照するが、FK制約は設定しない。

**理由**:
外部データベース（tag_db）への参照であり、直接的なFK制約は適用できない。ATTACH DATABASEで接続する。

## セッション管理方針

**採用パターン**: Contextマネージャによるメソッド単位セッション

```python
with self.session_factory() as session:
    # 操作
```

**理由**:
- 各操作の原子性を保ちやすい
- スレッドセーフティの確保
- セッションの開始、コミット/ロールバック、クローズが自動処理される

## genai-tag-db-toolsとの技術的整合性

**方針**:
基本的な考え方（ORM利用、セッション管理など）の整合性を保ちつつ、LoRAIro側ではより洗練された構成と実装を目指す。

**具体的アプローチ**:
- タグデータベースの構造など良い点は踏襲
- ディレクトリ/ファイル構成は改善
- 両者を扱う際の混乱を避ける

## 統合時の注意点

### データ形式の変更
- **save_annotations**: 引数形式が `AnnotationsDict` (TypedDict) に変更
- **get_image_annotations**: 返り値が `dict[str, list[dict[str, Any]]]` 形式
- **get_images_by_filter**: 引数が大幅追加（日付、NSFW、手動編集フラグなど）
  - 日付フィルターは `images.updated_at` のみを対象
  - NSFWフィルターと `manual_rating_filter` の相互作用に注意

### エラーハンドリングの変更
- `sqlite3.Error` から SQLAlchemy固有エラー (`SQLAlchemyError`, `IntegrityError` など) に変更
- Repository/Manager内でエラーログ出力されるため、呼び出し元での冗長なログは削減可能

### メソッド名の変更
- `find_duplicate_image` → `find_duplicate_image_by_phash`
- `get_processed_metadata` → `get_processed_image`

## ディレクトリ構成

```
src/lorairo/database/
├── __init__.py
├── schema.py            # SQLAlchemyモデル定義
├── db_repository.py     # Repositoryクラス群
├── db_manager.py        # Manager/Serviceクラス群
├── db_core.py           # DB設定、セッション管理、エンジン等
└── migrations/          # Alembic マイグレーション
    ├── env.py
    ├── script.py.mako
    └── versions/
```

## 設定ファイル連携

`config.toml` から読み込む設定:
- `directories.database`: データベースディレクトリ
- `database.image_db_filename`: 画像データベースファイル名
- `database.tag_db_package`: タグデータベースのパッケージ名
- `database.tag_db_filename`: タグデータベースのファイル名

これらは `src/lorairo/utils/config.py` を通じて `db_core.py` で使用される。
