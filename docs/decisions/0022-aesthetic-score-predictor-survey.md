# ADR 0022: Aesthetic Score Predictor Model Survey

- **日付**: 2025-02-06
- **ステータス**: Accepted
- **ソース**: [美的評価モデル比較：Aesthetic ShadowとVisionRewardの選択 (NEXTAltair, 2025-02-06)](https://nextaltair.hatenablog.com/entry/2025/02/06/Aesthetic_Score_Predictor)
- **関連 ADR**: [0004 Annotator-Lib Architecture](0004-annotator-lib-architecture.md)
- **関連実装**:
  - `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/pipeline_scorers.py` (Aesthetic Shadow / Cafe Aesthetic)
  - `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/scorer_clip.py` (ImprovedAesthetic / WaifuAesthetic)

## Context

LoRAIro の品質スコアリング機能において、生成画像の美的評価を数値化するモデルを選定する必要があった。
Stable Diffusion 等で生成した画像のデータセット品質管理・生成パラメータ最適化に活用するため、
複数の Aesthetic Score Predictor モデルを比較調査した。

評価対象は以下の観点:

- **対応領域**: アニメ特化 / 実写対応 / 汎用
- **処理速度**: バッチサイズ・スループット
- **入力解像度**: モデル固有の制約
- **出力スケール**: スコアの範囲・正規化方式
- **入手性**: 公式配布の継続性、ライセンス
- **計算コスト**: ローカル実行可能性

## Decision

`image-annotator-lib` で **以下 4 モデルを採用**し、用途に応じて使い分ける:

| モデル | 採用クラス | フレームワーク | 用途 |
|--------|----------|-------------|------|
| Aesthetic Shadow v1 | `AestheticShadow` (`pipeline_scorers.py`) | HF Pipeline | アニメ画像の高精度評価 |
| Aesthetic Shadow v2 | `AestheticShadow` (`pipeline_scorers.py`) | HF Pipeline | アニメ画像の 4 段階評価 |
| Cafe Aesthetic | `CafePredictor` (`pipeline_scorers.py`) | HF Pipeline | 実写・アニメ両対応、バッチ高速処理 |
| ImprovedAesthetic | `ImprovedAesthetic` (`scorer_clip.py`) | CLIP+MLP | 汎用・軽量 |
| WaifuAesthetic | `WaifuAesthetic` (`scorer_clip.py`) | CLIP+MLP | アニメ特化 (CLIP ベース) |

**保留中候補**: VisionReward (THUDM)・ImageReward (THUDM) は将来導入候補とし、
本 ADR では未採用とする。

## Rationale

### モデル比較表

| モデル | 開発元 | 専門領域 | パラメータ | 入力解像度 | 出力 | 速度 (A100) | ライセンス |
|--------|-------|---------|----------|----------|------|------------|----------|
| Aesthetic Shadow v1 | shadowlilac | アニメ | 約11億 (1.1B) | 1024×1024 | hq / lq の 2 値 | ~200ms/枚 | 利用可能 |
| Aesthetic Shadow v2 | shadowlilac | アニメ | 約11億 | 1024×1024 | very aesthetic / aesthetic / displeasing / very displeasing の 4 段階 | ~120ms/枚 | **2024 年末に公式リポジトリでの公開停止、ミラー使用** |
| Cafe Aesthetic | cafeai | 実写・アニメ両対応 | 約8600万 (BEiT-base) | 384×384 | 公式は `aesthetic` / `not_aesthetic` の 2 クラス分類。記事/実装側で `math.floor(aesthetic_score * 10)` で 0-10 化 | ~150ms/枚 (BS=32) | 利用可能 |
| CLIP+MLP | C. Schuhmann | 汎用 | 約5000万 | 記載なし | 1-10 | 記載なし | 利用可能 |
| Waifu-Diffusion Aesthetic | WD チーム | アニメ | 非公表 | 224×224 | 0-10 | - | 手動 DL 必須・サポート対象外 |
| **VisionReward** | THUDM (清華大学) | 多次元評価・動画対応 | 非公表 | 記載なし | チェックリスト形式 | - | Apache-2.0 |
| **ImageReward** | THUDM (清華大学) | テキスト-画像生成評価 | 非公表 | 224×224 | 標準正規分布 (μ=0.167, σ=1.033) | - | 利用可能 |

### スコア解釈の差異 (重要)

各モデルで **評価スケールが異なる** ため、スコア間の直接比較は不可:

- **Aesthetic Shadow v1**: hq / lq の独立した確率値 (合計 1.0 にならない)
- **Aesthetic Shadow v2**: 4 カテゴリの独立した確率値
- **Cafe Aesthetic**: `floor(raw_score × 10)` で 0-10 の整数化
- **CLIP+MLP / WaifuAesthetic**: 1-10 の連続値
- **ImageReward**: 標準正規分布に従う実数値 (`μ=0.167, σ=1.033`)
- **VisionReward**: 多次元のチェックリスト評価（コンテンツの豊かさ、細部の現実性、構図、色彩調和など）

LoRAIro の `UnifiedAnnotationResult.scores` フィールドはモデル横断で `dict[str, float]` を保持するが、
**スコア値の意味はモデル固有** であり、品質フィルタ等で複数モデルのスコアを混在させる場合は
モデル別に閾値を設定する必要がある。

### モデル別の採用根拠

#### Aesthetic Shadow v1 / v2 (採用)
- **長所**: アニメ画像で最高精度。v2 は 4 段階評価で粒度高い
- **短所**: v2 は公式配布停止のためミラーリポジトリ依存
- **採用理由**: アニメ画像主体の LoRA 学習データセット品質管理に必須

#### Cafe Aesthetic (採用)
- **長所**: バッチサイズ 32 対応で高スループット、実写・アニメ両対応、低品質線画の自動識別
- **短所**: 384×384 入力に限定
- **採用理由**: 大規模データセットの一次フィルタリングに最適
- **補足 (一次ソース)**: 公式モデルは `microsoft/beit-base-patch16-384` を 3.5K 程度の実写/アニメ画像でファインチューニングした **2 クラス分類器** (`aesthetic` / `not_aesthetic`)。0-10 スケール化は記事/`pipeline_scorers.py` 側の二次処理

#### ImprovedAesthetic / CLIP+MLP (採用)
- **長所**: CLIP エンベディング + MLP の軽量構成、汎用性が高い
- **短所**: モデル自体が古い (1 年以上前)、最新の生成画像傾向に追従しない
- **採用理由**: ベースライン比較用、軽量実行環境向けフォールバック

#### WaifuAesthetic (採用)
- **長所**: CLIP+3 層 NN でアニメ特化
- **短所**: 手動ダウンロード必須、サポート対象外
- **採用理由**: 既存 LoRA データセット作成ワークフローとの互換維持

#### VisionReward (未採用、将来候補)
- **長所**: 多次元評価（コンテンツの豊かさ Rich content / 細部の現実性 Details realistic / 構図のバランス / 色彩の調和）、解釈可能なチェックリスト形式、画像および動画に対応、Apache-2.0
- **短所**: 計算コストが比較的高い
- **未採用理由**: 単一スコアではない多次元評価のため、LoRAIro の `scores: dict[str, float]` への
  マッピング方針が未確定。GUI 表示・フィルタリング UX も再設計が必要
- **補足 (一次ソース)**: アノテーションは画像 48K に対し質問 3M、動画 33K に対し質問 2M。
  Video Preference Test Set で Tau=64.0 / Diff=72.1 を達成し VideoScore を 17.2% 上回る SOTA。
  Multi-objective Preference Optimization (MPO) で複数軸を同時最適化可能

#### ImageReward (未採用、将来候補)
- **長所**: ImageRewardDB (137K+ エキスパート評価) で学習、CLIP より 38.6% / Aesthetic より 39.6% / BLIP より 31.6% 高い精度。
  BLIP + MLP ベース、5 層 MLP による最終的なスコア予測、クロスアテンションによるテキストと画像の特徴融合
- **短所**: テキスト-画像ペアの評価モデルでありプロンプト入力前提
- **未採用理由**: LoRAIro は画像単体評価が主用途で、プロンプトを伴うフローが現状未整備
- **補足 (一次ソース)**: 学習データは [DiffusionDB](https://github.com/poloclub/diffusiondb) のテキストプロンプトと
  対応する生成画像から構築 (137K pairs of expert comparisons)。NeurIPS 2023 採択論文
  (arXiv:2304.05977)。Backbone は ViT-L 画像エンコーダ + Transformer テキスト特徴量をクロスアテンションで統合し、
  MLP head でスカラー報酬を出力

## Consequences

### 良い点

- 5 種類の採用モデルで「アニメ特化 (高精度)」「実写対応」「軽量汎用」の用途を網羅
- `image-annotator-lib` の Pipeline / CLIP 抽象化により、新規スコアラー追加が容易
- スコア意味論を ADR で明文化したため、モデル横断の閾値設定方針が明確化

### 悪い点・制約

- **Aesthetic Shadow v2 はミラー依存**: 公式配布停止のため、ミラーリポジトリの可用性に依存。
  別のミラー消失時に代替手段の確保が課題
- **スコア値の不均一性**: モデル間で出力スケールが異なるため、品質フィルタ実装時には
  モデル別閾値設定が必要 (UI で閾値スライダーを単一にできない)
- **VisionReward / ImageReward 未採用**: 多次元評価・テキスト連動評価のニーズが高まれば
  別途 ADR で導入判断が必要

### 未解決の論点

1. **Aesthetic Shadow v2 ミラー消失時の代替**: 候補モデルのバックアップ戦略
2. **マルチモデル評価の集約方針**: 複数スコアラーの結果を「総合スコア」として集約するロジック
   (現状: 各モデル独立のスコアを `scores: dict[str, float]` に保持)
3. **VisionReward 統合時の `UnifiedAnnotationResult` 拡張**: 多次元評価を保持する `aspects: dict[str, float]`
   フィールド追加の要否 (現時点では `raw_output` 任意辞書で対応可能)

## References

### 元記事
- [元ブログ記事: 美的評価モデル比較 (NEXTAltair, 2025-02-06)](https://nextaltair.hatenablog.com/entry/2025/02/06/Aesthetic_Score_Predictor)

### 採用モデルの一次ソース
- [shadowlilac/aesthetic-shadow (HuggingFace)](https://huggingface.co/shadowlilac/aesthetic-shadow)
- [shadowlilac/aesthetic-shadow-v2 (HuggingFace)](https://huggingface.co/shadowlilac/aesthetic-shadow-v2) — 公式配布停止
- [NeoChen1024/aesthetic-shadow-v2-backup (HuggingFace)](https://huggingface.co/NeoChen1024/aesthetic-shadow-v2-backup) — v2 ミラー
- [cafeai/cafe_aesthetic (HuggingFace)](https://huggingface.co/cafeai/cafe_aesthetic)
- [improved-aesthetic-predictor (LAION)](https://github.com/christophschuhmann/improved-aesthetic-predictor)

### 将来候補モデルの一次ソース
- [THUDM/ImageReward (GitHub)](https://github.com/THUDM/ImageReward)
- [THUDM/ImageRewardDB (HuggingFace Dataset)](https://huggingface.co/datasets/THUDM/ImageRewardDB)
- [ImageReward 論文 (arXiv 2304.05977)](https://arxiv.org/html/2304.05977v4) — NeurIPS 2023
- [THUDM/VisionReward (GitHub)](https://github.com/THUDM/VisionReward)
- [THUDM/VisionReward-Image (HuggingFace)](https://huggingface.co/THUDM/VisionReward-Image)
- [THUDM/VisionReward-Video (HuggingFace)](https://huggingface.co/THUDM/VisionReward-Video)
- [VisionReward 論文 (arXiv 2412.21059)](https://arxiv.org/html/2412.21059v1)

### 検証メモ
本 ADR は元ブログ記事を一次資料とし、2026-04-29 時点で各モデルの公式リポジトリ・論文と
クロスチェック済み。**入力解像度・パラメータ数・精度比較数値は一次ソースで裏取り完了**。
ブログ記事に含まれていた「VisionReward の入力 224×224 固定 / テキスト 35 トークン以下制約」
「CLIP+MLP の入力解像度 可変」は一次ソースで確認できなかったため本 ADR からは除外している。
