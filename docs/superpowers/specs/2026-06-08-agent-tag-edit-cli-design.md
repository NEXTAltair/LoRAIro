# エージェント向けタグ整備 CLI 設計仕様

- **日付**: 2026-06-08
- **対象 Issue**: #695, #697, #698
- **ステータス**: Approved

## 概要

エージェントが「変なタグを直す」作業を安全に行えるよう、CLI に以下3つの機能を追加・整理する。
判断はエージェントが担い、DB 操作の実行は CLI が担うという責務分離が設計の核心。

3件は独立した PR として順に起票する: **#695 → #697 → #698**

---

## PR 1: Issue #695 — `tags add/remove/replace`

### アーキテクチャ

- 新規ファイル: `src/lorairo/cli/commands/tags.py`
- `AnnotationRepository` に2メソッド追加
- `main.py` に `tags` グループを登録

### コマンドシグネチャ

```
lorairo-cli tags add     --project <name> --image-ids 1,2,3 --tags "t1,t2"               [--dry-run|--apply] [--json]
lorairo-cli tags remove  --project <name> --image-ids 1,2,3 --tags "bad_tag"             [--dry-run|--apply] [--json]
lorairo-cli tags replace --project <name> --image-ids 1,2,3 --from "変換元" --to "変換先" [--dry-run|--apply] [--json]
```

- デフォルト: dry-run（DB 非更新）
- `--apply` を付けた場合のみ書き込み
- `--image-ids`: カンマ区切り整数列。`--image-id` 複数指定形式は増やさない
- `is_edited_manually=True` で既存 MANUAL_EDIT 方針に準拠

### AnnotationRepository 追加メソッド

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

### replace の挙動

| 変換元の有無 | 変換先の有無 | 動作 | ステータス |
|---|---|---|---|
| なし | — | 何もしない | `skipped` / reason: `from_tag_not_found` |
| あり | なし | 変換元削除 + 変換先追加 | `changed` |
| あり | あり（既存） | 変換元削除のみ | `changed` |

### バリデーション

- 存在しない image_id → `NOT_FOUND` エラー（全件確認してから処理）
- 存在しないタグの add → 新規登録（add_tag_to_images_batch の既存挙動に準拠）
- 空 image_ids / 空タグ → `INVALID_INPUT`

### JSONL 出力

```jsonl
{"kind":"item","image_id":123,"action":"replace","from":"bad","to":"good","status":"changed"}
{"kind":"item","image_id":456,"action":"replace","from":"bad","to":"good","status":"skipped","reason":"from_tag_not_found"}
{"kind":"result","ok":true,"target_images":2,"changed":1,"skipped":1,"errors":0,"dry_run":true}
```

---

## PR 2: Issue #697 — `images search`

### アーキテクチャ

- `src/lorairo/cli/commands/images.py` に `search` サブコマンド追加
- Pydantic モデル `ImageSearchQuery` / `SortSpec` を同ファイル内に定義
- `ImageFilterCriteria` に `sort_field: str` / `sort_direction: str` を追加
- `ImageRepository.get_images_by_filter()` のソート対応

### コマンドシグネチャ

```
lorairo-cli images search --project <name> --query-file search.json [--json]
lorairo-cli images search --project <name> --query -                [--json]  # stdin
```

### 検索スキーマ (Pydantic モデル)

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

### ImageFilterCriteria への追加フィールド

```python
sort_field: str = "image_id"
sort_direction: str = "asc"
```

`sort` リストの先頭エントリのみ有効（多段ソートは将来拡張）。

### バリデーション

- 無効な JSON / スキーマ不一致 → `INVALID_INPUT`
- 任意 SQL は受け付けない
- `sort.field` が `image_id` / `file_path` 以外 → `INVALID_INPUT`
- `sort.direction` が `asc` / `desc` 以外 → `INVALID_INPUT`

### JSONL 出力

```jsonl
{"kind":"item","image_id":123,"file_path":"image_dataset/512/xxx.webp"}
{"kind":"item","image_id":456,"file_path":"image_dataset/512/yyy.webp"}
{"kind":"result","ok":true,"count":2,"total":2,"limit":500,"offset":0,"has_more":false}
```

read-only。ファイル出力などの副作用なし。

---

## PR 3: Issue #698 — `export create` 検索責務の完全分離

### アーキテクチャ

- `src/lorairo/cli/commands/export.py` を大幅簡略化
- 既存検索オプション・ヘルパー関数を削除
- `--image-ids` を必須オプションとして追加

### コマンドシグネチャ

```
lorairo-cli export create \
  --project <name> \
  --image-ids 1,2,3 \
  --output /tmp/out \
  --resolution 512
```

- `--format` 削除 → 常にタグtxt・キャプションtxt・JSONの全形式を出力
- `--image-ids` 必須（なければ `INVALID_INPUT`）

### 削除する既存オプション・関数

- オプション: `--tags`, `--excluded-tags`, `--caption`, `--manual-rating`, `--ai-rating`, `--include-nsfw`, `--score-min`, `--score-max`, `--format`
- ヘルパー: `_build_filter_criteria`, `_criteria_has_effective_filter`, `_validate_rating`, `_validate_score_bounds`

互換維持なし（CLI 大改修の運用開始前のため）。

### バリデーション

- `--image-ids` なし → `INVALID_INPUT`
- 存在しない image_id → `NOT_FOUND`

### ドキュメント更新

- `docs/cli.md` に典型ワークフローを2ステップで記載:
  `images search → export create --image-ids`
- `describe "export create"` の summary 更新

---

## 典型的なエージェントワークフロー

```bash
# 1. 対象画像を検索（stdin 経由でクエリを渡す）
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

各 PR で以下を追加:
- unit: AnnotationRepository の新メソッド（モック Session）
- unit: CLI コマンドの入力バリデーション（CliRunner）
- unit: JSONL 出力フォーマット確認
- integration: dry-run は DB を変更しないことを確認
- BDD: エージェント向けワークフローの振る舞い仕様（#695 のみ、検索・置換の組み合わせ）
