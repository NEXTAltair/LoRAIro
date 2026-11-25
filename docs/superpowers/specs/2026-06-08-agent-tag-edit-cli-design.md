# エージェント向けタグ整備 CLI 設計仕様

- **日付:** 2026-06-08
- **対象 Issue:** #695, #697, #698
- **ステータス:** Approved

## 概要

エージェントが「不適切なタグを直す」作業を安全に行えるように、CLI へ以下の 3 機能を追加・整理する。設計の核心は、判断をエージェントが担い、DB 操作の実行を CLI が担う責務分離である。

3 件は独立した PR として順に起票する(#695 → #697 → #698)。

---

## PR 1: Issue #695 — `tags add/remove/replace`

### アーキテクチャ

- 新規ファイルとして `src/lorairo/cli/commands/tags.py` を追加する。
- `AnnotationRepository` に 2 メソッドを追加する。
- `main.py` に `tags` グループを登録する。

### コマンドシグネチャ

```
lorairo-cli tags add     --project <name> --image-ids 1,2,3 --tags "t1,t2"               [--dry-run|--apply] [--json]
lorairo-cli tags remove  --project <name> --image-ids 1,2,3 --tags "bad_tag"             [--dry-run|--apply] [--json]
lorairo-cli tags replace --project <name> --image-ids 1,2,3 --from "変換元" --to "変換先" [--dry-run|--apply] [--json]
```

- デフォルトは dry-run(DB を更新しない)とし、`--apply` を付けた場合のみ書き込む。
- `--image-ids` はカンマ区切りの整数列とする。`--image-id` の複数指定形式は増やさない。
- `is_edited_manually=True` を設定し、既存の `MANUAL_EDIT` 方針に準拠する。

### `AnnotationRepository` 追加メソッド

```python
def remove_tag_from_images_batch(
    self, image_ids: list[int], tag: str, model_id: int | None
) -> tuple[bool, int]:
    """tag を指定画像群から削除。戻り値: (成功フラグ, 削除件数)"""

def replace_tag_for_images_batch(
    self, image_ids: list[int], from_tag: str, to_tag: str, model_id: int | None
) -> tuple[bool, int]:
    """from_tag を to_tag に置換。戻り値: (成功フラグ, 変更件数)"""
```

### `replace` の挙動

| 変換元の有無 | 変換先の有無 | 動作 | ステータス |
|---|---|---|---|
| なし | — | 何もしない | `skipped`(reason: `from_tag_not_found`) |
| あり | なし | 変換元を削除し、変換先を追加する | `changed` |
| あり | あり(既存) | 変換元の削除のみを行う | `changed` |

### バリデーション

- 存在しない `image_id` が含まれる場合は、全件確認の段階で `NOT_FOUND` エラーを返す。
- 存在しないタグの `add` は新規登録とする(`add_tag_to_images_batch` の既存挙動に準拠)。
- 空の `image_ids` または空タグは `INVALID_INPUT` とする。

### JSONL 出力

```jsonl
{"kind":"item","image_id":123,"action":"replace","from":"bad","to":"good","status":"changed"}
{"kind":"item","image_id":456,"action":"replace","from":"bad","to":"good","status":"skipped","reason":"from_tag_not_found"}
{"kind":"result","ok":true,"target_images":2,"changed":1,"skipped":1,"errors":0,"dry_run":true}
```

---

## PR 2: Issue #697 — `images search`

### アーキテクチャ

- `src/lorairo/cli/commands/images.py` に `search` サブコマンドを追加する。
- Pydantic モデルの `ImageSearchQuery` と `SortSpec` を同ファイル内に定義する。
- `ImageFilterCriteria` に `sort_field: str` と `sort_direction: str` を追加する。
- `ImageRepository.get_images_by_filter()` をソート対応させる。

### コマンドシグネチャ

```
lorairo-cli images search --project <name> --query-file search.json [--json]
lorairo-cli images search --project <name> --query -                [--json]  # stdin
```

### 検索スキーマ(Pydantic モデル)

```python
class SortSpec(BaseModel):
    field: Literal["image_id", "file_path"]
    direction: Literal["asc", "desc"] = "asc"

class ImageSearchQuery(BaseModel):
    image_ids: list[int] | None = None
    tags: list[str] | None = None
    excluded_tags: list[str] | None = None
    caption: str | None = None
    manual_rating: str | None = None
    ai_rating: str | None = None
    score_min: float | None = None
    score_max: float | None = None
    only_unrated: bool = False
    missing_model: str | None = None   # litellm_id 文字列
    include_nsfw: bool = False
    limit: int = Field(default=500, le=500, ge=1)
    offset: int = Field(default=0, ge=0)
    sort: list[SortSpec] = [SortSpec(field="image_id", direction="asc")]
```

### `ImageFilterCriteria` への追加フィールド

```python
sort_field: str = "image_id"
sort_direction: str = "asc"
```

`sort` リストの先頭エントリのみを有効とし、多段ソートは将来拡張とする。

### バリデーション

- 無効な JSON やスキーマ不一致は `INVALID_INPUT` とする。
- 任意の SQL は受け付けない。
- `sort.field` が `image_id` または `file_path` 以外の場合は `INVALID_INPUT` とする。
- `sort.direction` が `asc` または `desc` 以外の場合は `INVALID_INPUT` とする。

### JSONL 出力

```jsonl
{"kind":"item","image_id":123,"file_path":"image_dataset/512/xxx.webp"}
{"kind":"item","image_id":456,"file_path":"image_dataset/512/yyy.webp"}
{"kind":"result","ok":true,"count":2,"total":2,"limit":500,"offset":0,"has_more":false}
```

本コマンドは読み取り専用であり、ファイル出力などの副作用を持たない。

---

## PR 3: Issue #698 — `export create` からの検索責務の完全分離

### アーキテクチャ

- `src/lorairo/cli/commands/export.py` を大幅に簡略化する。
- 既存の検索オプションとヘルパー関数を削除する。
- `--image-ids` を必須オプションとして追加する。

### コマンドシグネチャ

```
lorairo-cli export create \
  --project <name> \
  --image-ids 1,2,3 \
  --output /tmp/out \
  --resolution 512
```

- `--format` を削除し、常にタグ txt、キャプション txt、JSON の全形式を出力する。
- `--image-ids` を必須とし、未指定時は `INVALID_INPUT` とする。

### 削除する既存オプション・関数

- **オプション:** `--tags`、`--excluded-tags`、`--caption`、`--manual-rating`、`--ai-rating`、`--include-nsfw`、`--score-min`、`--score-max`、`--format`
- **ヘルパー:** `_build_filter_criteria`、`_criteria_has_effective_filter`、`_validate_rating`、`_validate_score_bounds`

CLI 大改修の運用開始前であるため、後方互換は維持しない。

### バリデーション

- `--image-ids` が未指定の場合は `INVALID_INPUT` とする。
- 存在しない `image_id` が含まれる場合は `NOT_FOUND` とする。

### ドキュメント更新

- `docs/cli.md` に典型ワークフローを 2 ステップ(`images search` → `export create --image-ids`)で記載する。
- `describe "export create"` のサマリーを更新する。

---

## 典型的なエージェントワークフロー

```bash
# 1. 対象画像を検索(stdin 経由でクエリを渡す)
echo '{"tags":["bad_tag"],"include_nsfw":true}' | \
lorairo-cli images search \
  --project main_dataset \
  --query - \
  --json > result.jsonl

# 2. dry-run で確認
lorairo-cli tags replace \
  --project main_dataset \
  --image-ids $(jq -r 'select(.kind=="item")|.image_id' result.jsonl | paste -sd,) \
  --from "bad_tag" --to "good_tag" \
  --dry-run --json

# 3. 承認後に apply
lorairo-cli tags replace \
  --project main_dataset \
  --image-ids 123,456,789 \
  --from "bad_tag" --to "good_tag" \
  --apply --json
```

---

## テスト方針

各 PR で以下のテストを追加する。

- **ユニットテスト:** `AnnotationRepository` の新規メソッド(モック Session を使用)
- **ユニットテスト:** CLI コマンドの入力バリデーション(`CliRunner` を使用)
- **ユニットテスト:** JSONL 出力フォーマットの確認
- **統合テスト:** dry-run 実行時に DB が変更されないことの確認
- **BDD テスト:** エージェント向けワークフローの振る舞い仕様(#695 のみ、検索と置換の組み合わせ)
