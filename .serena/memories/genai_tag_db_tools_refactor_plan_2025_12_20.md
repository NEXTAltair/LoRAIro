# genai-tag-db-tools リファクタ計画（HF DB前提）

## 4) 起動/更新フロー

- 起動時に **HFの更新チェックを1回だけ** 行う（常時監視はしない）。
- ダウンロード完了後にDBを読み込む（起動直後に開かない）。
- オフライン時は **前回キャッシュ固定** で起動する。
- ベースDBに更新がある場合は **ベースを優先** し、ユーザーDBの変更を再適用する。
- ユーザーDBの変更とベースが競合する場合は **新しい日時の方を優先** する。
- 設定はAPI引数のみ（環境変数は使わない）。

## 7.1) APIモデル方針
- 外部向けAPIは **IDを露出しない**（TagRecord/TagRegisterResultからtag_idを除外）
- 外部検索条件は **文字列ベース**（format/typeは文字列、IDは受け取らない）
- 内部/整合性チェックのみ tag_id を使用（Repository/診断系）
- HF取得は **repo_id + filename** で特定（SQL検索での特定はしない）
- 固定URL一覧（repo_id/filename）
  - CC4: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db-CC4/blob/main/genai-image-tag-db-cc4.sqlite
  - MIT: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db-mit/blob/main/genai-image-tag-db-mit.sqlite
  - CC0: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db/blob/main/genai-image-tag-db-cc0.sqlite

## 8) 診断CLI（整合性チェック）
- 方針: ダウンロードDB単体の健全性ではなく、
  「ユーザーDB」と「ダウンロードDB」の整合性チェック
- 例: format/typeの存在、preferred_tag_idの整合、重複名の衝突影響

## 9) テスト戦略
- 単体→統合→GUIスモークで全面再設計

## 10) README/運用
- HF取得/キャッシュ場所の説明
- 統合ビュー/優先順位の説明
- 診断CLIの目的と使い方

## 11) 削除/修正の初期棚卸し（基準適用）

### 残す／再設計（必須）
- `src/genai_tag_db_tools/db/`:
  - `runtime.py`（DB初期化/セッション管理）
  - `schema.py`（HFスキーマへ差し替え前提）
  - `repository.py`（MergedTagRepository中心に再設計）
  - `db_maintenance_tool.py`（診断CLIとして再設計）
- `src/genai_tag_db_tools/io/hf_downloader.py`（HF取得・キャッシュ）
- `src/genai_tag_db_tools/services/`:
  - `tag_search.py`, `tag_register.py`, `tag_statistics.py`, `app_services.py`
- `src/genai_tag_db_tools/main.py`（CLI入口）
- `src/genai_tag_db_tools/utils/cleanup_str.py`（正規化）
- `src/genai_tag_db_tools/utils/messages.py`（メッセージ定義）

### 置換対象（移行して削除）
- 旧スキーマ依存の処理（旧 tags_v4 前提コード）
- 旧DB構築/取り込み系スクリプト（builder/CSV前提処理）

### 不確定（隔離候補）
- GUI層（API/CLI完成後に再設計）
  - `gui/windows/main_window.py`
  - `gui/widgets/*`
  - `gui/designer/*`

### 削除
- 旧DB作成/旧GUI/古いスクリプト/ローカルCSV前提
- `__pycache__/`（無視対象）

## 12) 未決事項
- 既存API互換範囲: **互換は重視しない（コード品質優先）**
- 診断CLIのチェック項目の最終確定


## 7) タグ統合・衝突ルール

- **同一タグ文字列で複数 tag_id を作らない**（登録段階でブロック）。
- usage_count は **合算しない**。最新日時の値を採用し、count が不変なら日付は更新しない。
- 翻訳は全言語を結合。**同一languageで異なる翻訳はリスト保持**（優先順位は付けない）。
- alias の推奨先が複数ある場合は **count が取れるなら最大**、取れないなら先勝ち＋レポート。
- invalid_tag / bad_tag は **redirectしない**（deprecated情報として記録のみ）。

## 13) 進捗（2025-12-21）
- 文字化けした既存ファイルをUTF-8で再生成（db/・services/の主要ファイル）。GUI系は対象外。
- `io/` ディレクトリを新設し、`hf_downloader.py` を実装（DL完了後に読み込む前提）。
- 公開API用に `core_api.py` を追加し、CLIはcore_api経由で呼び出す方針に変更。
- Pydanticモデルを整備（内部/外部を分離、外部はtag_idを露出しない）。検索条件は文字列のみ。
- CLI引数整理（`--revision` と `--max-cache-bytes` を削除、`--offset`は残す）。
- ユニットテスト追加: `test_hf_downloader.py` / `test_tag_repository.py` / `test_tag_register_service.py` / `test_tag_searcher.py`。
- キャッシュ構成: `cache_dir/base_dbs`, `cache_dir/user_db`, `cache_dir/metadata` + manifest運用。ユーザーDBの `DATABASE_METADATA` にSHA256追加予定（初回移行で列追加）。
- 統合ビュー/ユーザーDB運用: 検索は統合ビュー、登録はUserDB（Repository層で統合）。
- TagRegisterResult/TagRecord外部モデルはtag_id非公開、TagSearchRequestはformat/typeを文字列で受ける。
- HF取得は repo_id/filename 指定で固定（ファイル名指定方式で運用）。
