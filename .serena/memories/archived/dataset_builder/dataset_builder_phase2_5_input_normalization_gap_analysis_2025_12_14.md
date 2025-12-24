# Phase 2.5 Input Normalization Gap Analysis（dataset-builder）

## 作成日
2025年12月14日

## 背景

Phase 2 Data Loss Fix完了後、ユーザーから重要な方針変更・明確化がありました。現在の実装と新方針のギャップを分析し、Phase 2.5として対応します。

---

## 新方針サマリー

### 1. 翻訳運用の明確化
**新方針**: 同一(tag_id, language)で複数のtranslationを許容（表現揺れを許容）
- UNIQUE(tag_id, language, translation) のイメージ

**現状**: スキーマ未定義（おそらく暗黙的にUNIQUE(tag_id, language)を想定）

**影響**: TAG_TRANSLATIONS テーブルスキーマ変更が必要

### 2. source_tag代表値ルール
**新方針**: 
- 最初に登録されたものを代表（取り込み順の先頭＝tags_v4.db）
- source_tagは常に小文字統一（Witch→witch）

**現状**: 
- deduplication時にsort("tag_id")でfirst選択 → 正しい ✅
- source_tagの小文字統一なし → 要修正 ❌

**影響**: 全アダプタでsource_tag列の小文字化が必要

### 3. CSV等入力の"tag列"問題（最重要）
**新方針**: tag列が「正規タグ」か「source_tag」かの判定ロジックが必要
- 判定シグナル:
  - underscore率（生タグ寄り: "witch_hat" vs 正規化済み: "witch hat"）
  - 括弧エスケープ \(/\) の有無（正規化済み: "witch (sorceress)" vs 生タグ: "witch \(sorceress\)"）
  - normalize_tag の変化率（normalize前後で変わる＝生タグ寄り）
- 確信できない場合: unknown判定 → レポート → 手動指定

**現状**: 単純な tag → source_tag リネーム（Phase A/F）
- csv_adapter.py line 66-78: `df.rename({"tag": "source_tag"})`
- json_adapter.py line 31-36: 同上
- parquet_adapter.py line 31-36: 同上

**問題点**: 危険（入力ブレを吸収していない）

**影響**: 列正規化ロジックの全面書き直しが必要

### 4. ソース優先順位の変更
**新方針**: サイト間（danbooru/e621/derpibooru）に優先順位なし（同価値）
- 衝突は「同一format内で複数ソースがある場合」が主
- 手動判断前提

**現状**: source_priority_and_conflict_resolution_spec.md
- Priority 1: tags_v4.db（最高）
- Priority 2: e621_tags_jsonl.csv（高）
- Priority 3-5: 他のCSV（低）

**問題点**: 仕様書がサイト間に優先順位を付けている

**影響**: source_priority_and_conflict_resolution_spec.md 全面書き直し

### 5. 再現性の定義変更
**新方針**: 内容再現（content-level）を主、SQLiteバイト同一は必須でない

**現状**: build_reproducibility_guarantee_spec.md
- "bit-for-bit identical output databases"
- SHA256ハッシュ比較でバイト同一を検証

**問題点**: 過度に厳しい要件

**影響**: build_reproducibility_guarantee_spec.md 修正

---

## ギャップ分析

### Critical Gap 1: Tag Column Type Classification（判定ロジック欠如）

**影響度**: 🔴 Critical
**理由**: 現在の単純リネームは「生タグ」と「正規化済みタグ」を区別できず、データ破壊の可能性

**例**:
```
入力CSV: tag="witch_hat"（生タグ、アンダースコア含む）
現在の実装: source_tag="witch_hat"（誤り、正規化されていない）
正しい処理: source_tag="witch hat"（正規化後）

入力CSV: tag="witch hat"（既に正規化済み）
現在の実装: source_tag="witch hat"（正しい）
正しい処理: source_tag="witch hat"（そのまま）
```

**必要な実装**:
1. 新規モジュール: `core/column_classifier.py`
   - `TagColumnType` enum (NORMALIZED, SOURCE, UNKNOWN)
   - `classify_tag_column(df: pl.DataFrame, column_name: str) -> TagColumnType`
   - シグナル計算関数:
     - `calculate_underscore_ratio(tags: list[str]) -> float`
     - `detect_escaped_parentheses(tags: list[str]) -> float`
     - `calculate_normalize_change_ratio(tags: list[str]) -> float`

2. アダプタ修正:
   - `_normalize_columns()`の前に判定実行
   - UNKNOWN時はWARNINGログ + レポートCSV出力
   - ユーザーに手動指定を促す

**テスト要件**:
- test_column_classifier.py（新規）
  - test_classify_normalized_tags（正規化済み判定）
  - test_classify_source_tags（生タグ判定）
  - test_classify_unknown_tags（不明判定）
  - test_underscore_ratio_calculation
  - test_escaped_parentheses_detection
  - test_normalize_change_ratio

### Critical Gap 2: Source Tag Lowercase Normalization（小文字統一欠如）

**影響度**: 🟠 High
**理由**: 大文字小文字の不統一により、同一タグが重複登録される可能性

**例**:
```
tags_v4.db: source_tag="Witch"（大文字開始）
CSV: source_tag="witch"（小文字）
現在の実装: 2つの別タグとして登録される（誤り）
正しい処理: 両方とも "witch" に統一
```

