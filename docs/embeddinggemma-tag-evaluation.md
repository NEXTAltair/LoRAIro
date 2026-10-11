---
type: Guide
title: EmbeddingGemma 2 の画像タグ評価
status: Accepted
timestamp: 2026-10-11
tags: [embedding, evaluation, tags]
---

# EmbeddingGemma 2 の画像タグ評価

`scripts/evaluate_embeddinggemma_tags.py` は、既存の LoRAIro プロジェクト DB を使い、
画像の埋め込みから「付与済みタグをどこまで上位に拾えるか」を測る実験用スクリプト。
タグを生成するモデルではなく、候補語彙の中からタグを順位付けする能力を評価する。
アプリ本体への組み込みやタグの自動追加は行わない。

DB は既存の `create_project_session_factory(..., read_only=True)` で開く。
SQLite の `mode=ro` / `query_only=ON` により、migration・タグ更新を行わない。
画像はローカルモデルにのみ渡し、表示・サムネイル生成・HTML・画像データの出力は行わない。
`--prepare-only` はファイルの存在確認までで、画像をデコードしない。

## 実行

リポジトリルートで実行する。worktree では AGENTS.md に従い、共有 `.venv` を設定する。
Sentence Transformers 6.1.0 以上と、EmbeddingGemma 2 対応の Transformers 5.19.0 以上が必要。
`--with` は実験用の依存を一時環境に追加し、`--no-sync` は既存のアプリ環境の同期を省く。

```powershell
uv run --no-sync --with "sentence-transformers>=6.1.0,<7" --with "transformers>=5.19.0,<6" python scripts/evaluate_embeddinggemma_tags.py --db "H:/LoRAIro/lorairo_data/main_dataset_20250707_001/image_database.db" --output-dir ".agents/artifacts/embeddinggemma-tags" --limit 64
```

初回は Hugging Face からモデルをダウンロードする。以降はローカルキャッシュを使用する。
画像や DB の内容を外部推論 API へ送信しない。モデルの実行は CUDA があれば CUDA、なければ CPU。
GPU で BF16 が使える場合は BF16、それ以外は FP32 を使う。FP16 は使用しない。
音声エンコーダーは読み込まず、テキストと画像のみを使う。

モデルを読み込まず、まず評価対象だけ固定する場合:

```powershell
uv run --no-sync python scripts/evaluate_embeddinggemma_tags.py --db "H:/LoRAIro/lorairo_data/main_dataset_20250707_001/image_database.db" --output-dir ".agents/artifacts/tag-sample" --limit 64 --seed 42 --prepare-only
```

固定した画像 ID・候補語彙を再利用する場合:

```powershell
uv run --no-sync --with "sentence-transformers>=6.1.0,<7" --with "transformers>=5.19.0,<6" python scripts/evaluate_embeddinggemma_tags.py --manifest ".agents/artifacts/tag-sample/manifest.json" --output-dir ".agents/artifacts/tag-run" --vision-tokens 560 --dimensions 768 512 256
```

`--revision` にモデルのコミットを指定すると、モデルも固定できる。実際に解決されたコミットと
ライブラリのバージョンは `summary.json` に記録する。

## 評価対象と候補タグ

- `--reference all`（既定）: 拒否されていない付与済みタグ。未確認の自動タグも含む。
- `--reference manual`: `is_edited_manually=True` のタグがある画像を抽出し、そのタグだけを参照する。
- `--reference reviewed`: `reviewed_at` がある画像の採用タグを参照する。
- `--reference existing`: 元ファイル由来のタグ。生成プロンプト由来の可能性もあり、手動正解とは限らない。
- `--candidate-tags tags.json`: JSON の文字列配列、または `.txt` の一行一タグを候補語彙にする。
- `--exclude-tag trigger_name`: トリガーなどを候補と参照ラベルの両方から外す。複数指定可能。

