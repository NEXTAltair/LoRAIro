---
type: ADR
title: エクスポート前タグ編集の2層オーバーレイ契約 — DB編集層と出力オーバーレイ層の分離
status: Proposed
timestamp: 2026-06-27
tags: [export, tag-overlay, staging, qt-free-service, dataset-export, trigger-word]
---
# ADR 0080: エクスポート前タグ編集の2層オーバーレイ契約 — DB編集層と出力オーバーレイ層の分離

- **関連 Issue**: #932 (エクスポート前タグ編集パネル UX 設計), #942 (実装 Epic), #943 (本 ADR), #944 (overlay 適用ロジック), #945 (タグ集計サービス), #946 (trigger 語彙サービス)
- **関連 ADR**: 0065 (タグ/キャプション soft-reject), 0068 (タグ正規化の tagdb 委譲), 0055 (Workspace エクスポート対象の staging 統一), 0072 (Workspace ステージ選択ソース)

## Context

エクスポート直前に staging 集合のタグを整理する編集パネルを実装する (#932 で UX 確定、#942 で実装エポック化)。同じ画像群を別 trigger / 別タグ選択で複数の LoRA に出し分けたいので、整形を DB へ永続化すると破綻する。

タグ編集には性質の異なる2種類が混在する:

| 層 | 性質 | 操作 | 永続性 |
|---|---|---|---|
| **DB編集層** | アノテーション是正 | soft-reject / 復活 / 手動追加 / rating·score | DB へ永続・全エクスポートに影響 |
| **出力オーバーレイ層** | この書き出し1回の整形 | trigger 追加 / 出力除外 / 置換 | DB 不変・今回出力のみ |

DB編集層は既存資産で賄える (`SelectedImageDetailsWidget` の soft-reject = ADR 0065)。本 ADR が定義するのは **出力オーバーレイ層の契約 (S0)** で、#944 / #945 / #946 の実装はこの契約に対して書かれる。

`DatasetExportService` の現状のタグ出力は `_resolve_export_tags`（soft-reject 済みを除いた採用タグの和） → join → `_convert_tags_for_export`（`genai_tag_db_tools.convert_tags` による format 依存の alias→preferred 解決 + `type=meta` 除外、ADR 0068 Phase 3）の順。オーバーレイはこの convert を挟んで適用される。

## Decision

### 1. 出力オーバーレイのデータ構造

オーバーレイは per-image の純データ。3 操作のみを持つ。

```python
@dataclass
class ExportTagOverlay:
    add: list[str]            # trigger word 等。リテラル（convert を通さない）
    exclude: set[str]         # 出力から除外するタグ名
    replace: dict[str, str]   # X -> Y の 1:1 置換（削除は exclude が担うため replace の to は非空）
```

`replace` は 1:1。タグの横断削除は `exclude` が担い、1:N 展開（X → {Y, Z}）は本契約に含めない（必要が出たら別 ADR）。

### 2. per-image 適用パイプライン

`apply_overlay` は convert を内側に挟む順序で適用する。中核の判断は **trigger だけ convert をバイパスし、exclude/replace は convert 前のタグ（= パネルに見えている DB タグ）に効かせる** こと。

```
db_tags（convert 前・採用タグ）
  │
  ├─ 1. replace 適用（X→Y）
  ├─ 2. exclude 除去
  ├─ 3. convert（alias→preferred 解決 + meta 除外）   ← reader=None なら素通し
  ├─ 4. add を先頭に literal prepend（convert バイパス）
  └─ 5. 順序保持 dedup（先頭=trigger 側を優先して残す）
→ 出力タグ列
```

確定する不変条件:

- **exclude タグは出力に出ない**: `exclude` を `replace` の **後** に効かせる。`X→Y` の置換で生えた `Y` も exclude 指定なら消える（「Y を除外したのに replace で復活」を防ぐ）。
- **trigger はリテラル**: 漢字を含む trigger を convert に通さない。`add` は convert 後に literal prepend する。
- **dedup は先頭優先**: trigger と本文タグ、replace 産と既存タグが重複したら、順序を保ったまま初出（先頭の trigger 側）を残す。
- **オーバーレイ未指定なら従来挙動を完全維持**: `add`/`exclude`/`replace` がすべて空なら既存エクスポートと bit 単位で一致。
- **reader=None graceful degradation**: 外部 tag_db 不在で convert がスキップされても、replace/exclude/trigger は db_tags に対して機能する。

矛盾入力 (`X` を exclude かつ `X→Y` を replace) は replace 優先で `Y` が残る（同じ元タグへの rename と除外の同時指定はレアな矛盾なので contract で弾かない）。

### 3. スコープ付きルールと合成

オーバーレイは staging 集合の任意のサブセットに適用できる。「全画像に trigger A、加えてこの数枚にだけ trigger B」を表現する。

```python
@dataclass
class ScopedOverlayRule:
    image_ids: set[int] | None   # None = 全 staging 画像
    overlay: ExportTagOverlay

@dataclass
class ExportOverlayPlan:
    rules: list[ScopedOverlayRule]
    def effective_for(self, image_id: int) -> ExportTagOverlay: ...
```

`effective_for(image_id)` は、その画像を含む全ルールを **積み上げ合成** して per-image の実効 overlay を返す:

- **add**: ルール定義順に連結（global → subset）。最終 dedup で重複は畳まれる。
- **exclude**: 全該当ルールの和集合。
- **replace**: マージ。キー衝突は **後勝ち**（後定義 / より狭いスコープのルールが優先）。

**減算は持たない**。「全部のうち数枚だけ trigger を外す」は、外したいのではなく **付けたい集合を直接 scope に書く**ことで表現する（任意の `image_ids` 集合を取れるため「全部マイナス数枚」= 付けたい集合）。`exclude` は convert 前段で効くため prepend 後の trigger には届かず、trigger の打ち消しには使えない（不変条件「trigger 優先」と表裏）。

> この積み上げ合成は暫定確定であり、運用して使い心地が悪ければ別 ADR で見直す。

### 4. `DatasetExportService` フックと適用範囲

- フック点は `export_dataset_txt_format` / `export_dataset_json_format` のタグ文字列構築（`_resolve_export_tags` → convert）。convert の前後に overlay の各段を差し込む。
- 画像ごとに `plan.effective_for(image_id)` で実効 overlay を作り適用する。`plan` を渡さなければ従来挙動。
- overlay 適用も合成 (`effective_for`) も **Qt-free サービス**に閉じる。`ExportTagOverlay` / `apply_overlay` / `ExportOverlayPlan` は GUI にもサブセット選択状態にも依存しない純データ・純関数。

### 5. tagd 境界

trigger word の **語彙登録・補完** (#946, `genai-tag-db-tools` USER_TAGS) は本契約の外。`apply_overlay` / `effective_for` / `StagingTagAggregationService` は trigger 語彙 DB を参照しない。語彙サービスは UI の補完候補供給にのみ使われ、確定した trigger 文字列は `ExportTagOverlay.add` のリテラルとして渡る。これにより #944 / #945 は genai-tag-db-tools の overlay DB 再設計 (#940) と独立して実装できる。

## Consequences

**Positive**

- 出力整形を DB へ永続化しないため、同一画像群を複数 LoRA へ別 trigger で出し分けられる。
- 中核ロジック (`apply_overlay` / `effective_for`) が Qt-free 純関数なので単体テストが容易で、GUI / tagd / サブセット状態から分離される。
- overlay 未指定で既存エクスポートのリグレッションが起きない（明示的不変条件）。

**Negative / Trade-off**

- サブセット指定 (B) を採ったため、per-image 合成リゾルバ (`effective_for`) という1段が増える。全体一律 (A) より契約が複雑。
- exclude が trigger に届かない非対称性があり、「全部のうち数枚だけ trigger を外す」は scope を絞って表現する必要がある（直感に反する場合があるが、減算概念を持ち込まないトレードオフ）。
- 合成規則（後勝ち / 積み上げ）は運用前の暫定確定。使い心地次第で別 ADR で改訂し得る。

## Related

- ADR 0065 — soft-reject（DB編集層が再利用する是正状態）
- ADR 0068 — タグ正規化の tagdb 委譲（convert の意味と適用タイミング）
- ADR 0055 / 0072 — staging 集合がエクスポート対象・編集対象である根拠
