# Phase 2 Data Loss Fix - Implementation Plan (Approved)

## 承認日
2025年12月14日

## Executive Summary

genai-tag-db-dataset-builder Phase 2（マージロジック）の致命的なデータ損失問題を修正する実装計画。

**修正内容**:
1. アダプタの列正規化（tag → source_tag）
2. merge_tags()の防御的検証
3. 2パスalias登録（データ損失防止）
4. tags_v4.db重複排除（UNIQUE制約適用）
5. 3つの仕様ドキュメント作成

**スコープ**: データ損失修正のみ（パフォーマンス・CI/CDはPhase 5へ）
**推定工数**: 2-3日
**成功基準**: 既存49テストパス + 8+新規テスト + 3仕様書完成

---

## Critical Data Loss Scenarios Identified

### Issue 1: Adapter Column Normalization Missing
- **ファイル**: `csv_adapter.py:74-76`
- **問題**: validate()が`source_tag` OR `tag`を受け入れるが、read()が正規化しない
- **影響**: merge_tags()が`source_tag`を期待→KeyErrorまたは無言失敗
- **証拠**: dataset_rising_v2.csvは`tag`列を持つ（`source_tag`ではない）

### Issue 2: merge_tags() No Defensive Check
- **ファイル**: `merge.py:37`
- **問題**: `source_tag`列の存在を検証せず前提
- **影響**: アダプタが正規化しない場合にハードエラー

### Issue 3: Missing Alias Registration
- **ファイル**: `merge.py:108-120`
- **問題**: コメントでalias missing時のskipを認めている
- **影響**: alias関係が永久に失われる
- **根本原因**: 2パス処理なし（全タグ登録→関係作成の順序不履行）

### Issue 4: JSON/Parquet Adapters Weak Validation
- **ファイル**: `json_adapter.py:55-59`, `parquet_adapter.py:50-62`
- **問題**: DataFrameが空かどうかのみチェック、スキーマ未検証
- **影響**: 列欠損をmerge_tags()で初めて発見

### Issue 5: tags_v4.db UNIQUE Constraint Mismatch (NEW from GPT)
- **ファイル**: `tags_v4_adapter.py`
- **問題**: 既存tags_v4.dbはUNIQUE(tag)制約なし、実データに重複あり
- **新DB要件**: UNIQUE(tag)制約適用
- **影響**: 重複タグの統合戦略が必要
- **解決策**: 重複排除ロジック追加、TAG_STATUS衝突レポート

---

## Implementation Plan

### Phase A: CSV_Adapter Column Normalization
### Phase B: merge_tags() Defensive Validation
### Phase C: process_deprecated_tags() Logging
### Phase D: tags_v4.db Deduplication Logic (NEW)
### Phase E: Two-Pass Orchestration in Builder
### Phase F: JSON/Parquet Adapters Validation

---

## Specification Documents

### 1. dataset_builder_source_priority_and_conflict_resolution_spec_2025_12_14.md
### 2. dataset_builder_build_reproducibility_guarantee_spec_2025_12_14.md
### 3. dataset_builder_alias_registration_precondition_spec_2025_12_14.md

---

## Success Criteria

- ✅ 既存49テスト全パス
- ✅ 新規8+テストパス（アダプタ・merge・統合）
- ✅ カバレッジ≥55%維持（目標: 65%+）
- ✅ 仕様書3ファイル完成・レビュー済み
- ✅ サンプルDBビルド成功（データ損失警告なし）
- ✅ `tag`列CSVの無言失敗なし
- ✅ 2パスワークフローでalias関係損失なし
- ✅ tags_v4.db重複排除成功（NEW）

**詳細**: dataset_builder_phase2_data_loss_fix_day1_completion_2025_12_14.md, day2, day3参照

**承認者**: NEXTAltair（ユーザー）
**策定日**: 2025年12月14日