候補を指定しない場合、標本の参照タグ・拒否タグと、人数・髪色・目の色・髪の長さ・ポーズ・構図の
対照候補を使う。未知のタグを自由生成する評価ではない。同一画像・同一タグはモデル由来の
重複行を除き、空白と underscore の違いをそろえる。標本は固定 seed による画像単位の抽出。
欠損ファイルは件数を記録し、可能なら別の対象で補う。

既定では生タグ（`raw`）と英語説明文（`natural`）を比較する。
テキストには公式の分類用 prefix、画像には空の prefix を指定する。
既定の 768 / 256 次元は同じ推論結果から作り、切り詰めた後に L2 正規化して比較する。

独自の英語説明や日本語訳を試す場合、`--prompts raw custom --tag-texts descriptions.json` を使う。
`descriptions.json` は `{"black_hair": "黒髪", ...}` という形式で、**全候補の説明が必要**。
候補の一部だけを訳して比較条件が変わるのを防ぐ。限定した候補ファイルと組み合わせると作りやすい。

## 出力と読み方

| ファイル | 内容 |
| --- | --- |
| `manifest.json` | DB・seed・画像 ID・パス・参照/手動/拒否タグ・候補語彙。画像データは含まない |
| `summary.json` | 各条件と頻度ベースラインの集計、実行時間、実行環境 |
| `report.md` | 回収率と属性群ごとの一致率をまとめた、画像を含まない表 |
| `rankings.csv` | 各画像の上位候補と類似度、参照タグ・拒否タグとの対応 |
| `tag_ranks.csv` | 参照タグごとの順位。候補外のタグは順位・スコアが空欄 |
| `attribute_groups.csv` | 髪色など、対照群の候補が参照に一つある場合の順位とスコア差 |
| `embeddings.npz` | 元の画像・テキスト埋め込み、候補と説明文。画像の画素は含まない |

`observed_recall@k` は、参照タグのうち上位 k 件で拾えた割合。画像平均（macro）と
タグ数で重み付けした値（micro）を出す。候補外の参照タグも分母に残し、候補カバー率も表示する。
`observed_agreement@k` は、取得候補と DB タグが一致した割合。未付与タグの正誤は未知なので、
これを視覚的な適合率・誤検出率と解釈しない。類似度もタグ存在確率ではない。

手動タグ・確認済み画像・未確認画像の集計を分ける。該当データや拒否タグの比較がない場合は、
画像数 0 / 指標 `null` を表示する。頻度ベースラインは対象画像自身のタグを頻度計算から外す。
頻出タグを並べるだけでも得られる結果と、画像モデルの結果を比較するための基準。

`accepted_vs_rejected_win_rate` は、採用タグの類似度が `incorrect` 拒否タグより高い割合。
同点は 0.5。採用と拒否が同じ文字列で衝突したラベルは拒否比較から外す。
`not_needed` / `replaced` は比較対象にしない。ただしキャプションへの移動も `incorrect` を使う
（ADR 0087）ため、採用キャプションと一致する文字列を除外しても、視覚的不存在の正解とは限らない。

対照群の `reference_match_rate` は、参照に一つだけある候補が群内一位になる割合。
複数の髪色などが参照にある画像はその群の評価から外す。未付与の候補が実際に写っている可能性は
残るため、DB ラベルとの一致を測る補助指標として読む。

まずは手動・確認済みデータで、人数・髪色・目の色など各群の順位を確認する。
細部を拾う力は `--vision-tokens 280` / `560` / `1120` を同じ manifest で比較できる。
DB タグ自体の正確さを検証するには、ユーザーが別途確認したラベルが必要。

## 検証

```powershell
uv run --no-sync pytest tests/unit/scripts/test_embeddinggemma_tag_evaluation.py --no-cov
uv run --no-sync ruff check scripts/evaluate_embeddinggemma_tags.py tests/unit/scripts/test_embeddinggemma_tag_evaluation.py
```

単体テストは固定ベクトルと一時 DB を使う。画像ではないダミーファイルで `--prepare-only` が
動作し、DB バイト列が変化しないことも確認する。モデルダウンロードや実画像は不要。

仕様の参照:
[Google モデルカード](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)、
[Google マルチモーダル実行ガイド](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers)。
