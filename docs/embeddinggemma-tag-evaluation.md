---
type: Guide
title: EmbeddingGemma 2 の画像タグ評価
status: Accepted
timestamp: 2026-10-11
tags: [embedding, evaluation, tags]
---

# EmbeddingGemma 2 の画像タグ評価

`scripts/evaluate_embeddinggemma_tags.py` は、既存の LoRAIro プロジェクト DB を対象に、画像の埋め込みから「付与済みタグをどこまで上位に拾えるか」を測る実験用スクリプトである。タグを新規生成するモデルではなく、候補語彙の中からタグを順位付けする能力を評価する。アプリ本体への組み込みやタグの自動追加は行わない。

安全性を保つため、以下の制約のもとで動作する。

- **読み取り専用の DB アクセス**: 既存の `create_project_session_factory(..., read_only=True)` で DB を開く。SQLite の `mode=ro` と `query_only=ON` により、マイグレーションやタグ更新は一切行わない。
- **画像データの保護**: 画像はローカルモデルにのみ渡し、画面表示、サムネイル生成、HTML 出力、画像データの書き出しは行わない。`--prepare-only` 指定時はファイルの存在確認のみを行い、画像をデコードしない。

## 実行手順

### 環境準備と基本実行

リポジトリルートで実行する。worktree で実行する場合は `AGENTS.md` に従い、共有 `.venv` を使用する。出力先には空のディレクトリを指定し、再実行時は別の出力先を使って古い結果と新しい標本の混在を防ぐ。

必要なライブラリバージョンは Sentence Transformers 6.1.0 以上、および EmbeddingGemma 2 に対応した Transformers 5.19.0 以上である。実験用ライブラリだけを専用ディレクトリへ配置し、既存の PyTorch と torchvision を併用する。

以下は Windows の共有環境 `H:/LoRAIro/.venv` を使う手順である。別環境では共有 Python と出力先の絶対パスを適宜置き換える。worktree 内に専用の `.venv` は作成しない。

```powershell
$sharedPython = "H:/LoRAIro/.venv/Scripts/python.exe"
$evalRuntime = "H:/LoRAIro/.agents/artifacts/embeddinggemma-runtime"
uv pip install --python $sharedPython --target $evalRuntime --no-deps -r scripts/embeddinggemma_tag_eval_requirements.txt
$sourceDirectory = (Resolve-Path src).Path
$env:PYTHONPATH = "$evalRuntime;$sourceDirectory;$env:PYTHONPATH"
& $sharedPython scripts/evaluate_embeddinggemma_tags.py --db "H:/LoRAIro/lorairo_data/main_dataset_20250707_001/image_database.db" --output-dir "H:/LoRAIro/.agents/artifacts/embeddinggemma-tags" --limit 64
```

- この requirements ファイルは LoRAIro の共有環境へ追加するオーバーレイ用であり、単独で完結する依存集合ではない。NumPy、Pillow、Hugging Face Hub、PyTorch、torchvision などは共有環境のものを利用する。
- `uv --with` は PyTorch を別バージョンへ解決することがあり、Windows では共有 torchvision との組み合わせで `operator torchvision::nms does not exist` エラーが発生するため、この手順では使用しない。
- Linux 環境では共有 Python を `.venv/bin/python` とし、`PYTHONPATH` の区切り文字を `:` に変更する。

### モデル実行の仕様

初回実行時は Hugging Face からモデルをダウンロードし、2 回目以降はローカルキャッシュを使用する。画像や DB の内容を外部推論 API へ送信することはない。

推論デバイスは CUDA が利用可能なら CUDA、なければ CPU を選ぶ。GPU で BF16 が使える場合は BF16、それ以外は FP32 を使用し、FP16 は使用しない。音声エンコーダーは読み込まず、テキストと画像のみを使用する。

### 評価対象の固定と再利用

モデルを読み込まずに、まず評価対象だけを固定する場合は `--prepare-only` を指定する。

```powershell
& $sharedPython scripts/evaluate_embeddinggemma_tags.py --db "H:/LoRAIro/lorairo_data/main_dataset_20250707_001/image_database.db" --output-dir "H:/LoRAIro/.agents/artifacts/tag-sample" --limit 64 --seed 42 --prepare-only
```

固定した画像 ID と候補語彙を再利用して評価を実行する場合は、`--manifest` でマニフェストファイルを指定する。

```powershell
& $sharedPython scripts/evaluate_embeddinggemma_tags.py --manifest "H:/LoRAIro/.agents/artifacts/tag-sample/manifest.json" --output-dir "H:/LoRAIro/.agents/artifacts/tag-run" --vision-tokens 560 --dimensions 768 512 256
```

`--revision` にモデルのコミットを指定すると、モデルバージョンも固定できる。実際に解決されたコミットとライブラリのバージョンは `summary.json` に記録される。

## 評価対象と候補タグ

### 主なオプション

