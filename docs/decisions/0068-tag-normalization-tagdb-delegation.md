# 0068. タグ正規化責任の genai-tag-db-tools への集約

- Status: Accepted
- Date: 2026-06-16
- Deciders: NEXTAltair

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
LoRAIro は「保存は整形のみ」「表示/export は target format を指定して都度解決」を tagdb API
経由で行う。LoRAIro 側に正規化ロジックを散らさない。

### データの扱い

| 局面 | `Tag.tag` / 出力値 | 処理 |
|---|---|---|
| **保存** | `clean_format` 整形文字列のみ (preferred 未解決) | 全取込経路で統一。tag_id は同定できれば保存 |
| **GUI 詳細表示** | 基準 format (danbooru) の canonical | 表示時に `convert_tags` で preferred 解決 (キャッシュ付き) |
| **学習 export** | target format の canonical | `convert_tags(target)` + `type=meta` 除外 |
| **管理メタタグ** | DB / 表示には残す | export 時のみ `type=meta` を除外 |

### 原則

- **alias→preferred 解決は保存時に確定させない** (format 依存のため出力時に回す)。
- **変換失敗タグ (tagdb 未登録) は整形 raw のまま保持** — 勝手に削除しない (Issue の要件)。
- **format は固定しない** — 使う時 (表示/export) に指定。表示は基準 format (danbooru) 1 つで可。

## 実装 (フェーズ分割)

### Phase 1 (#769 中核)
- **genai-tag-db-tools**: `convert_tags` の lookup を case-insensitive 化
  (`Grey hair`→`grey hair` 同定)。`type=meta` 除外サポート。
- **LoRAIro**: 全保存経路で `Tag.tag = clean_format` 済みに統一
  (`_save_tags` / `batch_import_service` / `_persist_existing_annotations` / `register_prompt_tags`)。
- **LoRAIro**: 既存 DB の `Tag.tag` を `clean_format` で一括整形する修復スクリプト
  (preferred は焼かない)。

### Phase 2
- **LoRAIro**: GUI 詳細表示 (`SelectedImageDetailsWidget` / `AnnotationDataDisplayWidget`) で
  表示時に `convert_tags(danbooru)` を適用 (キャッシュ付き)。

### Phase 3
- **LoRAIro**: 学習 export の target format 出し分け + `type=meta` 除外。

## Consequences

### Positive
- `Tag.tag` の意味が「整形済み文字列 (preferred 未解決)」に一本化され明文化される。
- 正規化ロジックが genai-tag-db-tools に集約され、LoRAIro 側の散発呼び出しが消える。
- format 依存の alias/preferred 解決を出力時に回すことで、複数 format 学習に対応できる。
- 管理メタタグを削除せず export からのみ除外でき、追跡性と学習品質を両立。

### Negative / リスク
- 2 リポジトリ (LoRAIro + genai-tag-db-tools) にまたがる。submodule pin 更新が必要。
- GUI 表示時の `convert_tags` がコスト増 → キャッシュで緩和。
- 既存 DB の修復スクリプトは破壊的更新なので backup / dry-run を要する。

## Related

- Issue: NEXTAltair/LoRAIro#769
- 関連 Issue: NEXTAltair/genai-tag-db-tools#2 (refinement recommendation 仕様)
- ADR 0065 (Tag/Caption soft reject) — `rejected_at` による採否境界
