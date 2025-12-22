# Memory-First Development - 使用例

## Example 1: 新機能実装の完全フロー

### シナリオ
画像フィルタリング機能を新規実装する際のMemory-First開発。

### Phase 1: 実装前の事前確認

```
1. プロジェクト状況確認:
   mcp__serena__list_memories()
   → ["current-project-status", "active-development-tasks", ...]

   mcp__serena__read_memory("current-project-status")
   →  現在のブランチ: feature/thumbnail-details-dataflow-redesign
      最新の実装: Direct Widget Communication パターン確立
      次の優先事項: テスト整備、パフォーマンス確認

2. 過去の類似実装検索:
   cipher_memory_search(query="filtering search criteria widget")
   → 過去の「SearchCriteriaProcessor」実装パターンが見つかる
     - ビジネスロジック分離
     - Service層での実装
     - SQL生成とバリデーション

3. 設計要素抽出:
   cipher_extract_entities(
     text="画像フィルタリング機能: タグ、品質スコア、日付範囲での絞り込み"
   )
   → FilterCriteria, SearchCriteriaProcessor, ImageRepository などを特定

結果: 既存のSearchCriteriaProcessorパターンを活用できることが判明
```

### Phase 2: 実装中の継続記録

```
実装開始時（10:00）:
   mcp__serena__write_memory(
     memory_name="active-development-tasks",
     content='''
# 画像フィルタリング機能実装 - 2025-10-20

## 進行中タスク
- FilterCriteria データクラス実装

## 次のステップ
1. SearchCriteriaProcessor 拡張
2. ImageRepository フィルタリングメソッド追加
3. GUI Widget統合

## 技術的判断
まだなし
'''
   )

重要な判断時（12:00）:
   mcp__serena__write_memory(
     memory_name="active-development-tasks",
     content='''
# 画像フィルタリング機能実装 - 2025-10-20

## 進行中タスク
- SearchCriteriaProcessor 拡張実装中

## 完了した作業
✅ FilterCriteria データクラス実装
✅ バリデーションロジック追加

## 次のステップ
1. ImageRepository フィルタリングメソッド追加
2. GUI Widget統合
3. 単体テスト作成

## 技術的判断
- dataclass使用でボイラープレート削減
  理由: 型安全、コード簡潔化、イミュータブル
- Optional型で柔軟な絞り込み
  理由: すべての条件が必須ではない

## 課題
- 日付範囲の扱い（timezone考慮）
  解決策候補: UTC統一、または設定で選択可能に
'''
   )

作業終了時（17:00）:
   mcp__serena__write_memory(
     memory_name="active-development-tasks",
     content='''
# 画像フィルタリング機能実装 - 2025-10-20

## 完了した作業
✅ FilterCriteria データクラス
✅ SearchCriteriaProcessor 拡張
✅ ImageRepository フィルタリングメソッド

## 明日のタスク
1. GUI Widget統合
2. 単体テスト作成
3. 統合テスト実行

## 技術メモ
- SQLAlchemy filter()でAND条件構築
- Optional型の条件は動的に追加
- timezone はUTC統一で実装
'''
   )
```

### Phase 3: 完了後の知識蓄積

```
実装完了時:
   cipher_store_reasoning_memory(
     title="LoRAIro 画像フィルタリング機能設計・実装",
     content='''
# 画像フィルタリング機能実装

## 背景・動機
- ユーザーが大量の画像から目的の画像を効率的に探せるように
- タグ、品質スコア、日付範囲での柔軟な絞り込みが必要

## 設計アプローチ
- dataclass によるFilterCriteria定義
- SearchCriteriaProcessor での条件処理
- ImageRepositoryでのSQL生成
- Optional型で柔軟な絞り込み

## 技術選定
- Python dataclass: ボイラープレート削減、型安全
- SQLAlchemy filter(): 動的条件構築
- Optional[T]: 条件の柔軟性

## 実装詳細
```python
@dataclass
class FilterCriteria:
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

class ImageRepository:
    def get_filtered_images(self, criteria: FilterCriteria):
        query = self.session.query(Image)
        if criteria.tags:
            query = query.filter(Image.tags.contains(criteria.tags))
        if criteria.min_score:
            query = query.filter(Image.score >= criteria.min_score)
        # ... その他の条件
        return query.all()
```

## 結果・効果
- 柔軟なフィルタリング実現
- 型安全なAPI
- テストカバレッジ 85%

## 課題と解決策
- **課題**: timezone扱い
  **解決**: UTC統一、UI表示時にローカライズ

## 教訓・ベストプラクティス
- dataclassは型安全で簡潔
- Optional型で柔軟なAPI設計
- SQLAlchemy filter()で動的条件構築が容易

## アンチパターン
- 全条件を必須にすると柔軟性が失われる
- 文字列ベースのSQL構築は避ける（SQLAlchemy使用）
''',
     tags=["database", "filtering", "repository-pattern"],
     context="LoRAIro image filtering feature"
   )

   # Serena メモリ更新
   mcp__serena__write_memory(
     memory_name="current-project-status",
     content='''
# LoRAIro Project Status - 2025-10-20

## 最新の開発状況
✅ 画像フィルタリング機能実装完了

## 次の優先事項
1. 統合テスト実行
2. パフォーマンステスト
3. ユーザードキュメント更新
'''
   )
```

