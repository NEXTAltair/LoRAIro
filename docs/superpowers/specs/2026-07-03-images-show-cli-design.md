# エージェント向けタグ確認 CLI(`images show`)設計仕様

- **日付:** 2026-07-03
- **前提:** `docs/superpowers/specs/2026-06-08-agent-tag-edit-cli-design.md`(`tags add/remove/replace`、`images search`)の後続
- **ステータス:** Approved

## 概要

エージェントが CLI 経由で画像のタグを修正するには、判断材料として「その画像に現在付与されているタグ、キャプション、レーティング」を読み取る手段が必要である。書き込み側(`tags add/remove/replace`)は既存コマンドで足りているが、読み取り側が不足していた(`images search` は `image_id` と `file_path` のみを返し、アノテーション内容を返さない)。

タグの良否を判定するロジックは LoRAIro には組み込まない。判定はエージェント側が担い、CLI は「読む」「書く」の実行のみを担うという既存の責務分離方針を踏襲する。

## スコープ

- **追加:** `lorairo-cli images show`(読み取り専用)
- **変更なし:** `tags add/remove/replace`(既存コマンドをそのまま流用)
- **スコープ外:** タグの自動判定・提案ロジック、および AI モデル名の解決表示(`model_id` の名前引きは行わない)

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
| `--image-ids` | ○ | カンマ区切りの `image_id`(最大 500 件。`tags.py` の `MAX_IMAGE_IDS` と `_parse_image_ids` を再利用) |
| `--include-rejected` | - | 論理却下(soft-rejected)済みのタグ・キャプションも含める(既定値 `False`) |

本コマンドは読み取り専用(`side_effects: db_read` のみ)であり、`--apply` や dry-run の概念は持たない。

## 実装方式

- `src/lorairo/cli/commands/images.py` に `show` サブコマンドを追加する。
- 存在しない `image_id` は、`tags.py::_validate_image_ids_exist` と同じパターンで事前に全件確認し、`ImageNotFoundError` を送出する(全件確認してから処理する既存方針を踏襲)。
- 各 `image_id` に対して、GUI 詳細パネルと同一メソッドである `ImageRepository.get_image_annotations(image_id, include_rejected=...)` を**ロジック変更なしでそのまま呼び出す**。
- 戻り値の `tags`、`captions`、`scores`、`score_labels`、`ratings`、`quality_summary` の各辞書を、ほぼそのまま JSONL の `item` として出力する。
- モデル名の解決は行わず、`tags[].model_id` は生の ID のまま返す。エージェントがモデル名を必要とする場合は `models list` と突き合わせる(ORM の eager-load 構造を変更するのは本スコープに対して過剰である)。

## Pydantic スキーマ(イントロスペクション登録)

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

エラー応答には既存の `CliErrorResponse` パターンを流用する(存在しない `image_id` は `NOT_FOUND`、空または不正な `--image-ids` および 500 件超は `INVALID_INPUT`)。

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

- **ユニットテスト:** `CliRunner` を用いた `images show` の入力バリデーション(存在しない `image_id`、空または不正な CSV、500 件超)。
- **ユニットテスト:** `--include-rejected` の有無によって論理却下済み行の出力が切り替わること。
- **ユニットテスト:** JSONL 出力フォーマット(`kind:"item"` が `get_image_annotations()` の戻り値と一致すること)。
- 既存の `get_image_annotations()` 自体には変更を加えないため、リポジトリ層の新規テストは不要とする。

## ドキュメント更新

- `scripts/generate_cli_docs.py` を再実行し、`docs/cli.md` の Command Reference に `images show` を追記する。
