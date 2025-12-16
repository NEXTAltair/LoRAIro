# genai-tag-db-dataset-builder Phase 5-6 実装計画

## 策定日
2025年12月15日

## 概要

Phase 0-4 および Phase 2.5 の完了を受けて、Phase 5（テスト・検証）と Phase 6（ローカルビルド）の実装計画を策定します。

**スコープ**: Phase 2.5の方針に従い、**ローカルに存在する tags_v4.db + TagDB_DataSource_CSV のみ**を対象とします。外部データセット統合（deepghs/site_tags、HuggingFace公開等）は Phase 7（将来）に後回しします。

**重要**: Plan Mode「Phase 3完了記録の問題点分析」で指摘された技術的負債への対応を Phase 5 に統合します。

---

## 前提条件

### 完了済みフェーズ

**Phase 0-4** ✅:
- Phase 0: 基盤整備（pyproject.toml, ディレクトリ構造）
- Phase 1: アダプタ実装（base, tags_v4, csv, json, parquet）
- Phase 2: マージロジック実装（merge_tags, process_deprecated_tags, detect_conflicts）
- Phase 3: SQLite最適化（create_database, optimize_database, indexes）
- Phase 4: CI/CD構築（GitHub Actions, HF upload, metadata生成）

**Phase 2.5** ✅ (2025-12-15):
- 入力正規化強化（TagColumnType分類、NORMALIZED/UNKNOWN skip、lowercase normalization）
- テスト: 114 passed (105 unit + 9 integration)
- カバレッジ: 72.25%

### 技術的負債（優先度付き）

**Plan Mode「Phase 3完了記録の問題点分析」より**:

1. **高優先度（Phase 5で対応）**:
   - PRAGMAの接続単位設定の実装
   - テストスキーマの実DB互換化

2. **中優先度（Phase 5-6で対応）**:
   - 実クエリの文書化とインデックス再設計
   - 完了記録の修正

**注**: CI/CD構築は Phase 4 で完了済み（GitHub Actions, upload.py実装）のため、技術的負債には含まれません。

---

## Phase 5: テスト・検証（Week 8-9）

### 5.1 テストスイート整備（Day 1-2）

**目的**: 技術的負債対応とテスト網羅性向上

#### 5.1.1 テストスキーマの実DB互換化（高優先度）

**問題**: test_database.pyのTAG_STATUS.type_idがnullable（実DBはNOT NULL）

**対応**:
```python
# tests/unit/test_database.py

def test_create_tag_status_table(tmp_path):
    """TAG_STATUSテーブルがtags_v4.dbスキーマと互換性があることを確認"""
    conn = sqlite3.connect(tmp_path / "test.db")
    
    # 実DBスキーマと完全一致
    conn.execute("""
        CREATE TABLE TAG_STATUS (
            tag_id INTEGER NOT NULL,
            format_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,  # ← NOT NULL（修正）
            alias BOOLEAN NOT NULL,
            preferred_tag_id INTEGER NOT NULL,
            PRIMARY KEY (tag_id, format_id)
        )
    """)
```

**実装タスク**:
- [ ] test_database.pyのスキーマ修正（TAGS, TAG_STATUS, TAG_TRANSLATIONS, TAG_USAGE_COUNTS）
- [ ] 実DBスキーマ文書化（Serenaメモリ: dataset_builder_tags_v4_schema_specification）
- [ ] スキーマ検証テスト追加（test_schema_compatibility.py）

**成功基準**:
- test_database.pyの全テーブルスキーマが実DBと完全一致
- `PRAGMA table_info(TABLE_NAME)`でカラム定義比較テスト追加

#### 5.1.2 実クエリの文書化（中優先度）

**問題**: インデックス戦略の根拠不足（完了記録で推測のみ）

**対応**:
1. genai-tag-db-tools/TagRepositoryの実SQLを確認
2. Serenaメモリに記録（dataset_builder_query_patterns_and_index_strategy）
3. EXPLAIN QUERY PLANで実行計画検証