**必要な実装**:
1. tags_v4_adapter.py:
   - `_deduplicate_tags()`内でsource_tag小文字化
   - `df = df.with_columns(pl.col("source_tag").str.to_lowercase())`

2. csv/json/parquet adapters:
   - `_normalize_columns()`内でsource_tag小文字化
   - 同様の処理

3. merge.py:
   - `merge_tags()`内で新規タグのsource_tag小文字化
   - 既存タグとの統合時に小文字で比較

**テスト要件**:
- test_tags_v4_adapter.py:
  - test_source_tag_lowercase_normalization（新規）
- test_csv_adapter.py:
  - test_source_tag_lowercase_normalization（新規）
- test_merge.py:
  - test_merge_tags_lowercase_source_tag（新規）

### Medium Gap 3: Translation Schema Update（翻訳スキーマ）

**影響度**: 🟡 Medium
**理由**: 現在のスキーマは未定義だが、将来的に表現揺れを許容する必要

**必要な実装**:
1. database.py:
   - TAG_TRANSLATIONS テーブル作成SQL修正
   - UNIQUE制約変更: (tag_id, language) → (tag_id, language, translation)

2. test_database.py:
   - スキーマ検証テスト追加

**SQL例**:
```sql
CREATE TABLE TAG_TRANSLATIONS (
    tag_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    translation TEXT NOT NULL,
    UNIQUE(tag_id, language, translation),  -- 表現揺れを許容
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id)
);
```

### Low Gap 4: Specification Document Updates（仕様書更新）

**影響度**: 🟢 Low
**理由**: 実装が正しければ、仕様書は後から修正可能

**必要な修正**:

1. source_priority_and_conflict_resolution_spec.md:
   - ソース優先順位セクション削除
   - "Source Equality"セクション追加
     - tags_v4.dbは「最初のソース（登録順の先頭）」として扱う
     - サイト間（danbooru/e621/derpibooru）は同価値
     - 衝突は手動判断前提を強調
   - Rule 1-3の見直し（優先順位ベースの記述を削除）

2. build_reproducibility_guarantee_spec.md:
   - バイト同一要件を削除
   - "Content-Level Reproducibility"セクション追加
     - TAGS/TAG_STATUSの内容一致を検証
     - SQLiteバイナリ差異は許容（VACUUM等の最適化差異）
     - SHA256ハッシュはテーブル内容のみ（メタデータ除外）

3. alias_registration_precondition_spec.md:
   - 変更なし（2パス処理は既に正しい）

---

## 実装順序の提案

### Phase 2.5: Input Normalization Enhancement

**Day 1**: Critical Gap 1（Tag Column Type Classification）
- core/column_classifier.py実装
- test_column_classifier.py作成
- アダプタへの統合は保留（Day 2で実施）

**Day 2**: Critical Gap 1 + Gap 2統合
- アダプタ修正（判定ロジック統合 + 小文字化）
- csv/json/parquet adapters更新
- tags_v4_adapter更新
- 既存テスト修正 + 新規テスト追加

**Day 3**: Gap 3 + Gap 4
- database.py修正（翻訳スキーマ）
- 仕様書3ファイル更新
- 全テスト実行・レビュー

---

## リスク評価

### 高リスク: 既存テスト破壊

**問題**: Phase 2で作成した74テストが破壊される可能性

**理由**:
- 列正規化ロジックの変更により、テストデータの期待値が変わる
- source_tag小文字化により、既存のテストケースが失敗する可能性

**軽減策**:
1. 段階的実装（Day 1で判定ロジックのみ、Day 2で統合）
2. 既存テストを先に修正してから新機能を追加
3. 各Day後に全テストスイート実行

### 中リスク: 判定ロジックの精度

**問題**: underscore率等のシグナルで誤判定の可能性

**軽減策**:
1. 閾値を保守的に設定（確信度低い場合はUNKNOWN）
2. レポートCSV出力で手動検証可能に
3. 実データでの検証（TagDB_DataSource_CSV等）

### 低リスク: 仕様書の一貫性

**問題**: 仕様書更新が漏れる可能性

**軽減策**:
1. Day 3で全仕様書を一括レビュー
2. クロスリファレンスの検証

---

## Success Criteria（Phase 2.5）

- [ ] Tag Column Type Classification実装完了
  - [ ] core/column_classifier.py作成
  - [ ] test_column_classifier.py（6+テスト）
  - [ ] 判定精度検証（実データでUNKNOWN率 <10%）

- [ ] Source Tag Lowercase Normalization実装完了
  - [ ] 全アダプタ修正（4ファイル）
  - [ ] 新規テスト追加（3テスト）
  - [ ] 既存テスト修正（大文字使用箇所）

- [ ] Translation Schema Update実装完了
  - [ ] database.py修正
  - [ ] スキーマ検証テスト追加

- [ ] 仕様書3ファイル更新完了
  - [ ] source_priority_and_conflict_resolution_spec.md
  - [ ] build_reproducibility_guarantee_spec.md
  - [ ] alias_registration_precondition_spec.md

- [ ] 全74+新規テストパス
- [ ] カバレッジ≥66%維持

---

## Out of Scope（Phase 3以降）

- HuggingFace dataset統合（表形式入力の判定ロジックは同じ仕組みを使用）
- 実データでのサンプルDBビルド
- CI/CD統合

---

**策定者**: Claude Sonnet 4.5
**参照**: ユーザー方針変更（2025-12-14）
