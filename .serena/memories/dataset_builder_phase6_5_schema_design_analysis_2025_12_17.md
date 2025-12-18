# Phase 6.5 Schema Design Analysis: deepghs/site_tags Integration

## 策定日
2025年12月17日

## 分析目的

`deepghs/site_tags` の18サイト統合に伴うスキーマ変更計画を多角的に検討し、最適な設計アプローチを選定する。

---

## 現行計画（Approach A: TAG_FORMATS Extension）

### 提案スキーマ

```sql
-- 現在
CREATE TABLE TAG_FORMATS (
    format_id INTEGER PRIMARY KEY AUTOINCREMENT,
    format_name TEXT NOT NULL UNIQUE,
    description TEXT
);

-- 拡張後
ALTER TABLE TAG_FORMATS ADD COLUMN source_url TEXT;
ALTER TABLE TAG_FORMATS ADD COLUMN license TEXT;
ALTER TABLE TAG_FORMATS ADD COLUMN last_updated TEXT;
```

### 追加カラムの用途

1. **source_url**: データソースURL（例: `https://huggingface.co/datasets/deepghs/site_tags`）
2. **license**: ライセンス識別（CC0-1.0, MIT, CC-BY-4.0）
3. **last_updated**: 最終更新タイムスタンプ（ISO 8601形式）

### Approach A の評価

**Pros（長所）**:
- ✅ 実装が単純（ALTER TABLE x3のみ）
- ✅ 全format情報が1テーブルに集約（JOIN不要）
- ✅ 後方互換性あり（既存クエリは影響なし）
- ✅ 既存パターン踏襲（description列と同じ性質）
- ✅ マイグレーション容易（NULL許容で段階的移行可）

**Cons（短所）**:
- ❌ 関心の分離違反（format識別とビルドメタデータの混在）
- ❌ カラム制約なし（source_url/license/last_updatedは全てNULL許容）
- ❌ 複数ソース対応困難（danbooruが tags_v4.db + deepghs 両方から来る場合）
- ❌ テーブル幅増加（3 TEXT列追加）
- ❌ 将来拡張でALTER TABLE繰り返し

**クエリパターン分析**:
- 想定クエリ頻度: **低**（管理・デバッグ用のみ）
- 例: "Which formats are CC-BY-4.0?" → 年数回程度
- 例: "When was e621 last updated?" → デバッグ時のみ

**パフォーマンス影響**:
- TAG_FORMATS行数: 20〜50行程度（微小）
- インデックス不要（管理クエリのみ）
- 影響: **無視できるレベル**

---

## Alternative Approach B: 分離メタデータテーブル

### 提案スキーマ

```sql
CREATE TABLE TAG_FORMAT_METADATA (
    format_id INTEGER PRIMARY KEY,
    source_url TEXT,
    license TEXT,
    last_updated TEXT,
    data_version TEXT,           -- 将来拡張用
    contributor TEXT,            -- 将来拡張用
    FOREIGN KEY(format_id) REFERENCES TAG_FORMATS(format_id)
);
```

### Approach B の評価

**Pros（長所）**:
- ✅ 関心の分離（core識別とメタデータ分離）
- ✅ 将来拡張容易（メタデータ列追加でALTER TABLE不要）
- ✅ TAG_FORMATSをクリーンに保つ
- ✅ メタデータ不要なformatは行自体を持たない（省スペース）
- ✅ 1:1関係の明示化（format_id PK）

**Cons（短所）**:
- ❌ JOIN必要（format情報取得時）
- ❌ スキーマ複雑化（2テーブル管理）
- ❌ マイグレーション複雑（新テーブル作成+データ移行）
- ❌ 小規模データでのオーバーヘッド（~50行程度）

**クエリ例**:
```sql
-- format情報取得（JOIN必要）
SELECT f.format_name, m.license, m.last_updated
FROM TAG_FORMATS f
LEFT JOIN TAG_FORMAT_METADATA m ON f.format_id = m.format_id
WHERE f.format_name = 'danbooru';
```

