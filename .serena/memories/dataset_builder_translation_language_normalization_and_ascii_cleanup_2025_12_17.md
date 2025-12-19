# 作業記録: 翻訳language正規化 + ASCII-only翻訳の削除

## 日付
2025-12-17

## 目的
- tags_v4.db 由来の `TAG_TRANSLATIONS.language` が `japanese` / `zh-Hant` 等の表記揺れのままだと、Parquet出力（`language='ja'` / `language='zh'`）と整合しない。
- さらに、`language='japanese'` に英語などが誤登録されていると、`lang_ja` 汚染になる。

## 対応
1) tags_v4 取り込み時の language 正規化
- Phase 1で tags_v4.db の TAG_TRANSLATIONS を挿入する際に、`_normalize_language_value()`（内部で `_infer_language_code()`）を通す。
  - 例: `japanese -> ja`, `english -> en`, `zh-Hant -> zh`

2) ja/zh/ko の必須文字種フィルタ
- ユーザー決定: 絵文字/顔文字/記号/全角記号などは翻訳として不要なので削除。
- 実装: `_delete_translations_missing_required_script(conn, language)`
  - `ja`: ひらがな/カタカナ/漢字（CJK）を1文字も含まない翻訳を削除
  - `zh`: 漢字（CJK）を1文字も含まない翻訳を削除
  - `ko`: ハングルを1文字も含まない翻訳を削除
- 実ビルドログ例（CC0）:
  - `[Cleanup] Deleted 45140 translations lacking required script for ja`

3) 追加の中国語→日本語混入削除
- `Tags_zh_full.csv` の `zh-Hant` 値と一致する `language='ja'` を削除（既存方針）。

## 検証
- テスト: `pytest local_packages/genai-tag-db-dataset-builder -q` 全PASS。
- CC0 SQLite を再ビルドして、`TAG_TRANSLATIONS` の言語は `ja/zh` に正規化されることを確認。

## 追加観測（マルチバイト記号の混入）
- `language in ('ja','zh','ko')` でCJK/Hangul以外のマルチバイト記号（例: `\u2665`, 絵文字, 全角記号, ギリシャ文字など）が一定数存在する。
- ASCII-only ではないため今回の削除条件では残る（要否は今後判断）。