**実装タスク**:
- [ ] TagRepositoryの全メソッドの実SQLを抽出
- [ ] 各クエリのEXPLAIN QUERY PLAN結果記録（Serenaメモリ）
- [ ] idx_tags_tag とUNIQUE制約の重複検証
- [ ] idx_usage_counts_count の効果測定

**成功基準**:
- 全検索メソッドの実SQLが文書化
- インデックスあり/なしの実行時間比較データ取得

### 5.2 PRAGMA設定修正（Day 3-4）

**問題**: 接続単位のPRAGMA設定が効果なし（build/optimizeで接続を閉じるため）

#### 5.2.1 BUILD_TIME_PRAGMAS/DISTRIBUTION_PRAGMASの再分類

**現状**:
```python
BUILD_TIME_PRAGMAS = [
    "PRAGMA journal_mode = OFF;",         # ✅ 永続化
    "PRAGMA synchronous = OFF;",          # ✅ DB状態
    "PRAGMA cache_size = -128000;",       # ❌ 接続単位
    "PRAGMA temp_store = MEMORY;",        # ❌ 接続単位
    "PRAGMA locking_mode = EXCLUSIVE;",   # ❌ 接続単位
]
```

**修正後**:
```python
# database.py

# 永続化されるPRAGMA（create_database/optimize_databaseで設定）
PERSISTENT_PRAGMAS = {
    "build": [
        "PRAGMA journal_mode = OFF;",
        "PRAGMA synchronous = OFF;",
    ],
    "distribution": [
        "PRAGMA journal_mode = WAL;",
        "PRAGMA synchronous = NORMAL;",
    ]
}

# 接続単位のPRAGMA（各フェーズの接続ごとに設定）
CONNECTION_PRAGMAS = [
    "PRAGMA cache_size = -128000;",
    "PRAGMA temp_store = MEMORY;",
    "PRAGMA locking_mode = EXCLUSIVE;",
]
```

#### 5.2.2 builder.pyの修正

**Phase 1-4の各CSV取り込み処理で接続ごとにPRAGMAを適用**:

```python
# builder.py

def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    """接続ごとにPRAGMAを適用"""
    for pragma in CONNECTION_PRAGMAS:
        conn.execute(pragma)

def build_dataset(...):
    # Phase 1: tags_v4.db取り込み
    conn = sqlite3.connect(output_path)
    _apply_connection_pragmas(conn)  # ← 追加
    # ... 取り込み処理 ...
    conn.close()

    # Phase 2: CSV取り込み
    conn = sqlite3.connect(output_path)
    _apply_connection_pragmas(conn)  # ← 追加
    # ... 取り込み処理 ...
    conn.close()
```

**実装タスク**:
- [ ] database.pyのPRAGMA設定再分類
- [ ] _apply_connection_pragmas()関数実装
- [ ] builder.pyの全フェーズで接続ごとにPRAGMA適用
- [ ] ビルド時間のベンチマーク（修正前後の比較）

**成功基準**:
- 狙いの接続でPRAGMAが適用される（ログ/PRAGMA値確認）
- ビルド時間のベンチマーク測定完了

### 5.3 データ整合性検証（Day 5-6）

#### 5.3.1 外部キー制約検証

**実装**:
```python
# tests/integration/test_schema_integrity.py

def test_foreign_key_constraints(built_db_path):
    """全外部キー制約が満たされることを確認"""
    conn = sqlite3.connect(built_db_path)
    
    # TAG_STATUS.tag_id → TAGS.tag_id
    result = conn.execute("""
        SELECT COUNT(*) FROM TAG_STATUS ts
        LEFT JOIN TAGS t ON ts.tag_id = t.tag_id
        WHERE t.tag_id IS NULL
    """).fetchone()[0]
    assert result == 0, "TAG_STATUS has invalid tag_id references"
    
    # TAG_STATUS.preferred_tag_id → TAGS.tag_id
    # TAG_TRANSLATIONS.tag_id → TAGS.tag_id
    # TAG_USAGE_COUNTS.tag_id → TAGS.tag_id
    # ... 全外部キーを検証 ...
```

