# 作業記録: lang_ja（=TAG_TRANSLATIONS.language='ja'）への中国語/英語混入対策

## 日付
2025-12-17

## 背景
HF Dataset Viewer の `lang_ja`（Parquet出力時に `TAG_TRANSLATIONS.language='ja'` を抽出）に、日本語以外（中国語/英語）が混ざって見える問題が出た。

ユーザー調査の結論:
- `tags_v4.db`（ベースDB）側で、非日本語が `language='japanese'` として誤登録されていた。
- ビルド時に `_infer_language_code()` で `japanese -> ja` に変換されるため、結果DBに `language='ja'` として混入する。
- Parquet出力ロジック（WHERE language='ja'）自体は正しい。

## 方針（ユーザー合意）
ビルダーのみを修正し、DBツール側は触らない。

- CC0版ビルド: `TagDB_DataSource_CSV/translation/Tags_zh_full.csv` の翻訳語（列 `zh-Hant`）と一致する `language='ja'` の翻訳レコードを削除して `lang_ja` 汚染を防ぐ。
- MIT版ビルド: `TagDB_DataSource_CSV/A/EnglishDictionary.csv` の語（列 `source_tag`）と一致する `language='ja'` の翻訳レコードを削除する。

※ ライセンス混入回避のため、**対象CSVが今回のビルドで include 判定される場合のみ**クリーンアップを行う。

## 実装
- `src/genai_tag_db_dataset_builder/builder.py`
  - tags_v4 取り込み（Phase 1）の `TAG_TRANSLATIONS.language` を `_normalize_language_value()` で正規化（例: `japanese -> ja`, `zh-Hant -> zh`）。
  - `_delete_ja_translations_by_value_list(conn, values)` を追加（TEMP表に詰めて `DELETE ... IN (SELECT ...)`）。
  - `_delete_translations_ascii_only_for_languages(conn, languages={'ja','zh','ko'})` を追加（ASCIIのみの翻訳は誤りとして削除）。
  - `_load_column_values_from_csv(csv_path, column_name, overrides, report_dir_path)` を追加。
  - Phase 2 終了後、Phase 2.5 前に cleanup を実行。
  - 実行時は `source_effects.tsv` に `action=cleanup_deleted` として記録。

## テスト
- 追加: `tests/unit/test_translation_cleanup.py`
  - `language='ja'` のみが削除されること
  - CSVから `zh-Hant` 列の値を読み取れること
- `pytest local_packages/genai-tag-db-dataset-builder -q` -> 全テストPASS

## 動作確認（ログ）
- MITビルドで以下のログを確認:
  - `[Cleanup] Deleted 264 ja translations based on TagDB_DataSource_CSV/A/EnglishDictionary.csv ...`