**適用シナリオ**:
- メタデータが頻繁に更新される場合
- メタデータ項目が10個以上に増える見込み
- メタデータの有無でformat扱いを変える場合

---

## Alternative Approach C: JSON Metadata Column

### 提案スキーマ

```sql
ALTER TABLE TAG_FORMATS ADD COLUMN metadata TEXT;  -- JSON文字列

-- 使用例
-- {"source_url": "https://...", "license": "CC0-1.0", "last_updated": "2025-12-17T00:00:00Z"}
```

### Approach C の評価

**Pros（長所）**:
- ✅ 最大の拡張柔軟性（スキーマ変更不要）
- ✅ 単一列追加のみ（ALTER TABLE x1）
- ✅ 将来のメタデータ項目追加が自由

**Cons（短所）**:
- ❌ SQLiteのJSON関数は限定的（PostgreSQLのJSONBなし）
- ❌ 型安全性喪失（全て文字列）
- ❌ インデックス不可（license等での検索が非効率）
- ❌ アプリケーション層でのJSON parse必須
- ❌ データ検証が困難（スキーマレス）

**SQLite JSON制約**:
- `json_extract()` 関数は利用可能
- ただしインデックス作成不可（Generated Columnで回避可能だが複雑）
- パフォーマンス: 小規模データでは問題ないが、拡張性に疑問

**適用シナリオ**:
- メタデータ構造が頻繁に変わる場合
- スキーマ変更を極力避けたい場合
- **本プロジェクトには不適合**（構造化データ向き）

---

## Alternative Approach D: 複数ソース対応設計

### 背景: 複数ソース問題

**問題**:
- `danbooru` formatは tags_v4.db からも deepghs/site_tags からも来る
- 現行計画では source_url に「どちらのURL」を入れるか不明確
- ライセンスも source ごとに異なる可能性

### 提案スキーマ（データ来歴追跡）

```sql
CREATE TABLE DATA_SOURCES (
    source_id INTEGER PRIMARY KEY,
    source_name TEXT UNIQUE NOT NULL,  -- 'tags_v4_db', 'deepghs_site_tags'
    source_url TEXT,
    license TEXT,
    last_updated TEXT,
    description TEXT
);

CREATE TABLE FORMAT_SOURCE_MAPPING (
    format_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    PRIMARY KEY (format_id, source_id),
    FOREIGN KEY(format_id) REFERENCES TAG_FORMATS(format_id),
    FOREIGN KEY(source_id) REFERENCES DATA_SOURCES(source_id)
);
```

### Approach D の評価

**Pros（長所）**:
- ✅ 正確なデータ来歴追跡（多対多関係）
- ✅ 同一formatの複数ソース対応
- ✅ ソース単位でのライセンス管理
- ✅ 将来のソース追加が容易

**Cons（短所）**:
- ❌ 設計複雑度が大幅増加（3テーブル管理）
- ❌ クエリ複雑化（2段JOIN必要）
- ❌ 現時点の要件に対してオーバーエンジニアリング
- ❌ 実装・テスト工数増大

**クエリ例**:
```sql
-- danbooruの全ソース取得
SELECT s.source_name, s.license, s.last_updated
FROM TAG_FORMATS f
JOIN FORMAT_SOURCE_MAPPING m ON f.format_id = m.format_id
JOIN DATA_SOURCES s ON m.source_id = s.source_id
WHERE f.format_name = 'danbooru';
```

**適用シナリオ**:
- データ来歴が法的要件の場合
- 監査ログが必須の場合
- **現時点では過剰**（Phase 7で検討）

---

## 要件再確認

### 機能要件

1. **データソース識別**: 各formatがどこから来たか記録
2. **ライセンス管理**: format単位でライセンス識別
3. **更新追跡**: 最終ビルド日時の記録
4. **後方互換性**: 既存CC0/MIT版への影響最小化

### 非機能要件