#### 5.3.2 CHECK制約検証

**実装**:
```python
def test_check_constraints(built_db_path):
    """CHECK制約が満たされることを確認"""
    conn = sqlite3.connect(built_db_path)
    
    # alias=0時はpreferred_tag_id=tag_id
    result = conn.execute("""
        SELECT COUNT(*) FROM TAG_STATUS
        WHERE alias = 0 AND preferred_tag_id != tag_id
    """).fetchone()[0]
    assert result == 0, "alias=0 but preferred_tag_id != tag_id"
    
    # alias=1時はpreferred_tag_id!=tag_id
    result = conn.execute("""
        SELECT COUNT(*) FROM TAG_STATUS
        WHERE alias = 1 AND preferred_tag_id = tag_id
    """).fetchone()[0]
    assert result == 0, "alias=1 but preferred_tag_id = tag_id"
```

#### 5.3.3 重複排除検証

**実装**:
```python
def test_unique_constraints(built_db_path):
    """UNIQUE制約が満たされることを確認"""
    conn = sqlite3.connect(built_db_path)
    
    # TAGS.tag UNIQUE
    result = conn.execute("""
        SELECT tag, COUNT(*) as cnt FROM TAGS
        GROUP BY tag HAVING cnt > 1
    """).fetchall()
    assert len(result) == 0, f"Duplicate tags found: {result}"
    
    # TAG_TRANSLATIONS UNIQUE(tag_id, language, translation)
    # TAG_USAGE_COUNTS UNIQUE(tag_id, format_id)
    # ... 全UNIQUE制約を検証 ...
```

**実装タスク**:
- [ ] test_schema_integrity.py作成（外部キー、CHECK、UNIQUE制約）
- [ ] 実データでの整合性検証
- [ ] 衝突検出レポート（type_id_conflicts.csv, alias_changes.csv）の検証

### 5.4 パフォーマンス測定（Day 7-8）

#### 5.4.1 ビルド時間測定

**実装**:
```python
# tests/performance/test_build_performance.py

def test_full_build_time():
    """フルビルド時間を測定"""
    start_time = time.time()
    
    # tags_v4.db + CSV全ファイル
    build_dataset(
        output_path=Path("test_output.db"),
        tags_v4_path=Path("tags_v4.db"),
        csv_dir=Path("TagDB_DataSource_CSV"),
    )
    
    elapsed = time.time() - start_time
    assert elapsed < 9000, f"Build time {elapsed}s exceeds 150min"  # 150分 = 9000秒
```

#### 5.4.2 クエリパフォーマンス測定

**実装**:
```python
def test_query_performance(built_db_path):
    """検索クエリのパフォーマンスを測定"""
    conn = sqlite3.connect(built_db_path)
    
    # タグ名部分一致検索
    start = time.time()
    conn.execute("SELECT * FROM TAGS WHERE tag LIKE '%witch%'").fetchall()
    elapsed = time.time() - start
    assert elapsed < 0.1, f"Search query {elapsed}s > 100ms"
    
    # 使用回数ソート
    # 翻訳取得
    # ... 全クエリパターンを測定 ...
```

**実装タスク**:
- [ ] ビルド時間測定（tags_v4.db + CSV全ファイル）
- [ ] クエリパフォーマンス測定（全検索パターン）
- [ ] インデックス効果の実測（あり/なし比較）
- [ ] メモリ使用量測定

**成功基準**:
- ビルド時間: 75-150分以内
- タグ名検索: <100ms
- 使用回数ソート: <100ms

### 5.5 テスト実行環境の文書化（Day 9-10）

**問題**: Phase 3完了記録に実行環境前提が不足

**対応**:
Serenaメモリ `dataset_builder_testing_guide` に以下の内容を記録：

```markdown
## テスト実行環境

**必須環境**:
- Python: 3.12.12
- UV: 0.5.0+
- Dependencies: `uv sync --dev`

**テスト実行コマンド**:
```bash
# プロジェクトルートから実行
cd /workspaces/LoRAIro
uv run pytest local_packages/genai-tag-db-dataset-builder/tests/

