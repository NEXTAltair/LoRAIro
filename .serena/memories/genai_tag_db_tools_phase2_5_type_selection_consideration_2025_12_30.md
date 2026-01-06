# Phase 2.5: type_name選択機能の検討

**日付**: 2025-12-30  
**状態**: 🤔 検討中

## ユーザー要求

「unknownのタイプを登録する時既存データベースにあるtype name 検索して既存の名前を割り当てを選択できる処理も計画に入ってる?」

## 現状

### 既存API（利用可能）
- `MergedTagReader.get_all_types()` - 全type_nameリスト取得（Base DB + User DB）
- `MergedTagReader.get_tag_types(format_id)` - format内type_nameリスト取得

### Phase 2.5計画（既存）
- **P2.5-1**: format内type_id採番ロジック
- **P2.5-2**: 不完全タグ一括更新API (`update_tags_type_batch()`)
- **P2.5-3**: テストケース追加

**P2.5-2の仕様**:
```python
def update_tags_type_batch(tag_updates: List[TagTypeUpdate], format_id: int):
    # TagTypeUpdate で type_name を直接指定
    # create_type_name_if_not_exists() で自動作成
    pass
```

**制約**: 「GUI実装: 不要（LoRAIro側でサービス層として利用）」

## 実装オプション

### オプション1: 現在の計画維持（最小スコープ）
**内容**:
- P2.5-1, P2.5-2, P2.5-3 のみ実装
- type_name は外部（LoRAIro）から直接指定
- 既存type_name一覧取得は `get_all_types()` / `get_tag_types()` で可能（API既存）

**利点**:
- スコープ明確、実装工数少ない
- LoRAIroで自由にUI実装可能（Qtウィジェット、候補表示など）
- genai-tag-db-toolsはシンプルなサービス層のみ

**欠点**:
- LoRAIro側でtype_name一覧取得→表示→選択ロジックを実装必要

### オプション2: type_name候補取得ヘルパー追加
**内容**:
- P2.5-1, P2.5-2, P2.5-3 実装
- **P2.5-4** 追加: `get_available_type_names(format_id: int | None = None) -> list[str]`
  - `format_id` 指定時: 該当formatのtype_nameリスト
  - `format_id=None`: 全type_nameリスト（Base + User）
  - 内部で `get_all_types()` / `get_tag_types()` を呼ぶラッパー

**利点**:
- LoRAIroから使いやすいAPI提供
- 統一されたインターフェース
- 実装コスト低い（既存APIのラッパーのみ）

**欠点**:
- 既存APIと重複（`MergedTagReader.get_all_types()` と同じ）

### オプション3: type_name提案機能（高度）
**内容**:
- P2.5-1, P2.5-2, P2.5-3 実装
- **P2.5-4** 追加: `suggest_type_names_for_tag(tag: str, format_id: int) -> list[str]`
  - タグ内容から適切なtype_nameを推測（heuristic）
  - 例: "1girl" → ["character", "person", "subject"]
  - 既存type_nameから類似度計算、候補返却

**利点**:
- ユーザー体験向上（手動選択の手間削減）
- インテリジェントな提案

**欠点**:
- 実装コスト高い（推論ロジック必要）
- 精度保証困難
- スコープ拡大（Phase 2.5を超える）

## 推奨アプローチ

**オプション1（現在の計画維持）** を推奨:

**理由**:
1. **既存APIで十分**: `get_all_types()`, `get_tag_types(format_id)` が既に存在
2. **責任分離明確**: genai-tag-db-tools = データ操作、LoRAIro = UI/UX
3. **柔軟性**: LoRAIroで独自のtype_name選択UI実装可能（ドロップダウン、検索ボックス、フィルタなど）
4. **スコープ制御**: Phase 2.5は「不完全タグ一括更新」に集中

**LoRAIro側の実装例**:
```python
# LoRAIro側で実装
def show_type_selection_dialog(tag: str, format_id: int):
    # 1. 既存type_name一覧取得
    type_names = merged_reader.get_tag_types(format_id)  # または get_all_types()
    
    # 2. Qt UI で選択ダイアログ表示
    selected_type = QInputDialog.getItem(
        parent, "Select Type", f"Type for tag '{tag}':", 
        type_names, editable=True
    )
    
    # 3. 一括更新APIで反映
    updates = [TagTypeUpdate(tag=tag, type_name=selected_type)]
    tag_register_service.update_tags_type_batch(updates, format_id)
```

## 決定事項（2025-12-30）

**✅ Phase 2.5計画に追加**:
- **P2.5-4**: type_name選択・割り当てインターフェース実装
  - 既存type_name一覧取得のエクスポート（`get_all_types()`, `get_tag_types(format_id)` 活用）
  - 一括更新API (`update_tags_type_batch()`) との統合
  - LoRAIroから利用可能なAPI設計

**実装方針**:
- genai-tag-db-tools: type_name一覧取得・一括更新APIのみ提供
- LoRAIro: 選択UIの実装（既存APIを消費）

## 次ステップ

1. **Phase 2.5実装開始**: P2.5-1, P2.5-2, P2.5-3, P2.5-4
2. **LoRAIro連携設計**: type_name選択UIをLoRAIro側で実装

## 関連API（既存）

- `MergedTagReader.get_all_types()`: [repository.py:1007-1013](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L1007-L1013)
- `MergedTagReader.get_tag_types(format_id)`: [repository.py:991-997](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L991-L997)
- `TagReader.get_all_types()`: [repository.py:321-323](local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py#L321-L323)
