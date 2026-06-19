---
type: ADR
title: タグ正規化責任の genai-tag-db-tools への集約
status: Accepted (Revised: 2026-06-16 — 解決タイミングを表示時から保存時へ変更)
timestamp: 2026-06-16
deciders: NEXTAltair
tags: []
---
# ADR 0068: タグ正規化責任の genai-tag-db-tools への集約

## Context

LoRAIro GUI の詳細表示に未整形タグが出るケースが報告された (Issue #769, image ID `14443`)。
例: `_touhou`, `blue_hair_`, `alternate_costume`, `Grey hair`, `Pov hands`, `bad_id`,
`bad_pixiv_id`, `__commentary_request`, `_highres` など。

調査の結果、原因は単一バグではなく **タグ canonical 化の境界がアーキテクチャ上存在しない**
ことだった。

1. **表示は `Tag.tag` を verbatim 出力** — `ImageRepository._format_tags()` は
   `", ".join(tag.tag for ...)` で tagdb 変換を一切かけない。DB の値がそのまま画面に出る。
2. **保存経路ごとに正規化レベルがバラバラ**:
   - `.txt` 取込 (`ExistingFileReader._read_annotations`): `clean_format()` のみ (`_`→空白、
     小文字化なし・tagdb 解決なし)
   - `_persist_existing_annotations` (`db_manager.py`): `tag` は raw 保存、clean_format は
     `tag_id` キャッシュキーにしか使わない
   - OpenAI Batch JSONL 取込 (`batch_import_service`): `tag.strip()` のみ
   - AI annotation 保存 (`_save_tags`): 正規化なし (`tag=tag_string` verbatim)
   - GUI 手動追加 (`batch_tag_add_widget`): `clean_format()` + `.lower()` + `.strip()`
3. **alias→preferred (推奨タグ) 関係は format (サイト) ごとに異なる**。あるタグが
   danbooru では別タグの alias でも e621 では preferred 扱い、というように「どの canonical に
   解決するか」自体が format 依存。よって**取込時に 1 format の preferred を焼き込むのは不可**
   (後で別 format 学習時に食い違う)。
4. tagdb には既に `convert_tags(repo, tags, format_name)` という canonical 化一括 API がある
   (`clean_format` + `resolve_preferred=True`) が、LoRAIro は未使用。さらに既存の
   `search_tags` 呼び出しは全て `resolve_preferred=False`。
5. `convert_tags` の完全一致 lookup は **case-sensitive** (`normalize_search_keyword` は
   lower しない) ため、`Grey hair` が danbooru の `grey hair` にマッチせず変換漏れする。

## Decision

正規化 (整形・語の同定・preferred 解決) の責任を **genai-tag-db-tools に集約**する。
LoRAIro 側に正規化ロジックを散らさない。

### 改訂 (2026-06-16): 解決タイミングを「表示時」から「保存時」へ

初版は alias→preferred を「format 依存だから保存時に確定させず、表示/export 時に都度
`convert_tags` で解決する」とした。しかし表示時の per-tag `convert_tags` は **画像1枚の
詳細表示ごとに タグ数 × リポジトリ数 の DB ラウンドトリップ** を発生させ、Windows ネイティブの
実 tag_db で詳細表示が許容外に遅くなった (キャッシュでも初表示コストは消えない。初版が
Negative リスクに挙げた「GUI 表示時の `convert_tags` がコスト増」が顕在化)。

そこで **基準 format (danbooru) の canonical を保存時に焼き込み、表示/export は verbatim**
とする方針へ改訂する。複数 format 学習で別 format が必要な場合は export 時に
danbooru→target を変換する (基準は danbooru)。「元タグ (raw) の保持に実用上の意味は薄い」
というプロダクト判断に基づく。

### データの扱い

| 局面 | `Tag.tag` / 出力値 | 処理 |
|---|---|---|
| **保存 (非手動)** | danbooru canonical (preferred) | `clean_format` 後に `search_tags_bulk(danbooru, resolve_preferred=True)` で焼き込み。preferred tag_id も保存 |
| **保存 (手動編集)** | `clean_format` 整形文字列 | `is_edited_manually=True` はユーザー表記を尊重し canonical 化しない |
| **GUI 詳細表示** | 保存済み値 (verbatim) | 変換しない (表示コストゼロ) |
| **学習 export** | target format の canonical | `convert_tags(target)` + `type=meta` 除外。danbooru は near no-op |
| **管理メタタグ** | DB / 表示には残す | export 時のみ `type=meta` を除外 |

### 原則

- **非手動タグの alias→preferred は保存時に danbooru で確定させる** (表示/export を verbatim 化)。
- **手動編集タグ (`is_edited_manually=True`) は canonical 化しない** — ユーザー表記を保持する。
- **canonical 解決は1画像=1回の bulk lookup** — per-tag 呼び出しを禁止 (遅延の元凶)。
- **変換失敗タグ (tagdb 未登録) は整形 raw のまま保持** — 勝手に削除しない (Issue の要件)。
- **基準 format は danbooru** — 別 format が必要な export 時にのみ danbooru→target を変換。

## 実装 (フェーズ分割)

### Phase 1 (#769 中核)
- **genai-tag-db-tools**: `convert_tags` の lookup を case-insensitive 化
  (`Grey hair`→`grey hair` 同定)。`type=meta` 除外サポート。
- **LoRAIro**: 全保存経路で `Tag.tag = clean_format` 済みに統一
  (`_save_tags` / `batch_import_service` / `_persist_existing_annotations` / `register_prompt_tags`)。
- **LoRAIro**: 既存 DB の `Tag.tag` を `clean_format` で一括整形する修復スクリプト
  (preferred は焼かない)。

### Phase 2 (初版 → 改訂で撤回)
- 初版: GUI 詳細表示で表示時に `convert_tags(danbooru)` を適用 (キャッシュ付き)。
- **改訂で撤回**: 表示時変換は実 DB で許容外に遅いため削除し、表示は verbatim へ戻す。
  代わりに保存境界 (`_save_tags`) で danbooru canonical を焼き込む (1画像=1 bulk lookup)。
  既存 DB は修復スクリプトを danbooru 解決対応に拡張して再実行する。

### Phase 3
- **LoRAIro**: 学習 export の target format 出し分け + `type=meta` 除外 (現状維持)。

## Consequences

### Positive
- `Tag.tag` の意味が「danbooru canonical (手動編集は整形済み)」に一本化され明文化される。
- 正規化ロジックが genai-tag-db-tools に集約され、LoRAIro 側の散発呼び出しが消える。
- **表示/export が verbatim になり、詳細表示の per-tag DB ラウンドトリップが消滅** (本改訂の主目的)。
- canonical 解決コストは保存時 (バッチ処理) に1回だけ集約され、interactive path から外れる。
- 管理メタタグを削除せず export からのみ除外でき、追跡性と学習品質を両立。

### Negative / リスク
- 元タグ (raw) は保持しない。別 format 学習時は danbooru→target 変換となり、
  raw→target と完全一致しないケースがあり得る (基準 danbooru のプロダクト判断で許容)。
- 既存 DB の修復スクリプトは破壊的更新なので backup / dry-run を要する。
- 保存時に danbooru canonical を焼くため、保存経路は外部 tag_db に依存する
  (取得失敗時は `clean_format` のみへ graceful degradation)。

## Related

- Issue: NEXTAltair/LoRAIro#769
- 関連 Issue: NEXTAltair/genai-tag-db-tools#2 (refinement recommendation 仕様)
- ADR 0065 (Tag/Caption soft reject) — `rejected_at` による採否境界