# カバレッジ付き
uv run pytest local_packages/genai-tag-db-dataset-builder/tests/ --cov=genai_tag_db_dataset_builder --cov-report=xml
```

**CI環境**:
- GitHub Actions: ubuntu-latest
- Python: 3.12
- Cache: uv cache
```

**実装タスク**:
- [ ] Serenaメモリ dataset_builder_testing_guide 作成
- [ ] 実行環境セクション追加
- [ ] テスト実行コマンド文書化
- [ ] CI/CD設定の文書化

### 5.6 完了記録の修正とドキュメント整備（Day 11-12）

**対応**:
```markdown
# Phase 3完了記録（修正版）

## PRAGMA設定の正確な説明

**永続化されるPRAGMA**:
- journal_mode: ✅ DBファイルに永続化
- synchronous: ✅ DB状態として残る

**接続単位のPRAGMA**（builder.pyの各接続で設定が必要）:
- cache_size: ❌ 接続を閉じると無効
- temp_store: ❌ 接続を閉じると無効
- locking_mode: ❌ 接続を閉じると無効

## テストスキーマの実DB互換性

**test_database.pyのスキーマ**:
- Phase 5で実DBスキーマと完全一致に修正
- TAG_STATUS.type_id: nullable → NOT NULL
- 全テーブルで実DBスキーマを文書化

## インデックス戦略の根拠

**実クエリベースの検証**:
- genai-tag-db-tools/TagRepositoryの実SQL確認済み
- EXPLAIN QUERY PLANで実行計画検証済み
- インデックスあり/なしの実行時間比較データ取得
```

**実装タスク**:
- [ ] Phase 3完了記録の修正
- [ ] PRAGMAの永続性マトリクス追加
- [ ] 実行環境セクション追加
- [ ] インデックス戦略の根拠追記
- [ ] Serenaメモリ作成（dataset_builder_tags_v4_schema_specification, dataset_builder_query_patterns_and_index_strategy, dataset_builder_testing_guide, dataset_builder_local_build_guide, dataset_builder_troubleshooting）

---

## Phase 6: ローカルビルド（Week 10-11）

### 6.1 ローカルビルド実行（Day 1-3）

**準備**:
1. データソース配置
   - tags_v4.db配置
   - TagDB_DataSource_CSV配置

2. ビルド実行
```bash
cd /workspaces/LoRAIro
uv run python -m genai_tag_db_dataset_builder.builder \
    --output local_tag_database.db \
    --tags-v4 tags_v4.db \
    --csv-dir TagDB_DataSource_CSV \
    --unknown-report-dir reports/unknown \
    --overrides column_type_overrides.json
```

3. ビルド検証
   - データ整合性検証（FK/CHECK/UNIQUE制約）
   - パフォーマンス測定（ビルド時間、代表クエリ）
   - サイズ確認

**実装タスク**:
- [ ] builder.pyのCLIインターフェース実装
- [ ] ビルド実行スクリプト作成
- [ ] ビルドログ収集
- [ ] 衝突レポート（type_id_conflicts.csv, alias_changes.csv）の手動レビュー

### 6.2 レポート確認・手動修正（Day 4-6）

**対応内容**:
1. UNKNOWN判定レポート確認
   - `reports/unknown/*.tsv` のレビュー
   - 必要に応じて `column_type_overrides.json` 作成
   - 再ビルド

2. 衝突レポート確認
   - `type_id_conflicts.csv` のレビュー
   - `alias_changes.csv` のレビュー
   - 手動修正が必要な箇所の特定

3. データ品質確認
   - 外部キー制約違反チェック
   - UNIQUE制約違反チェック
   - CHECK制約違反チェック

**実装タスク**:
- [ ] UNKNOWNレポートの手動レビュー
- [ ] 衝突レポートの手動レビュー
- [ ] データ品質検証の実行
- [ ] 必要に応じて再ビルド