- `--reference all`(既定): 拒否されていない付与済みタグを参照する。未確認の自動タグも含まれる。
- `--reference manual`: `is_edited_manually=True` のタグを持つ画像を抽出し、そのタグだけを参照する。
- `--reference reviewed`: `reviewed_at` が設定されている画像の採用タグを参照する。
- `--reference existing`: 元ファイル由来のタグを参照する。生成プロンプト由来の可能性もあり、手動正解とは限らない。
- `--candidate-tags tags.json`: JSON の文字列配列、または `.txt` の 1 行 1 タグ形式を候補語彙として使用する。
- `--exclude-tag trigger_name`: トリガーワードなどを候補と参照ラベルの両方から除外する。複数指定できる。

### 候補構築とプロンプト比較の仕組み

候補を指定しない場合は、標本の参照タグ・拒否タグに加え、人数、髪色、目の色、髪の長さ、ポーズ、構図の対照候補を使用する。未知のタグを自由生成する評価ではない。同一画像・同一タグのモデル由来による重複行は除き、空白とアンダースコアの違いをそろえる。標本は固定シードによる画像単位の抽出であり、欠損ファイルは件数を記録したうえで可能なら別の対象で補う。

既定では生タグ(`raw`)と英語説明文(`natural`)を比較する。テキストには公式の分類用接頭辞、画像には空の接頭辞を指定する。既定の 768 次元と 256 次元は同じ推論結果から生成し、切り詰めた後に L2 正規化して比較する。

独自の英語説明や日本語訳を試す場合は、`--prompts raw custom --tag-texts descriptions.json` を指定する。`descriptions.json` は `{"black_hair": "黒髪", ...}` の形式で記述し、**全候補の説明を含める必要がある**。これは、候補の一部だけを訳して比較条件が崩れるのを防ぐためである。限定した候補ファイルと組み合わせると作成しやすい。

## 出力と読み方

### 出力ファイル一覧

| ファイル | 内容 |
| --- | --- |
| `manifest.json` | DB パス、シード、画像 ID、画像パス、参照・手動・拒否タグ、候補語彙。画像データは含まない |
| `summary.json` | 各条件と頻度ベースラインの集計結果、実行時間、実行環境 |
| `report.md` | 回収率と属性群ごとの一致率をまとめた表(画像は含まない) |
| `rankings.csv` | 各画像の上位候補と類似度、参照タグ・拒否タグとの対応 |
| `tag_ranks.csv` | 参照タグごとの順位。候補外のタグは順位・スコアが空欄になる |
| `attribute_groups.csv` | 髪色など、対照群の候補が参照に 1 つだけある場合の順位とスコア差 |
| `embeddings.npz` | 元の画像・テキスト埋め込み、候補と説明文。画像の画素データは含まない |

### 評価指標の解釈

- **`observed_recall@k`**: 参照タグのうち上位 k 件で拾えた割合である。画像単位の平均(macro)とタグ数で重み付けした値(micro)を算出する。候補外の参照タグも分母に残し、候補カバー率もあわせて表示する。
- **`observed_agreement@k`**: 取得候補と DB タグが一致した割合である。未付与タグの正誤は未知であるため、視覚的な適合率や誤検出率とは解釈しない。類似度もタグの存在確率を表すものではない。
- **サブセット別集計と頻度ベースライン**: 手動タグ、確認済み画像、未確認画像に分けて集計する。該当データや拒否タグの比較対象がない場合は、画像数 0、指標 `null` と表示する。頻度ベースラインは対象画像自身のタグを頻度計算から除外しており、頻出タグを並べるだけで得られる結果と画像モデルの結果を比較するための基準となる。
- **`accepted_vs_rejected_win_rate`**: 採用タグの類似度が `incorrect` 拒否タグより高い割合であり、同点は 0.5 とする。採用と拒否が同じ文字列で衝突したラベルは比較から除外し、`not_needed` と `replaced` は比較対象にしない。ただし、キャプションへの移動も `incorrect` を使用する(ADR 0087)ため、採用キャプションと一致する文字列を除いても、視覚的に存在しないことの正解とは限らない。
- **`reference_match_rate`(対照群)**: 参照に 1 つだけ含まれる候補が群内で 1 位になる割合である。複数の髪色などが参照にある画像は、その群の評価から除外する。未付与の候補が実際に写っている可能性は残るため、DB ラベルとの一致を測る補助指標として読む。

### 評価の進め方

まずは手動タグや確認済みデータを使い、人数、髪色、目の色など各属性群の順位を確認する。細部を拾う能力は、`--vision-tokens 280` / `560` / `1120` を同じ `manifest.json` に対して実行することで比較できる。なお、DB タグ自体の正確さを検証するには、ユーザーが別途確認した正解ラベルが必要である。

## 検証

```powershell
uv run --no-sync pytest tests/unit/scripts/test_embeddinggemma_tag_evaluation.py --no-cov
uv run --no-sync ruff check scripts/evaluate_embeddinggemma_tags.py tests/unit/scripts/test_embeddinggemma_tag_evaluation.py
```

単体テストは固定ベクトルと一時 DB を用いる。画像ではないダミーファイルで `--prepare-only` が動作すること、および実行前後で DB のバイト列が変化しないことも確認する。モデルダウンロードや実画像は不要である。

### 仕様の参照

- [Google モデルカード](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)
- [Google マルチモーダル実行ガイド](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers)
