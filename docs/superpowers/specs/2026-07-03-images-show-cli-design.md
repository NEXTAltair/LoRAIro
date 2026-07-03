# エージェント向けタグ確認 CLI (`images show`) 設計仕様

- **日付**: 2026-07-03
- **前提**: `docs/superpowers/specs/2026-06-08-agent-tag-edit-cli-design.md`（`tags add/remove/replace`, `images search`）の後続
- **ステータス**: Approved

## 概要

エージェントが「画像のタグがおかしいので直す」を CLI 経由で行うには、判断材料として
「その画像に今ついているタグ・キャプション・レーティング」を読む手段が要る。書き込み側
（`tags add/remove/replace`）は既存で足りているが、読み取り側に欠落があった
（`images search` は `image_id` / `file_path` のみ返し、アノテーション内容を返さない）。

タグの良し悪しを判定するロジックは LoRAIro には組み込まない。判定はエージェント側が担い、
CLI は「読む」「書く」の実行だけを担う、という既存の責務分離方針をそのまま踏襲する。

## スコープ

- 追加: `lorairo-cli images show`（read-only）
- 変更なし: `tags add/remove/replace`（既存のまま流用）
- スコープ外: タグの自動判定・提案ロジック、AIモデル名の解決表示（`model_id` の名前引きはしない）

## コマンド

```bash
lorairo-cli images show --project <name> --image-ids 42
lorairo-cli images show --project <name> --image-ids 42,57,103 --include-rejected
lorairo-cli --json images show --project <name> --image-ids 42
```

### オプション

| オプション | 必須 | 説明 |
|---|---|---|
| `--project` / `-p` | ○ | プロジェクト名 |
| `--image-ids` | ○ | カンマ区切り image_id。最大 500 件（`tags.py` の `MAX_IMAGE_IDS` / `_parse_image_ids` を再利用） |
| `--include-rejected` | - | soft-rejected 済みタグ/キャプションも含める（既定 `False`） |

read-only（`side_effects: db_read` のみ）。`--apply` / dry-run の概念はない。

## 実装方式

- `src/lorairo/cli/commands/images.py` に `show` サブコマンドを追加
- 存在しない image_id は `tags.py::_validate_image_ids_exist` と同じパターンで
  事前に全件チェックし `ImageNotFoundError` を送出（全件確認してから処理、の既存方針を踏襲）
- 各 image_id について `ImageRepository.get_image_annotations(image_id, include_rejected=...)`
  を**そのまま呼び出す**（ロジック変更なし）。GUI 詳細パネルが使っているものと同一メソッド
- 返り値の `tags` / `captions` / `scores` / `score_labels` / `ratings` / `quality_summary`
  辞書をほぼそのまま JSONL item として出力する
- モデル名解決はしない。`tags[].model_id` は生の ID のまま返す。エージェントが必要なら
  `models list` と突き合わせる（ORM の eager-load 構造を変えるのは今回のスコープに対して過剰）

## Pydantic スキーマ（introspection 登録）

```python
class ImagesShowInput(BaseModel):
    project: str
    image_ids: str  # CSV, max 500
    include_rejected: bool = False

class ImagesShowItem(BaseModel):
    image_id: int
    tags: list[dict]
    captions: list[dict]
    scores: list[dict]
    score_labels: list[dict]
    ratings: list[dict]
    quality_summary: dict

class ImagesShowResult(BaseModel):
    target_images: int
```

`CliErrorResponse` は既存パターンを流用（存在しない image_id → `NOT_FOUND`、
空/不正な `--image-ids` → `INVALID_INPUT`、500件超 → `INVALID_INPUT`）。

## JSONL 出力例

```jsonl
{"kind":"item","image_id":42,"tags":[{"id":1,"tag":"1girl","tag_id":10,"model_id":3,"existing":true,"is_edited_manually":false,"confidence_score":null,"rejected_at":null,"created_at":"...","updated_at":"..."}],"captions":[],"scores":[],"score_labels":[],"ratings":[],"quality_summary":{}}
{"kind":"result","ok":true,"target_images":1}
```

## 典型的なエージェントワークフロー

```bash
# 1. 対象画像のパスと現行タグを確認
lorairo-cli images search --project main_dataset --query '{"image_ids":[42]}' --json
lorairo-cli images show   --project main_dataset --image-ids 42 --json

# 2. (エージェントが画像本体を見てタグの過不足を判断)

# 3. dry-run で提案を確認
lorairo-cli tags remove --project main_dataset --image-ids 42 --tags "bad_tag" --json
lorairo-cli tags add    --project main_dataset --image-ids 42 --tags "correct_tag" --json

# 4. 承認後に apply
lorairo-cli tags remove --project main_dataset --image-ids 42 --tags "bad_tag" --apply --json
lorairo-cli tags add    --project main_dataset --image-ids 42 --tags "correct_tag" --apply --json
```

## テスト方針

- unit: `images show` の入力バリデーション（CliRunner） — 存在しない image_id、空/不正 CSV、500件超
- unit: `--include-rejected` あり/なしで soft-rejected 行の有無が切り替わること
- unit: JSONL 出力フォーマット（`kind:"item"` が `get_image_annotations()` の戻り値と一致すること）
- 既存の `get_image_annotations()` 自体には変更を加えないため、Repository 層の新規テストは不要

## ドキュメント更新

- `scripts/generate_cli_docs.py` を再実行し `docs/cli.md` の Command Reference に
  `images show` を追記