### 6.3 ローカルビルド完了記録作成（Day 7）

**内容**:
```markdown
# Local Tag Database Build Completion Report

## ビルド日
2025-12-XX

## 概要
ローカルソース（tags_v4.db + TagDB_DataSource_CSV）からの統合タグデータベース構築完了。

## データソース
- tags_v4.db: 993,514タグ（基盤データ）
- TagDB_DataSource_CSV: 各投稿サイトのローカルデータ

## ビルド結果
- 総タグ数: X,XXX,XXX
- エイリアス数: XXX,XXX
- 翻訳数: XXX,XXX
- データベースサイズ: XXXMB
- ビルド時間: XXX分

## 品質検証結果
- 外部キー制約: 100%パス
- CHECK制約: 100%パス
- UNIQUE制約: 100%パス
- UNKNOWN率: X.X%

## 既知の制限事項
- UNKNOWN判定されたソース: X件（reports/unknown参照）
- type_id衝突: X件（type_id_conflicts.csv参照）

## 次のステップ（Phase 7）
- 外部データセット統合（deepghs/site_tags, danbooru-wiki-2024）
- HuggingFace公開
- ライセンス確定
```

**実装タスク**:
- [ ] 完了記録の作成（Serenaメモリ: dataset_builder_phase6_local_build_completion_report）
- [ ] Phase 7への引き継ぎ事項整理



---

## 成功基準

### Phase 5成功基準（テスト・検証）

**技術的負債対応**:
- [ ] テストスキーマの実DB互換化（高優先度）
- [ ] PRAGMAの接続単位設定の実装（高優先度）
- [ ] 実クエリの文書化とインデックス再設計（中優先度）
- [ ] 完了記録の修正（中優先度）

**テスト・検証**:
- [ ] 全テストスイート実行（unit + integration）
- [ ] データ整合性検証（FK/CHECK/UNIQUE）
- [ ] パフォーマンス測定（ビルド時間・代表クエリ）
- [ ] カバレッジ≥75%（目標、必要に応じて見直し）

### Phase 6成功基準（ローカルビルド）

**ビルド**:
- [ ] ローカルフルビルド成功（`tags_v4.db` + `TagDB_DataSource_CSV`）
- [ ] スキップ/UNKNOWN/衝突/孤立参照のレポートが出力され、手動修正が可能

**公開（Phase 7へ後回し）**:
- [ ] HuggingFace公開 / Dataset Card / リリースノート / ライセンス整備は Phase 7 で対応

---

## リスク管理

### 高リスク

1. **ビルド時間超過**
   - 発生確率: 中
   - 影響度: 高
   - 対策: PRAGMA最適化、並列処理検討

2. **データ整合性違反**
   - 発生確率: 中
   - 影響度: 高
   - 対策: Integration Tests強化、外部キー制約検証

### 中リスク

3. **UNKNOWN率の大量発生**
   - 発生確率: 中
   - 影響度: 中
   - 対策: overrides.json準備、手動レビュー体制

4. **パフォーマンス劣化**
   - 発生確率: 低
   - 影響度: 中
   - 対策: インデックス最適化、PRAGMA調整

### 低リスク

5. **レポート見落とし**
   - 発生確率: 低
   - 影響度: 中
   - 対策: レポート確認手順の文書化、チェックリスト作成

---

## タイムライン

### Phase 5: テスト・検証（Week 8-9、12日間）

- Day 1-2: テストスキーマの実DB互換化
- Day 3-4: PRAGMA設定修正
- Day 5-6: データ整合性検証
- Day 7-8: パフォーマンス測定
- Day 9-10: テスト実行環境の文書化
- Day 11-12: 完了記録の修正

### Phase 6: ローカルビルド（Week 10-11、7日間）

- Day 1-3: ローカルビルド実行（tags_v4.db + TagDB_DataSource_CSV）
- Day 4-6: レポート確認・手動修正（UNKNOWN/衝突/データ品質）
- Day 7: ローカルビルド完了記録作成

