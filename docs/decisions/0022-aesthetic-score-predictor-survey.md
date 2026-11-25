---
type: ADR
title: Aesthetic Score Predictor Model Survey
status: Accepted
timestamp: 2025-02-06
tags: []
---
# ADR 0022: Aesthetic Score Predictor Model Survey

- **ソース**: [美的評価モデル比較:Aesthetic ShadowとVisionRewardの選択 (NEXTAltair, 2025-02-06)](https://nextaltair.hatenablog.com/entry/2025/02/06/Aesthetic_Score_Predictor)
- **関連 ADR**: [0004 Annotator-Lib Architecture](0004-annotator-lib-architecture.md)
- **関連実装**:
  - `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/pipeline_scorers.py`(Aesthetic Shadow / Cafe Aesthetic)
  - `local_packages/image-annotator-lib/src/image_annotator_lib/model_class/scorer_clip.py`(ImprovedAesthetic / WaifuAesthetic)

## Context

LoRAIro の品質スコアリング機能において、生成画像の美的評価を数値化するモデルを選定する必要があった。Stable Diffusion などで生成した画像のデータセット品質管理や生成パラメータ最適化に活用するため、複数の Aesthetic Score Predictor モデルを比較調査した。

評価にあたっては以下の観点を設定した。

- **対応領域**:アニメ特化、実写対応、汎用
- **処理速度**:バッチサイズおよびスループット
- **入力解像度**:モデル固有の制約
- **出力スケール**:スコアの範囲および正規化方式
- **入手性**:公式配布の継続性とライセンス
- **計算コスト**:ローカル環境での実行可能性

## Decision

`image-annotator-lib` では**以下のモデル群を採用**し、用途に応じて使い分ける。

| モデル | 採用クラス | フレームワーク | 用途 |
|--------|----------|-------------|------|
| Aesthetic Shadow v1 | `AestheticShadow` (`pipeline_scorers.py`) | HF Pipeline | アニメ画像の高精度評価 |
| Aesthetic Shadow v2 | `AestheticShadow` (`pipeline_scorers.py`) | HF Pipeline | アニメ画像の 4 段階評価 |
| Cafe Aesthetic | `CafePredictor` (`pipeline_scorers.py`) | HF Pipeline | 実写・アニメ両対応、バッチ高速処理 |
| ImprovedAesthetic | `ImprovedAesthetic` (`scorer_clip.py`) | CLIP+MLP | 汎用・軽量 |
| WaifuAesthetic | `WaifuAesthetic` (`scorer_clip.py`) | CLIP+MLP | アニメ特化(CLIP ベース) |

**保留中の候補**:VisionReward(THUDM)および ImageReward(THUDM)は将来の導入候補とし、本 ADR では未採用とする。

## Rationale

### モデル比較表

| モデル | 開発元 | 専門領域 | パラメータ | 入力解像度 | 出力 | 速度 (A100) | ライセンス |
|--------|-------|---------|----------|----------|------|------------|----------|
| Aesthetic Shadow v1 | shadowlilac | アニメ | 約11億 (1.1B) | 1024×1024 | `hq` / `lq` の 2 値 | ~200ms/枚 | 利用可能 |
| Aesthetic Shadow v2 | shadowlilac | アニメ | 約11億 | 1024×1024 | `very aesthetic` / `aesthetic` / `displeasing` / `very displeasing` の 4 段階 | ~120ms/枚 | **2024 年末に公式リポジトリでの公開停止、ミラー使用** |
| Cafe Aesthetic | cafeai | 実写・アニメ両対応 | 約8600万 (BEiT-base) | 384×384 | 公式は `aesthetic` / `not_aesthetic` の 2 クラス分類。記事・実装側で `math.floor(aesthetic_score * 10)` により 0-10 化 | ~150ms/枚 (BS=32) | 利用可能 |
| CLIP+MLP | C. Schuhmann | 汎用 | 約5000万 | 記載なし | 1-10 | 記載なし | 利用可能 |
| Waifu-Diffusion Aesthetic | WD チーム | アニメ | 非公表 | 224×224 | 0-10 | - | 手動ダウンロード必須・サポート対象外 |
| **VisionReward** | THUDM (清華大学) | 多次元評価・動画対応 | 非公表 | 記載なし | チェックリスト形式 | - | Apache-2.0 |
| **ImageReward** | THUDM (清華大学) | テキスト-画像生成評価 | 非公表 | 224×224 | 標準正規分布 (μ=0.167, σ=1.033) | - | 利用可能 |

### スコア解釈の差異 (重要)

モデルごとに**評価スケールが異なる**ため、異なるモデルのスコア同士を直接比較することはできない。

- **Aesthetic Shadow v1**:`hq` と `lq` の独立した確率値(合計は 1.0 にならない)。
- **Aesthetic Shadow v2**:4 カテゴリの独立した確率値。
- **Cafe Aesthetic**:`floor(raw_score × 10)` による 0-10 の整数値。
- **CLIP+MLP / WaifuAesthetic**:1-10 の連続値。
- **ImageReward**:標準正規分布に従う実数値(`μ=0.167, σ=1.033`)。
- **VisionReward**:多次元のチェックリスト評価(コンテンツの豊かさ、細部の現実性、構図、色彩調和など)。

LoRAIro の `UnifiedAnnotationResult.scores` フィールドはモデル横断で `dict[str, float]` を保持する。しかし**スコア値の意味はモデル固有**であるため、品質フィルタなどで複数モデルのスコアを扱う場合は、モデル別に閾値を設定する必要がある。

### モデル別の採用根拠

#### Aesthetic Shadow v1 / v2 (採用)

- **長所**:アニメ画像で最も高い精度を示す。v2 は 4 段階評価により粒度が高い。
- **短所**:v2 は公式配布が停止しているため、ミラーリポジトリに依存する。
- **採用理由**:アニメ画像を主体とする LoRA 学習データセットの品質管理に必須である。

#### Cafe Aesthetic (採用)

- **長所**:バッチサイズ 32 に対応して高スループットを発揮する。実写・アニメの両方に対応し、低品質な線画も自動識別できる。
- **短所**:入力解像度が 384×384 に限定される。
- **採用理由**:大規模データセットの一次フィルタリングに適している。
- **補足(一次ソース)**:公式モデルは `microsoft/beit-base-patch16-384` を約 3.5K 枚の実写・アニメ画像でファインチューニングした**2 クラス分類器**(`aesthetic` / `not_aesthetic`)である。0-10 スケールへの変換は記事および `pipeline_scorers.py` 側の二次処理である。

#### ImprovedAesthetic / CLIP+MLP (採用)

- **長所**:CLIP エンベディングと MLP を組み合わせた軽量構成で、汎用性が高い。
- **短所**:モデル自体が 1 年以上前と古く、最新の生成画像傾向には追従しにくい。
- **採用理由**:ベースライン比較および軽量実行環境向けのフォールバックとして有用である。

#### WaifuAesthetic (採用)

- **長所**:CLIP と 3 層ニューラルネットワークで構成され、アニメ画像に特化している。
- **短所**:手動ダウンロードが必須であり、公式サポートの対象外である。
- **採用理由**:既存の LoRA データセット作成ワークフローとの互換性を維持するためである。

#### VisionReward (未採用、将来候補)

- **長所**:コンテンツの豊かさ(Rich content)、細部の現実性(Details realistic)、構図のバランス、色彩の調和といった多次元評価を解釈可能なチェックリスト形式で行える。画像と動画の両方に対応し、ライセンスは Apache-2.0 である。
- **短所**:計算コストが比較的高い。
- **未採用理由**:単一スコアではない多次元評価であるため、LoRAIro の `scores: dict[str, float]` へのマッピング方針が未確定である。GUI 表示やフィルタリングの UX も再設計を要する。
- **補足(一次ソース)**:アノテーション規模は画像 48K に対して質問 3M、動画 33K に対して質問 2M である。Video Preference Test Set で Tau=64.0、Diff=72.1 を達成し、VideoScore を 17.2% 上回る SOTA を記録している。また、Multi-objective Preference Optimization(MPO)により複数軸を同時最適化できる。

#### ImageReward (未採用、将来候補)

- **長所**:ImageRewardDB(137K+ 件のエキスパート評価)で学習されており、CLIP より 38.6%、Aesthetic より 39.6%、BLIP より 31.6% 高い精度を示す。BLIP と MLP をベースとし、クロスアテンションによるテキストと画像の特徴融合、および 5 層 MLP によるスコア予測を行う。
- **短所**:テキストと画像のペアを評価するモデルであり、プロンプト入力を前提とする。
- **未採用理由**:LoRAIro は画像単体の評価を主用途としており、プロンプトを伴う評価フローが未整備である。
- **補足(一次ソース)**:学習データは [DiffusionDB](https://github.com/poloclub/diffusiondb) のテキストプロンプトと対応する生成画像から構築されている(137K pairs of expert comparisons)。NeurIPS 2023 採択論文(arXiv:2304.05977)で発表された。バックボーンは ViT-L 画像エンコーダと Transformer テキスト特徴量をクロスアテンションで統合し、MLP ヘッドからスカラー報酬を出力する構成である。

## Consequences

### 良い点

- 5 種類の採用モデルにより、「アニメ特化(高精度)」「実写対応」「軽量汎用」の主要用途を網羅できる。
- `image-annotator-lib` の Pipeline および CLIP 抽象化により、新規スコアラーを追加しやすい。
- 各モデルのスコア意味論を ADR に明文化したことで、モデル横断の閾値設定方針が明確になった。

### 悪い点・制約

- **Aesthetic Shadow v2 のミラー依存**:公式配布が停止しているため、ミラーリポジトリの可用性に依存する。ミラー消失時の代替手段を確保することが課題である。
- **スコア値の不均一性**:モデル間で出力スケールが異なるため、品質フィルタ実装時にはモデル別の閾値設定が必要となる(UI で単一の閾値スライダーに統一できない)。
- **VisionReward および ImageReward の未採用**:多次元評価やテキスト連動評価の需要が高まった場合は、別途 ADR を作成して導入を判断する必要がある。

### 未解決の論点

1. **Aesthetic Shadow v2 ミラー消失時の代替**:候補モデルのバックアップ戦略を検討する必要がある。
2. ~~**マルチモデル評価の集約方針と尺度統一**~~ **(解決済み:#626 / ADR 0029)**
   モデル間でスケールが異なる数値スコアを、手動スライダーと同じ 0.0-10.0 の表示尺度へ統一する方針が確定した。
   - `src/lorairo/domain/score_scaler.py` が各スコアラーの正方向キー(`higher_is_better=True`)を対象に、Animagine 由来しきい値を節点(knot)とした連続・区分線形補間で 0-10 化する。
   - 手動値がある場合は最優先とし、ない場合は各スコアラーの連続 0-10 値の平均を表示スコア(`score_value`)とする。
   - 離散の品質ティアバッジ(ADR 0029 の `compute_quality_summary`)は併存させ、連続表示スコアと役割分担する。
   - ライブラリ側の `ScoreScale`(`range` / `higher_is_better`)メタデータ安定化は `iam-lib#144` で扱う。
3. **VisionReward 統合時の `UnifiedAnnotationResult` 拡張**:多次元評価を保持する `aspects: dict[str, float]` フィールド追加の要否(現時点では任意の `raw_output` 辞書で対応可能である)。

## Related

- [ADR 0029 — Unified Dataset Quality Tier](0029-unified-dataset-quality-tier.md):ティアバッジ(離散)と表示スコア(連続)の役割分担
- [Issue #626](https://github.com/NEXTAltair/LoRAIro/issues/626):AI 数値スコアの表示尺度統一(consumer 側)
- [image-annotator-lib#144](https://github.com/NEXTAltair/image-annotator-lib/issues/144):スコアラー `ScoreScale` メタデータ安定化(provider 側)

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

本 ADR は元ブログ記事を一次資料とし、2026-04-29 時点で各モデルの公式リポジトリおよび論文とクロスチェック済みである。**入力解像度・パラメータ数・精度比較数値は一次ソースで裏取りを完了している。**

なお、元ブログ記事に含まれていた「VisionReward の入力 224×224 固定・テキスト 35 トークン以下制約」および「CLIP+MLP の入力解像度可変」は一次ソースで確認できなかったため、本 ADR からは除外している。
