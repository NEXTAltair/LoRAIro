# Issue #4: Rating/Score更新機能の実装計画（改訂版）

**策定日**: 2025-11-27
**対象**: `ImageDbWriteService`の3箇所のFIXME実装（行56, 135, 165）
**重要**: 既存実装との整合性を最優先し、Repository/Manager層の拡張を含む包括的な実装

## ユーザー設計決定（2025-11-27確定）

1. **Rating保存**: ratingsテーブルに保存 → **既存フィルタ（manual_rating_filter, NSFW除外）の修正必須**
2. **モデル管理**: Repository/ManagerにMANUAL_EDIT作成APIを追加
3. **Score保存**: 0-10スケールで保存（UI値÷100） → **AI出力と同じスケールで統一**
4. **読み出しロジック**: Repository側の `_format_annotations_for_metadata()` を修正 → **単一ソース化**

## 実装アプローチ

### Phase 1: Repository/Manager層の拡張

#### 1-1. Repository: MANUAL_EDITモデル管理API追加

**ファイル**: `src/lorairo/database/db_repository.py`

**新規メソッド**:
```python
def _get_or_create_manual_edit_model(self, session: Session) -> int:
    # model_name="MANUAL_EDIT"のモデルを検索
    # 存在すればそのIDを返す
    # 存在しなければ models テーブルに新規作成（model_name="MANUAL_EDIT", provider="user"）
    # model_typesテーブルへの関連付けは不要
```

#### 1-2. Manager: MANUAL_EDITモデルID取得API追加

**ファイル**: `src/lorairo/database/db_manager.py`

**新規メソッド**:
```python
def get_manual_edit_model_id(self) -> int:
    # インスタンス変数でキャッシュ（初回のみDB呼び出し）
    # Repository層の _get_or_create_manual_edit_model() を呼び出し
```

#### 1-3. Repository: メタデータ整形のバグ修正

**ファイル**: `src/lorairo/database/db_repository.py`（行1258-1298付近）

**修正内容**:
- **(A) Ratingバグ修正**: 行1296のTypeError（文字列の平均計算）を修正
  - 修正後: `latest_rating = max(image.ratings, key=lambda r: r.created_at)`
  - `annotations["rating_value"] = latest_rating.normalized_rating`
  
- **(B) Score処理の明確化**: 平均値から最新値取得に変更
  - 修正後: `latest_score = max(image.scores, key=lambda s: s.created_at)`
  - `annotations["score_value"] = latest_score.score`（0-10スケール）

### Phase 2: フィルタロジック修正

#### 2-1. manual_rating_filterの修正

**ファイル**: `src/lorairo/database/db_repository.py`（行1130-1137付近）

**現状**: `Image.manual_rating`カラムを直接参照
**修正後**: ratingsテーブルからMANUAL_EDITモデルのratingを参照
```python
manual_edit_subq = (
    select(Rating.image_id)
    .where(Rating.normalized_rating == manual_rating_filter)
    .where(Rating.model_id == manual_edit_model_id)
    .distinct()
)
query = query.where(Image.id.in_(manual_edit_subq))
```

#### 2-2. NSFW除外ロジックの修正

**ファイル**: `src/lorairo/database/db_repository.py`（行1118-1171付近）

**現状**: `Image.manual_rating.is_not(None)`でチェック
**修正後**: ratingsテーブルから手動評価の存在をチェック
```python
has_manual_rating_subq = (
    select(Rating.image_id)
    .where(Rating.model_id == manual_edit_model_id)
    .distinct()
)
has_manual_rating = Image.id.in_(has_manual_rating_subq)
```

**注意**: `Image.manual_rating`カラムは将来的にdeprecated

### Phase 3: ImageDbWriteService実装

**ファイル**: `src/lorairo/gui/services/image_db_write_service.py`

#### 3-1. FIXME #1: Rating/Score読み込み（行56）

**修正方針**: Repository側で整形済みのメタデータを読むだけ

```python
# Repository整形済みメタデータから取得
image_metadata = self.db_manager.repository.get_image_metadata(image_id)
rating_value = image_metadata.get("rating_value", "")

# Score: 0-10スケールをUI用に0-1000に変換
score_0_10 = image_metadata.get("score_value", 0.0)
score_value = int(score_0_10 * 100)
```

#### 3-2. FIXME #2: Rating更新（行135）

```python
# 1. バリデーション（PG, PG-13, R, X, XXX）
# 2. MANUAL_EDITモデルID取得
model_id = self.db_manager.get_manual_edit_model_id()

# 3. RatingAnnotationData作成（raw_rating_value必須）
rating_data: RatingAnnotationData = {
    "model_id": model_id,
    "raw_rating_value": rating,       # 必須フィールド
    "normalized_rating": rating,
    "confidence_score": 1.0
}

# 4. save_annotations経由で保存（Upsert）
```

#### 3-3. FIXME #3: Score更新（行165）