**総所要時間**: 19日間（Phase 5: 12日 + Phase 6: 7日）

---

## 次のステップ

1. **Phase 5開始**: テストスキーマの実DB互換化から着手
2. **PRAGMA修正**: builder.pyの接続ごとにPRAGMA適用
3. **データ整合性検証**: Integration Tests追加
4. **Phase 6完了後**: Phase 7で外部データセット統合・HuggingFace公開

---

## 設計決定の記録

### 技術的負債対応の統合

**決定**: Phase 5にPlan Modeで指摘された技術的負債対応を統合

**理由**:
- Phase 5（テスト・検証）は品質保証フェーズであり、負債対応に最適
- Phase 6（初回ビルド）前に全問題を解決することで、初回ビルドの成功確率を高める

**トレードオフ**:
- Phase 5の期間が延長（8日 → 12日）
- しかし、Phase 6での問題発生リスクを大幅に削減

### PRAGMAの再分類

**決定**: PERSISTENT_PRAGMAS と CONNECTION_PRAGMAS に分離

**理由**:
- 永続化されるPRAGMAと接続単位のPRAGMAの混在が誤解を招いていた
- 明示的に分離することで、builder.pyでの正しい適用が可能

**影響**:
- database.pyの修正が必要
- builder.pyの全接続で_apply_connection_pragmas()呼び出しが必要

### テストスキーマの実DB互換化

**決定**: test_database.pyのスキーマを実DBと完全一致させる

**理由**:
- テストが「実DBで動作する保証」になっていなかった
- 実DBスキーマとの不一致により、本番環境での問題発生リスク

**トレードオフ**:
- テストデータの作成が若干厳格になる（type_id NOT NULL）
- しかし、実DB互換性の保証が得られる

### Phase 6スコープの限定

**決定**: Phase 6はローカルソースのみ（tags_v4.db + TagDB_DataSource_CSV）、外部データセットはPhase 7

**理由**:
- Phase 2.5の方針（ローカル優先・公開は後で）を継承
- ローカルビルドで技術的負債対応の効果を検証
- 外部データセット統合前にプロセスの安定性を確認

**影響**:
- HuggingFace公開、ライセンス確定、外部データセット統合は全てPhase 7に後回し
- Phase 6の成功基準からビルド時間・サイズの具体的数値目標を削除

---

## 参照

- **Plan Mode プラン**: /home/vscode/.claude/plans/ethereal-chasing-eagle.md
- **Phase 3完了記録**: dataset_builder_phase3_completion_2025_12_13
- **Phase 2.5完了記録**: dataset_builder_phase2_5_completion_report_2025_12_14
- **Phase 2.5実装計画**: dataset_builder_phase2_5_implementation_plan_2025_12_14
- **Phase 2.5ギャップ分析**: dataset_builder_phase2_5_input_normalization_gap_analysis_2025_12_14
- **設計計画**: dataset_builder_design_plan_2025_12_13
- **仕様書（Phase 2完了時作成）**:
  - dataset_builder_source_priority_and_conflict_resolution_spec_2025_12_14
  - dataset_builder_build_reproducibility_guarantee_spec_2025_12_14
  - dataset_builder_alias_registration_precondition_spec_2025_12_14
- **Phase 2完了記録**:
  - dataset_builder_phase2_data_loss_fix_implementation_plan_2025_12_14
  - dataset_builder_phase2_data_loss_fix_day1_completion_2025_12_14
  - dataset_builder_phase2_data_loss_fix_day2_completion_2025_12_14
  - dataset_builder_phase2_data_loss_fix_day3_completion_2025_12_14
  - dataset_builder_phase_2_4_completion_summary_2025_12_14
- **その他関連メモリ**:
  - dataset_builder_overrides_feature_completion_2025_12_14
  - dataset_builder_tag_database_hybrid_architecture_pattern_2025_12_13
  - dataset_builder_tag_database_integration_redesign_plan_v2_2025_12_13

---

**策定者**: Claude Sonnet 4.5
**策定日**: 2025年12月15日