1. **実装容易性**: Phase 6.5 の 4週間で完了可能
2. **マイグレーション安全性**: 既存DBの破壊リスク最小化
3. **クエリ性能**: 管理クエリの応答時間（重要度: 低）
4. **将来拡張性**: Phase 7でのリポジトリ自動化対応

---

## 設計選定基準

### 評価軸

| 評価軸 | 重み | Approach A | Approach B | Approach C | Approach D |
|-------|------|-----------|-----------|-----------|-----------|
| **実装容易性** | 高 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ |
| **マイグレーション安全性** | 高 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **関心の分離** | 中 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **将来拡張性** | 中 | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **クエリ性能** | 低 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **型安全性** | 中 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |

### 総合スコア（加重平均）

- **Approach A**: 4.1/5.0（現行計画）
- **Approach B**: 3.7/5.0（分離メタデータ）
- **Approach C**: 3.0/5.0（JSON列）
- **Approach D**: 2.8/5.0（複数ソース対応）

---

## 潜在的問題の分析

### 問題1: 複数ソースの取り扱い

**現状**:
- tags_v4.db に danbooru データあり
- deepghs/site_tags に danbooru データあり
- 同一 format_name に複数ソース

**Approach A での対処**:
- source_url: "最も権威あるソース"または"最新ソース"のURLのみ記録
- 例: `https://huggingface.co/datasets/deepghs/site_tags`
- 制約: 複数ソースの追跡は DATABASE_METADATA で補完

**Approach D での対処**:
- DATA_SOURCES テーブルで全ソースを追跡
- FORMAT_SOURCE_MAPPING で多対多関係
- 完全な来歴追跡が可能

**推奨**:
- Phase 6.5: Approach A（単一ソースURL）
- Phase 7: 必要に応じて Approach D へ移行検討

### 問題2: license 列の意味

**解釈1: Format固有ライセンス**
- 例: danbooruは CC-BY-4.0（公式サイトのライセンス）
- 用途: ユーザーへのライセンス情報提供

**解釈2: ビルド単位ライセンス**
- 例: CC0版ビルドでは全て CC0-1.0
- 用途: ビルド成果物のライセンス識別

**現行計画の解釈**: **解釈1（Format固有）**
- `UPDATE TAG_FORMATS SET license = 'CC0-1.0' WHERE format_name IN ('danbooru', 'e621');`
- これはdanbooru formatのライセンスを CC0-1.0 に設定（format固有）

**問題点**:
- CC4版では danbooru は CC-BY-4.0 になるが、同じDBにCC0のe621も含まれる
- license列が「format固有」なら、ビルド単位のライセンスはどこに記録？

**解決策**:
- DATABASE_METADATA に `build.license = 'CC-BY-4.0'` を追加
- TAG_FORMATS.license は format固有ライセンス
- 両方を記録して混乱回避

### 問題3: last_updated の粒度

**解釈1: Format単位更新日時**
- deepghs/site_tags の danbooru が最終更新された日時

**解釈2: ビルド実行日時**
- このDBをビルドした日時（全format共通）

**現行計画の解釈**: **解釈1（Format単位）**が妥当

**実装課題**:
- deepghs/site_tags は Git リポジトリ
- 各サイトフォルダの最終コミット日時を取得？
- または Parquet ファイルの更新日時を使用？

**推奨**:
- deepghs/site_tags からの取得時に Git commit date を記録
- Phase 7 で自動取得実装

---

## 代替案の提案

### Hybrid Approach: Approach A + DATABASE_METADATA

**設計**:
1. TAG_FORMATS に source_url, license, last_updated を追加（Approach A）
2. DATABASE_METADATA に以下を記録:
   ```
   build.license = 'CC-BY-4.0'
   build.timestamp = '2025-12-17T12:00:00Z'
   build.base_db = 'tags_v4.db + deepghs/site_tags'
   ```

**利点**:
- Format固有情報とビルド情報を分離
- 単純な実装（Approach A維持）
- ビルド全体のメタデータも記録

