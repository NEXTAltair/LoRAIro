# Civitai コンテンツ分類レベル

出典: https://education.civitai.com/civitais-guide-to-content-levels/

## 分類体系

Civitai のすべてのコンテンツは、映画レーティングに準拠した 5 段階で分類される。

| レベル | 内容 |
| --- | --- |
| PG | Safe For Work。成人向けコンテンツを含まない |
| PG-13 | 露出度の高い服装やセクシーな衣装、暴力、軽度のゴア表現 |
| R | 成人向けのテーマや状況、部分的なヌード、写実的な暴力・死亡描写 |
| X | 写実的なヌード、成人向けの対象物や設定 |
| XXX | 露骨な性的コンテンツ、または不穏で写実的なコンテンツ |

## プロジェクト内での使用箇所

- `images.manual_rating` カラム(手動評価)
- `ratings.normalized_rating` カラム(AI または手動編集モデルによるレーティング結果)
- `_apply_nsfw_filter` での除外判定:`["r", "x", "xxx"]` を NSFW とみなす
- UI の Rating 選択肢:`PG`、`PG-13`、`R`、`X`、`XXX`