## Example 2: リファクタリングのMemory記録

### シナリオ
DatasetStateManager の大規模リファクタリング。

### 実装前
```
cipher_memory_search(query="state manager refactoring cache removal")
→ 過去の類似リファクタリング事例を確認

結果: キャッシュ削除時の注意点、影響範囲分析方法を発見
```

### 実装中
```
mcp__serena__write_memory(
  "active-development-tasks",
  '''
## リファクタリング進捗
- 段階1: データキャッシュ削除 ✅
- 段階2: Direct Widget Communication実装 🔄
- 段階3: テスト更新 ⏳

## 削除したメソッド
- get_image_by_id()
- has_images()
- get_current_image_data()

## 影響箇所
- ThumbnailSelectorWidget: image_metadata_selected追加
- SelectedImageDetailsWidget: connect_to_thumbnail_widget()追加
- Tests: 3ファイル更新必要
'''
)
```

### 完了後
```
cipher_store_reasoning_memory(
  title="LoRAIro DatasetStateManager簡素化リファクタリング",
  content='''
## リファクタリング目的
- 複雑な間接フロー（3段階）の簡素化
- データキャッシュ重複削除
- パフォーマンス向上

## アプローチ
- キャッシュ統一: ThumbnailSelectorWidget.image_metadataに一本化
- Direct Communication: Signal/Slot直接接続
- 責任分離: DatasetStateManagerはUI状態のみ

## 結果
- コード削減: 150行 → ネット67行削減
- パフォーマンス: 3段階 → 1段階（大幅向上）
- 保守性: 責任分離明確化

## 教訓
- 間接レイヤーは必要最小限に
- キャッシュ統一でメモリ効率化
- Direct Communicationで十分な場合は積極採用
'''
)
```

## Example 3: デバッグ情報の記録

### シナリオ
複雑なバグの調査と解決。

```
mcp__serena__write_memory(
  "debug_thumbnail_selection_2025_10_20",
  '''
# サムネイル選択バグ調査

## 症状
- サムネイルクリック時に画像詳細が更新されない
- コンソールエラーなし

## 調査結果
1. Signal/Slot接続は正常
2. データは正しく取得されている
3. 問題: SelectedImageDetailsWidget.update()が呼ばれていない

## 原因
- ThumbnailSelectorWidget.image_metadata_selectedシグナルは発火
- しかしSelectedImageDetailsWidget側で接続されていなかった
- MainWindow初期化時の接続処理が抜けていた

## 解決策
MainWindow.__init__()に以下を追加:
```python
self.selected_image_details.connect_to_thumbnail_widget(
    self.thumbnail_selector
)
```

## 教訓
- Direct Widget Communicationは接続忘れに注意
- 初期化処理のチェックリスト作成が必要
'''
)

解決後にCipherに記憶:
cipher_store_reasoning_memory(
  title="LoRAIro Direct Widget Communication 接続パターン",
  content='''
## ベストプラクティス
MainWindow初期化時に明示的な接続処理:

```python
class MainWindow:
    def __init__(self):
        self._init_widgets()
        self._connect_widgets()  # 専用メソッドで接続

    def _connect_widgets(self):
        # 全てのWidget間接続をここに集約
        self.selected_image_details.connect_to_thumbnail_widget(
            self.thumbnail_selector
        )
        # その他の接続...
```

## アンチパターン
- 接続処理が散在
- 暗黙的な接続（自動接続への期待）
'''
)
```

## ベストプラクティス

### Serena Memory更新頻度
- **開始時**: 必ず現在状況確認
- **実装中**: 1-2時間ごと、重要な判断後
- **終了時**: 次回のための状況記録

### Cipher Memory記録タイミング
- **機能完了時**: 実装パターンと判断を記録
- **リファクタリング完了時**: アプローチと効果を記録
- **重要な技術判断時**: 選定理由と根拠を記録

### 記録すべき内容
#### Serena（一時的）
- 現在の作業内容
- 完了したタスク
- 次のステップ
- 一時的な判断
- デバッグ情報

#### Cipher（永続的）
- 設計アプローチ
- 技術選定理由
- 実装結果と効果
- 課題と解決策
- 教訓とアンチパターン

### LoRAIro固有
- **アーキテクチャ変更**: 必ずCipherに記録
- **パフォーマンス改善**: 効果測定結果と共に記録
- **デバッグ**: 複雑な問題はSerena→解決後Cipherに移行