**欠点**:
- 2箇所にメタデータ分散（TAG_FORMATS + DATABASE_METADATA）
- 整合性管理が必要

---

## 最終推奨

### Phase 6.5 での採用: **Approach A（改良版）**

**理由**:
1. ✅ 実装容易性（4週間で完了可能）
2. ✅ マイグレーション安全性（ALTER TABLE のみ）
3. ✅ 後方互換性（既存クエリ影響なし）
4. ✅ 要件充足（現時点の要件を満たす）

**改良点**:
1. **DATABASE_METADATA にビルド情報追加**:
   ```sql
   INSERT INTO DATABASE_METADATA VALUES ('build.license', 'CC-BY-4.0');
   INSERT INTO DATABASE_METADATA VALUES ('build.timestamp', '2025-12-17T12:00:00Z');
   INSERT INTO DATABASE_METADATA VALUES ('build.base_sources', 'tags_v4.db, deepghs/site_tags');
   ```

2. **TAG_FORMATS.license の明確化**:
   - Docstringで「format固有ライセンス」と明記
   - ビルド全体のライセンスとは別物と文書化

3. **TAG_FORMATS.source_url の方針**:
   - 複数ソースがある場合は「最新ソース」のURLを記録
   - 例: deepghs/site_tags のURL
   - tags_v4.db からの継承分は NULL

4. **TAG_FORMATS.last_updated の取得方針**:
   - deepghs/site_tags: Git commit date または file mtime
   - tags_v4.db: ビルド実行日時

### Phase 7 での再検討事項

1. **Approach D（複数ソース対応）への移行**:
   - リポジトリ自動化で複数ソースが増える場合
   - データ来歴追跡が重要になる場合

2. **Approach B（分離メタデータ）への移行**:
   - メタデータ項目が10個以上に増える場合
   - TAG_FORMATS が肥大化する場合

---

## リスク評価

| リスク | 発生確率 | 影響度 | 対策 |
|-------|---------|-------|------|
| **複数ソース来歴不明** | 中 | 中 | DATABASE_METADATA に補足記録 |
| **license列の意味混乱** | 中 | 低 | Docstringで明確化 + build.license分離 |
| **将来拡張でALTER TABLE繰り返し** | 低 | 低 | Phase 7で Approach B 検討 |
| **マイグレーション失敗** | 低 | 高 | バックアップ必須、dry-run実装 |

---

## 実装チェックリスト（Approach A改良版）

### Week 1: スキーマ設計

- [ ] TAG_FORMATS 拡張SQL確定
- [ ] DATABASE_METADATA 追加項目確定
- [ ] マイグレーションスクリプト作成
- [ ] Docstring更新（license/source_url/last_updated意味明記）

### Week 2: マイグレーション実装

- [ ] builder.py に `--migrate-schema` オプション追加
- [ ] マイグレーション適用関数実装
- [ ] DATABASE_METADATA 書き込み処理追加
- [ ] ユニットテスト追加（test_migrate_schema.py）

### Week 3: 検証

- [ ] 既存CC0版DBでマイグレーション実行
- [ ] スキーマ検証（PRAGMA table_info）
- [ ] データ整合性確認（FK/CHECK/UNIQUE制約）
- [ ] ロールバック手順確認

### Week 4: CC0版再ビルド

- [ ] 新スキーマでCC0版フルビルド
- [ ] source_url/license/last_updated 自動設定
- [ ] DATABASE_METADATA 設定確認
- [ ] レポート確認

---

## 関連ドキュメント

- `dataset_builder_phase6_5_cc4_local_build_plan_2025_12_17.md`: 実装計画
- `dataset_builder_design_plan_2025_12_13.md`: 基本設計
- `dataset_builder_deepghs_site_tags_investigation_log_2025_12_17.md`: 調査ログ

---

**策定者**: Claude Sonnet 4.5  
**レビュー**: 未実施
