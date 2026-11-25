---
type: ADR
title: タグ正規化責任の genai-tag-db-tools への集約
status: "Accepted (Revised: 2026-06-16 — 解決タイミングを表示時から保存時へ変更)"
timestamp: 2026-06-16
deciders: NEXTAltair
tags: []
---
# ADR 0068: タグ正規化責任の genai-tag-db-tools への集約

## Context

LoRAIro GUI の詳細表示に未整形のタグが出力されるケースが報告された(Issue #769、image ID `14443`)。具体的には `_touhou`、`blue_hair_`、`alternate_costume`、`Grey hair`、`Pov hands`、`bad_id`、`bad_pixiv_id`、`__commentary_request`、`_highres` などが該当する。

調査の結果、原因は単一のバグではなく、タグを正規化(canonical 化)する責務境界がアーキテクチャ上に存在しないことだった。

1. **表示層は `Tag.tag` をそのまま出力している**: `ImageRepository._format_tags()` は `", ".join(tag.tag for ...)` として tagdb 変換を一切かけず、DB の値をそのまま画面へ表示している。
2. **保存経路ごとに正規化レベルがばらついている**:
   - `.txt` 取込(`ExistingFileReader._read_annotations`): `clean_format()` のみ(`_` を空白へ変換するが、小文字化や tagdb 解決は行わない)
   - `_persist_existing_annotations`(`db_manager.py`): `tag` は生文字列のまま保存し、`clean_format` は `tag_id` のキャッシュキーにしか使っていない
   - OpenAI Batch JSONL 取込(`batch_import_service`): `tag.strip()` のみ
   - AI アノテーション保存(`_save_tags`): 正規化なし(`tag=tag_string` をそのまま保存)
   - GUI 手動追加(`batch_tag_add_widget`): `clean_format()` + `.lower()` + `.strip()`
3. **エイリアスから推奨タグ(preferred)への解決はフォーマットごとに異なる**: あるタグが danbooru では別タグのエイリアスであっても、e621 では推奨タグ扱いになることがある。どの正規形へ解決するかはフォーマット依存であるため、初版時点では「取込時に 1 つのフォーマットの推奨タグを焼き込むのは不可」と考えていた。
4. **既存の tagdb API が活用されていない**: tagdb にはすでに `convert_tags(repo, tags, format_name)` という一括正規化 API(`clean_format` + `resolve_preferred=True`)が存在するが、LoRAIro では未使用だった。既存の `search_tags` 呼び出しもすべて `resolve_preferred=False` だった。
5. **完全一致検索が大文字・小文字を区別している**: `convert_tags` の完全一致ルックアップは大文字・小文字を区別する(`normalize_search_keyword` が小文字化しない)。そのため、`Grey hair` が danbooru の `grey hair` に一致せず変換漏れが発生する。

## Decision

タグの正規化(表記整形、語の同定、推奨タグ解決)の責任を `genai-tag-db-tools` へ集約する。LoRAIro 側に正規化ロジックを分散させない。

### 改訂(2026-06-16): 解決タイミングを「表示時」から「保存時」へ変更

初版では、エイリアスから推奨タグへの変換はフォーマット依存であるため保存時に確定させず、表示時およびエクスポート時に都度 `convert_tags` で解決する方針とした。

しかし、表示時にタグ単位で `convert_tags` を呼ぶと、画像 1 枚の詳細表示ごとに「タグ数 × リポジトリ数」の DB ラウンドトリップが発生する。Windows ネイティブの実 tag_db 環境では詳細表示が許容できないほど遅くなり、キャッシュを入れても初回表示のコストは消えなかった(初版でリスクとして挙げていた「GUI 表示時の `convert_tags` コスト増」が顕在化した)。

そこで方針を改訂し、基準フォーマット(danbooru)の正規形を保存時に焼き込み、表示およびエクスポートでは保存済みの値をそのまま使うこととする。別フォーマットでの学習が必要な場合は、エクスポート時に danbooru から対象フォーマットへ変換する。「元の生タグを保持する実用上の意味は薄い」というプロダクト判断に基づく決定である。

### データの扱い

| 局面 | `Tag.tag` / 出力値 | 処理 |
|---|---|---|
| **保存(非手動)** | danbooru 正規形(preferred) | `clean_format` 後に `search_tags_bulk(danbooru, resolve_preferred=True)` で焼き込む。推奨 `tag_id` も保存する |
| **保存(手動編集)** | `clean_format` 整形文字列 | `is_edited_manually=True` はユーザー表記を尊重し、正規化しない |
| **GUI 詳細表示** | 保存済み値(そのまま出力) | 変換しない(表示コストゼロ) |
| **学習エクスポート** | 対象フォーマットの正規形 | `convert_tags(target)` と `type=meta` 除外を行う。danbooru 出力時はほぼ変換不要 |
| **管理メタタグ** | DB・表示には残す | エクスポート時のみ `type=meta` を除外する |

### 原則

- **非手動タグの推奨タグ解決は保存時に danbooru 基準で確定させる**: これにより表示とエクスポートでの変換コストをなくす。
- **手動編集タグ(`is_edited_manually=True`)は正規化しない**: ユーザーが入力した表記を保持する。
- **正規化解決は 1 画像につき 1 回の一括検索で行う**: 遅延の原因となるタグ単位の個別呼び出しは禁止する。
- **変換に失敗したタグ(tagdb 未登録)は整形済みの生文字列のまま保持する**: 勝手に削除しない(Issue の要件)。
- **基準フォーマットは danbooru とする**: 別フォーマットが必要なエクスポート時のみ、danbooru から対象フォーマットへ変換する。

## 実装(フェーズ分割)

### Phase 1(#769 中核)

- **`genai-tag-db-tools`**: `convert_tags` のルックアップを大文字・小文字非区別にする(`Grey hair` を `grey hair` として同定する)。あわせて `type=meta` の除外をサポートする。
- **LoRAIro**: 全保存経路(`_save_tags`、`batch_import_service`、`_persist_existing_annotations`、`register_prompt_tags`)で `Tag.tag` を `clean_format` 済みに統一する。
- **LoRAIro**: 既存 DB の `Tag.tag` を `clean_format` で一括整形する修復スクリプトを用意する(この段階では推奨タグは焼き込まない)。

### Phase 2(初版 → 改訂により撤回)

- **初版**: GUI 詳細表示で表示時に `convert_tags(danbooru)` をキャッシュ付きで適用する予定だった。
- **改訂による撤回**: 表示時変換は実 DB で許容外に遅いため削除し、表示をそのまま出力する形へ戻す。代わりに保存境界(`_save_tags`)で danbooru 正規形を焼き込む(1 画像につき 1 回の一括検索)。既存 DB については、修復スクリプトを danbooru 解決対応へ拡張して再実行する。

### Phase 3

- **LoRAIro**: 学習エクスポートにおける対象フォーマット別の出し分けと `type=meta` 除外を維持する。

## Consequences

### 利点

- `Tag.tag` の意味が「danbooru 正規形(手動編集は整形済み)」に一本化され、仕様が明確になる。
- 正規化ロジックが `genai-tag-db-tools` に集約され、LoRAIro 側の散発的な呼び出しがなくなる。
- 表示とエクスポートで保存値をそのまま出力できるようになり、詳細表示時のタグ単位 DB ラウンドトリップが消滅する(本改訂の主目的)。
- 正規化コストが保存時(バッチ処理)の 1 回だけに集約され、対話的な画面操作の経路から切り離される。
- 管理メタタグを削除せずエクスポート時のみ除外できるため、追跡性と学習データの品質を両立できる。

### 代償・リスク

- 元の生タグは保持しない。別フォーマットでの学習時は danbooru 経由の変換になるため、生タグから直接変換した場合と完全一致しないケースがあり得る(danbooru 基準というプロダクト判断で許容する)。
- 既存 DB の修復スクリプトは破壊的な更新を伴うため、バックアップと dry-run が必要である。
- 保存時に danbooru 正規形を焼き込むため、保存経路が外部 tag_db に依存する(取得失敗時は `clean_format` のみへ段階的にフォールバックする)。

## Related

- Issue: NEXTAltair/LoRAIro#769
- 関連 Issue: NEXTAltair/genai-tag-db-tools#2(refinement recommendation 仕様)
- ADR 0065(Tag/Caption soft reject) — `rejected_at` による採否境界
