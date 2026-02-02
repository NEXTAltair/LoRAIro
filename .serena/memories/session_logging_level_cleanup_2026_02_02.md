# Session: ログレベル整理とロギング指針策定

**Date**: 2026-02-02
**Branch**: feature/annotator-library-integration
**Status**: completed

---

## 実装結果

### 1. 登録処理のper-item INFOログをDEBUGに変更（全3セッション）

画像登録時に1画像あたり5行以上のINFOログが出力される問題を修正。
5つのレイヤーにまたがるper-itemログを全てDEBUGに変更。

**変更ファイル:**

| ファイル | メソッド | 変更内容 |
|---|---|---|
| `db_repository.py` | `add_original_image` | INFO→DEBUG: "オリジナル画像をDBに追加しました" |
| `db_repository.py` | `find_duplicate_image_by_phash` | INFO→DEBUG: "pHashによる重複画像が見つかりました" |
| `db_repository.py` | `add_processed_image` | INFO→DEBUG: "処理済み画像をDBに追加しました" + "既存の処理済み画像IDが見つかりました" |
| `db_repository.py` | `save_annotations` | INFO→DEBUG: "画像ID X のアノテーションを保存・更新しました" |
| `file_system.py` | `save_processed_image` | INFO→DEBUG: "処理済み画像を保存" |
| `image_processor.py` | `__init__` | INFO→DEBUG: "ImageProcessingManagerが正常に初期化" |
| `db_manager.py` | `detect_duplicate_image` | INFO→DEBUG: "重複検出: pHash一致" |
| `db_manager.py` | `register_original_image` | INFO→DEBUG (前セッション) |
| `db_manager.py` | `register_processed_image` | INFO→DEBUG (前セッション) |
| `db_manager.py` | `_generate_thumbnail_512px` | INFO→DEBUG (前セッション) |
| `db_manager.py` | `save_tags` | INFO→DEBUG (前セッション) |
| `registration_worker.py` | `_process_associated_files` | INFO→DEBUG: タグ追加、キャプション追加 |
| `batch_processor.py` | `_import_tag_file` | INFO→DEBUG: タグ追加 |
| `batch_processor.py` | `_import_caption_file` | INFO→DEBUG: キャプション追加 |
| `batch_processor.py` | `_process_single_image` | INFO→DEBUG: 画像登録成功 |

### 2. ロギング指針の策定

- `.claude/rules/logging.md` を新規作成
- Serena Memory `logging_guidelines` を更新
- `CLAUDE.md` のLogging項目を拡充

## 設計意図

### なぜ「1万件でも読める量」を基準にしたか
- LoRAIroは数百〜数千枚の画像をバッチ処理する
- INFOレベルは運用監視用であり、常時有効
- per-itemログがINFOだと、821件処理で4000行以上のログが発生し実用的でない

### なぜ3つの禁止パターンを明文化したか
1. **多層重複ログ**: 今回の問題の直接原因。Repository/Manager/Worker/FileSystemの5層が同じ操作をINFOで出力していた
2. **毎回生成オブジェクトの初期化ログ**: ImageProcessingManagerが画像ごとに生成・破棄されるのにINFOを出していた
3. **ループ内INFO**: 上記2つの根本的な判断基準

## 問題と解決

### 問題1: 最初の修正が不十分だった
- 1回目: registration_worker.py + batch_processor.py のみ修正
- ユーザーテストで「まだうるさい」→ 実ログを確認すると db_manager.py が出力元
- 2回目: db_manager.py を修正
- ユーザーテストで「まだうるさい」→ 実ログを確認すると db_repository.py, file_system.py, image_processor.py が出力元
- 3回目: 残り全箇所を修正 → 解決

**教訓**: ログの出力元はログファイルの `module:function` 表記で特定する。コードレビューだけでなく実ログを見るべき。

### 問題2: 同じ処理が複数レイヤーで重複
- 登録フロー: Worker → db_manager → db_repository → file_system
- 各レイヤーが独自にINFOログを出力 → 1件あたり5行以上
- 解決: 低レイヤーは全てDEBUG、サマリーだけINFO

## 未完了・次のステップ

- 起動時の初期化ログ（100行以上のINFO）も整理候補だが、今回はスコープ外
- 既存コード全体へのlogging.mdルール適用は段階的に実施