```python
# 1. バリデーション（0-1000）
# 2. UI値（0-1000）を0-10スケールに変換
score_0_10 = score / 100.0

# 3. MANUAL_EDITモデルID取得
model_id = self.db_manager.get_manual_edit_model_id()

# 4. ScoreAnnotationData作成
score_data: ScoreAnnotationData = {
    "model_id": model_id,
    "score": score_0_10,              # 0-10スケールで保存
    "is_edited_manually": True
}

# 5. save_annotations経由で保存
```

### Phase 4: Widget統合

**ファイル**: `src/lorairo/gui/widgets/selected_image_details_widget.py`

**新規メソッド**:
```python
def set_image_db_write_service(self, service: ImageDbWriteService) -> None:
    self._image_db_write_service = service
```

**Score表示**: Repository値（0-10）×100でスライダー値に変換

### Phase 5: テスト（16件）

#### Repository/Managerテスト（5件）
1. MANUAL_EDITモデル初回作成
2. MANUAL_EDITモデル既存取得
3. 最新Rating取得確認
4. 最新Score取得確認
5. フィルタ修正動作確認

#### ImageDbWriteServiceテスト（8件）
6. Rating/Score読み込み正常系
7. Scoreスケール変換（0-10→0-1000）
8. 空アノテーション処理
9. Rating更新正常系
10. Ratingバリデーションエラー
11. raw_rating_value設定確認
12. Score更新正常系
13. Scoreスケール変換（0-1000→0-10）

#### 統合テスト（3件）
14. Rating完全ワークフロー（作成→読込→更新→再読込→フィルタ検索）
15. Score完全ワークフロー
16. 手動Rating設定後のフィルタ動作確認

## 重要な技術的決定

### 1. Repository側での単一ソース化
- Rating/Scoreの読み出しを `_format_annotations_for_metadata()` に集約
- 検索結果と詳細表示で同じデータソースを使用
- GUI側の実装がシンプルに

### 2. Scoreスケールの統一（0-10）
- DBには0-10スケールで保存、UI側で×100/÷100変換
- AI出力と同じスケールで平均計算や比較が自然
- **変換ルール**:
  - 保存時: UI値（0-1000）÷100 → DB値（0-10）
  - 表示時: DB値（0-10）×100 → UI値（0-1000）

### 3. ratingsテーブルへの移行とフィルタ修正
- 手動Ratingをratingsテーブルに保存
- `Image.manual_rating`カラムは将来的にdeprecated
- 段階的移行（既存データは残す、新規はratingsテーブル）

### 4. MANUAL_EDITモデルのLazy Initialization
- 初回使用時に作成、Manager層でキャッシュ
- 起動時の負荷を軽減

## 既知の課題

### 課題1: Image.manual_ratingカラムの扱い（優先度: 低）
- 既存データが `Image.manual_rating` に保存されている可能性
- 新規実装ではratingsテーブルを使用
- 既存カラムは読み取り専用として残す

### 課題2: Migration不整合（優先度: 低）
- Rating.model_idのON DELETE動作が不一致（Migration: SET NULL, Schema: CASCADE）
- MANUAL_EDITモデルは削除しないためMVPには影響なし

### 課題3: フィルタ性能（優先度: 低）
- ratingsテーブルへのサブクエリで性能低下の可能性
- 必要に応じて `(image_id, model_id, created_at)` の複合インデックス追加

## 成功基準

### 機能要件
1. ✅ 3箇所のFIXME（56, 135, 165）が全て実装完了
2. ✅ ユーザーがRating/Scoreを編集でき、即座にDB保存される
3. ✅ 保存後の再読み込みで正しい値が表示される
4. ✅ manual_rating_filterで手動Ratingが検索できる
5. ✅ NSFW除外ロジックが手動Ratingを考慮する

### 品質要件
6. ✅ 単体テスト16件がpass
7. ✅ テストカバレッジ75%以上
8. ✅ mypy型チェックエラーなし
9. ✅ Ruffフォーマット・リントエラーなし

### データ整合性
10. ✅ Scoreスケール変換が正しく動作（0-1000 ⇔ 0-10）
11. ✅ RatingAnnotationDataの全必須フィールド（raw_rating_value含む）が設定される
12. ✅ is_edited_manually=Trueが正しく設定される

## 修正対象ファイル

### データ層（Repository/Manager）
- `src/lorairo/database/db_repository.py`（4箇所修正）
- `src/lorairo/database/db_manager.py`（1メソッド追加）

### サービス層（GUI）
- `src/lorairo/gui/services/image_db_write_service.py`（3箇所FIXME実装）

### ウィジェット層
- `src/lorairo/gui/widgets/selected_image_details_widget.py`（1メソッド追加）

### テストファイル
- `tests/unit/database/test_db_repository.py`（5件追加）
- `tests/unit/gui/services/test_image_db_write_service.py`（8件追加）
- `tests/integration/gui/test_rating_score_workflow.py`（新規、3件）

## 次ステップ

1. 計画レビュー → 実装フェーズへ移行
2. `/implement` コマンドで段階的実装開始
3. 各Phase完了後に該当テストを実行
4. 全Phase完了後に統合テスト実行
5. database-design-decisionsメモリ更新
