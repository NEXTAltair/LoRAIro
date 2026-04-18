# Civitai コンテンツ分類レベル

出典: https://education.civitai.com/civitais-guide-to-content-levels/

## 分類体系

Civitai のすべてのコンテンツは映画レーティングに準拠した5段階で分類される。

| レベル | 内容 |
|--------|------|
| PG     | Safe For Work。成人向けコンテンツなし |
| PG-13  | 露出度の高い服装・セクシーな衣装、暴力、軽度のゴア |
| R      | 成人向けテーマ・状況、部分的なヌード、グラフィックな暴力・死亡描写 |
| X      | グラフィックなヌード、成人向けオブジェクト・設定 |
| XXX    | 露骨な性的コンテンツ、または不穏なグラフィックコンテンツ |

## プロジェクト内での使用箇所

- `images.manual_rating` カラム（手動評価）
- `ratings.normalized_rating` カラム（AI/手動編集モデルによるレーティング結果）
- `_apply_nsfw_filter` での除外判定: `["r", "x", "xxx"]` を NSFW とみなす
- UI の Rating 選択肢: `PG / PG-13 / R / X / XXX`
