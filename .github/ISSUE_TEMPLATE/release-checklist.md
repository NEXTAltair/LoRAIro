---
name: リリース前チェックリスト
about: リリース毎の手動 pre-release 検証 Issue を起票する
title: "[Release vX.Y.Z] Pre-release Checklist"
labels: documentation
assignees: ''
---

<!--
本テンプレートは docs/release-checklist.md の写しです。
原本(docs/release-checklist.md)を更新した際は、本テンプレートも同期してください。
実行タイミングや失敗時の対応といった運用ルールは原本を参照してください。
-->

- バージョン: vX.Y.Z
- リリース PR: #___

## 前提:自動テスト(Tier 1〜3)の完了

- [ ] 本体テスト `uv run pytest` がすべて成功することを確認します。
- [ ] ローカルパッケージのテスト `make test-all` がすべて成功することを確認します。
- [ ] Tier 1 Smoke、Tier 2 Real API、Tier 3 CLI E2E がすべて成功することを確認します。

## A. GUI 起動と主要画面の確認

- [ ] アプリを起動し、`MainWindow` が正常に表示されることを確認します。
- [ ] 5 段階初期化のログがすべて INFO レベルで完了し、異常な ERROR や WARNING が出ていないことを確認します。
- [ ] サムネイルを選択した際、詳細・タグ編集・検索フィルタの各ウィジェットが正常に機能することを確認します。

## B. 単発アノテーションの動作確認(機能別)

- [ ] Tagger:`wd-vit-tagger-v3` で 1 画像を処理し、タグが GUI に表示されることを確認します。
- [ ] Captioner:`BLIPLargeCaptioning` で 1 画像を処理し、キャプションが表示されることを確認します。
- [ ] Scorer:`cafe_aesthetic` で 1 画像を処理し、スコアが表示されることを確認します。

## C. WebAPI の動作確認(プロバイダ別)

- [ ] Gemini:`gemini/gemini-flash-lite-latest` で 1 画像を処理し、出力を確認します。
- [ ] OpenAI:`openai/gpt-4o-mini` で 1 画像を処理し、出力を確認します。
- [ ] Anthropic:`anthropic/claude-haiku-4-5` で 1 画像を処理し、出力を確認します。
- [ ] OpenRouter:`openrouter/anthropic/claude-haiku-4.5` で 1 画像を処理し、出力を確認します。

## D. DB マイグレーションの確認

- [ ] 直前リリースで作成したプロジェクト DB を本リリースで開き、起動エラーが起きないことを確認します。
- [ ] `alembic upgrade head` がエラーなく完了することを確認します。
- [ ] 既存データがこれまでどおり読み込めることを確認します。

## E. CLI 主要コマンドの確認

- [ ] `lorairo-cli status` が終了コード 0 で完了し、表示崩れがないことを確認します。
- [ ] `lorairo-cli project create <name>` および `lorairo-cli project list` が正常に動作することを確認します。
- [ ] `lorairo-cli images register <dir> --project <name>` が正常に動作することを確認します。
- [ ] `lorairo-cli models list` および `lorairo-cli models list --type webapi` が正常に動作することを確認します。
- [ ] `lorairo-cli annotate run --project <name> --model <m>` が正常に動作することを確認します。
- [ ] `lorairo-cli export create --project <name> --output <dir> --tags <tag>` が正常に動作することを確認します(エクスポート時はフィルタ指定が必須です。詳細は ADR 0019 を参照してください)。

## F. プラットフォーム別の動作確認

- [ ] Linux コンテナ:GUI のオフスクリーン実行および CLI が正常に動作することを確認します。
- [ ] Windows(`cp932` 環境):#254 および #263 で対応したコンソール表示が崩れないことを確認します。
- [ ] WSL:パス解決が正常に行われることを確認します。

## G. 設定ファイル変更の確認

- [ ] `config/lorairo.toml` を新規環境(サンプル状態)からコピーし、アプリが正常に起動することを確認します。
- [ ] API キー未設定の状態でも、縮退モード(degraded mode)として GUI が起動することを確認します。

---

詳細な手順と運用ルールは [docs/release-checklist.md](../../docs/release-checklist.md) を参照してください。
失敗した項目がある場合は、`release-blocker` ラベル付きの Issue を起票し、リリースを延期してください。
