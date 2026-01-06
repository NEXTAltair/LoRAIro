# genai-tag-db-tools: 不完全タグ管理機能仕様

**日付**: 2025-12-30  
**コンテキスト**: Phase 2 (タグ登録) 完了後の次期機能実装  
**目的**: LoRAIroからの一括タグ登録時に、type判定を後回しにできる仕様策定

## 背景

LoRAIroからの新規タグ登録時、都度type判定を行うと作業フローが悪化するため、一時的に不完全なデータを蓄積し、後で一括修正できる仕組みが必要。

## ユーザー決定事項

### 1. 不完全判定基準

**仕様**: `type_name == "unknown"` **のみ**で判定  
**理由**: format_nameチェックは不要（ユーザー登録formatのみが対象のため、format_idフィルタで十分）

### 2. type_name自動作成

**仕様**: 任意のtype_name文字列を許可、存在しなければ自動作成  
**実装状況**: 既に `TagRegisterService.register_tag()` で実装済み ([tag_register.py:151-174](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_register.py#L151-L174))

### 3. type_id採番戦略

**当初案**: format_idと同じく1000+シーケンス  
**調査結果**: **不要** - 以下の理由による：

#### データベース設計詳細

```
TagTypeName (グローバル管理)
├─ type_name_id: PRIMARY KEY (AUTO INCREMENT)
├─ type_name: UNIQUE (例: "unknown", "character", "general")
└─ description: NULL可

TagTypeFormatMapping (format × type関連付け)
├─ format_id: PRIMARY KEY (外部キー -> TAG_FORMATS)
├─ type_id: PRIMARY KEY (format内でのローカル番号)
├─ type_name_id: 外部キー -> TagTypeName
└─ description: NULL可
```

**重要**: `type_id`はformat依存の**ローカル番号**

#### 衝突が発生しない理由

**Base DBとUser DBは物理的に異なるSQLiteファイル**:
- Base DB: HuggingFaceからダウンロードされる複数のSQLiteファイル
  - `genai-image-tag-db-cc4.sqlite` (CC4ライセンス)
  - `genai-image-tag-db-mit.sqlite` (MITライセンス)
  - `genai-image-tag-db-cc0.sqlite` (CC0ライセンス)
- User DB: ローカルで作成される単一のSQLiteファイル
  - `user_tags.sqlite`

**各SQLiteファイルは独立したスキーマとデータを持つ**:
- 同じテーブル構造（TagTypeName, TagTypeFormatMappingなど）
- 独立したAUTO INCREMENT カウンター
- 独立した外部キー制約（同一ファイル内でのみ機能）

**具体例**:
- Base DB内: `TagTypeName(type_name_id=1, type_name="unknown")`, `TagTypeFormatMapping(format_id=1, type_id=0, type_name_id=1)`
- User DB内: `TagTypeName(type_name_id=1, type_name="unknown")`, `TagTypeFormatMapping(format_id=1000, type_id=0, type_name_id=1)`

→ 同じ type_id=0, type_name_id=1 だが、**異なるSQLiteファイル内のレコード**のため衝突しない

**format_idが分離されているため、type_idは各format内でのローカル番号（0,1,2...）として重複可能**

#### 既存実装

[repository.py:681-714](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L681-L714) `create_type_format_mapping_if_not_exists()`:
- 新規type_name作成時、現在は `type_id=1` 固定
- 複数type_nameを同一formatに追加する場合、衝突防止ロジックが必要

### 4. GUI実装

**仕様**: 不要（LoRAIro側でサービス層として利用）

## 既存API分析

### 不完全タグ検索

```python
reader.search_tags(
    keyword="",  # 全タグ
    type_name="unknown",
    format_name="Lorairo"
)
```

**実装場所**: [repository.py:169-224](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L169-L224)

### タグtype更新

```python
repository.update_tag_status(
    tag_id=123,
    format_id=1000,
    alias=False,
    preferred_tag_id=123,
    type_id=2  # 新しいtype_id
)
```

**制約**: [repository.py:491-504](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L491-L504)
- 指定したtype_idがTagTypeFormatMappingに存在しない場合エラー
- 事前に `create_type_format_mapping_if_not_exists()` でマッピング作成が必要

### type_name取得

```python
type_name_id = reader.get_type_id("character")  # type_name -> type_name_id
```

**実装場所**: [repository.py:113-116](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L113-L116)

### format対応type一覧

```python
type_names = reader.get_tag_types(format_id=1000)
# Returns: ["unknown", "character", "general", ...]
```

**実装場所**: [repository.py:299-307](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L299-L307)

## 実装要件

### 必須API

1. **不完全タグ取得API**
   - 入力: `format_id` (or `format_name`)
   - 出力: type_name="unknown"のタグ一覧

2. **タグtype一括更新API**
   - 入力: `List[(tag_id, new_type_name)]`, `format_id`
   - 処理:
     1. type_nameからtype_name_id取得（存在しなければ作成）
     2. TagTypeFormatMappingでformat_id+type_nameに対応するtype_id検索
     3. マッピングが存在しなければ、format内で次のtype_id採番して作成
     4. update_tag_status()でtype_id更新

3. **format内type_id採番ロジック**
   - 現在のformat_idで使用中のtype_idを取得
   - max(type_id) + 1 を返す（存在しなければ0）

### データ整合性保証

- TagTypeFormatMappingへの自動マッピング作成
- format内type_id重複防止
- トランザクション保証（一括更新時のrollback対応）

## 実装対象外

- type_id 1000+オフセット（不要）
- GUI実装（LoRAIro側で実装）
- format_id衝突チェック（既に実装済み）

## 関連コミット

- format_id 1000+実装: [genai-tag-db-tools](local_packages/genai-tag-db-tools) commit 60f156d, 20b0127
- Phase 2完了記録: [.serena/memories/genai_tag_db_tools_phase2_tag_registration_completion_2025_12_30.md](.serena/memories/genai_tag_db_tools_phase2_tag_registration_completion_2025_12_30.md)

## 次ステップ

1. format内type_id採番ロジック実装
2. 不完全タグ一括更新API実装
3. 既存test_tag_register.pyにテストケース追加
4. LoRAIro統合テスト
