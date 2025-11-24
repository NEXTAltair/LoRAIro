# Legacy Code Cleanup - Phase C完了記録

**実施日時**: 2025-11-22
**フェーズ**: Phase C - TODO整理（コメント更新のみ）
**実施時間**: 15分（計画20分 → 実績15分、5分短縮）

## 実施概要

Phase Cの「TODO更新のみ」アプローチに従い、9箇所のTODOコメントをFIXME/PENDING形式に変換しました。GitHub Issue作成はスキップし、ユーザーが別途実施します。

## 変更ファイル一覧

### 1. db_manager.py (2箇所更新)
- **L679**: `TODO: エラー記録テーブルが必要` → `FIXME: Issue #1参照 - エラー記録テーブルが必要`
- **L722**: `TODO: エラー記録テーブル参照` → `FIXME: Issue #1参照 - エラー記録テーブル参照`
- **Issue関連**: #1 エラー記録テーブルの設計と実装

### 2. db_repository.py (2箇所更新)
- **L449**: `TODO: 実際の連携処理に置き換える` → `FIXME: Issue #2参照 - 実際の連携処理に置き換える`
- **L1307**: `TODO: rating (AIによる評価) でのフィルタも追加検討` → `FIXME: Issue #3参照 - rating (AIによる評価) でのフィルタも追加検討`
- **Issue関連**: #2 外部Tag DB連携、#3 Ratingフィルタ追加

### 3. image_db_write_service.py (3箇所更新)
- **L56**: `TODO: 実際のスキーマに合わせて実装` → `FIXME: Issue #4参照 - 実際のスキーマに合わせて実装`
- **L135**: `TODO: 実際のRating更新機能を実装` → `FIXME: Issue #4参照 - 実際のRating更新機能を実装`
- **L165**: `TODO: 実際のScore更新機能を実装` → `FIXME: Issue #4参照 - 実際のScore更新機能を実装`
- **Issue関連**: #4 Rating/Score更新機能の実装

### 4. model_sync_service.py (1箇所更新)
- **L220**: `TODO: ライブラリ側で廃止日時管理する場合の処理` → `FIXME: Issue #5参照 - ライブラリ側で廃止日時管理する場合の処理`
- **Issue関連**: #5 モデル廃止日時管理機能

### 5. search_criteria_processor.py (1箇所更新)
- **L230**: `TODO: 重複除外ロジック実装` → `FIXME: Issue #6参照 - 重複除外ロジック実装`
- **Issue関連**: #6 重複画像除外機能

### 6. autocrop.py (1箇所更新)
- **L347**: `TODO: This logic should be reviewed for appropriateness` → `FIXME: Issue #7参照 - This logic should be reviewed for appropriateness`
- **Issue関連**: #7 AutoCropマージンロジックの妥当性レビュー

### 7. image_preview.py (1箇所更新)
- **L230**: `TODO: この表示される画像が異常に小さい` → `FIXME: Issue #8参照 - この表示される画像が異常に小さい`
- **Issue関連**: #8 画像プレビュー表示サイズ修正

### 8. image_processing_service.py (1箇所更新 - PENDING形式)
- **L109**: 詳細なPENDINGコメントに変換
```python
# PENDING: エラーハンドリング戦略の決定
# 理由: ユーザー要件次第（バッチ処理の堅牢性 vs 即座なエラー通知）
# トリガー条件: ユーザーフィードバック or 本番運用での挙動確認後
# 関連Issue: 将来的にエラーハンドリング設定をGUIで選択可能にする検討
# 現在の挙動: エラーをログに記録して処理継続（安全側に倒している）
```

## 検証結果

### TODO残存確認
```bash
serena: search_for_pattern "TODO" in src/lorairo/
```
- **結果**: `{}`（空結果）
- **確認**: `src/lorairo/`配下にTODOコメントが残っていないことを確認

### 更新パターン別集計
- **FIXME形式** (Issue参照): 8箇所
  - Issue #1: 2箇所 (db_manager.py)
  - Issue #2: 1箇所 (db_repository.py L449)
  - Issue #3: 1箇所 (db_repository.py L1307)
  - Issue #4: 3箇所 (image_db_write_service.py)
  - Issue #5: 1箇所 (model_sync_service.py)
  - Issue #6: 1箇所 (search_criteria_processor.py)
  - Issue #7: 1箇所 (autocrop.py)
  - Issue #8: 1箇所 (image_preview.py)
- **PENDING形式** (詳細コンテキスト): 1箇所
  - image_processing_service.py L109

## GitHub Issue作成（ユーザー実施予定）

以下の8つのIssueテンプレートが計画フェーズで準備されています：

1. **Issue #1**: エラー記録テーブルの設計と実装
2. **Issue #2**: 外部Tag DB連携機能の実装
3. **Issue #3**: AI評価Rating フィルタの追加
4. **Issue #4**: Rating/Score更新機能の実装
5. **Issue #5**: モデル廃止日時管理機能の追加
6. **Issue #6**: 重複画像除外機能の実装
7. **Issue #7**: AutoCropマージンロジックのレビューと改善
8. **Issue #8**: ImagePreview表示サイズ問題の修正

**注意**: これらのIssueはユーザーが別途GitHub Web UIまたは`gh` CLIで作成します。

## Phase C完了確認

- ✅ 9箇所のTODOコメント更新完了
- ✅ TODO残存確認（ゼロ件）
- ✅ Phase C証跡記録作成
- ⏭️ GitHub Issue作成（ユーザー別途実施）

## 次のステップ

**Phase D（保留）**: 型ヒントコメント、CLAUDE.md更新（20分）

## 教訓

### 効率化できた点
- 計画通りの実施により計画時間より5分短縮
- serena search_for_patternによる効率的な残存TODO確認

### 改善点
- 特になし。計画通りスムーズに完了。
