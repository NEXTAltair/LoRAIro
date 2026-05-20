---
name: リリース前チェックリスト
about: リリース毎の手動 pre-release 検証 Issue を起票する
title: "[Release vX.Y.Z] Pre-release Checklist"
labels: documentation
assignees: ''
---

<!--
本テンプレートは docs/release-checklist.md の写しです。
原本 (docs/release-checklist.md) を更新した際は、本テンプレートも同期してください。
運用ルール (実行タイミング・失敗時の対応) は原本を参照。
-->

- バージョン: vX.Y.Z
- リリース PR: #___

## 前提: 自動テスト (Tier 1〜3) の完走

- [ ] 本体テスト `uv run pytest` 完走
- [ ] local package テスト `make test-all` 完走
- [ ] Tier 1 Smoke / Tier 2 Real API / Tier 3 CLI E2E 完走

## A. GUI 起動・主要画面確認

- [ ] アプリ起動 → MainWindow 表示
- [ ] 5 段階初期化のログが全 INFO レベルで完走 (ERROR/WARNING の異常なし)
- [ ] サムネイル選択 → 各 widget (詳細 / タグ編集 / 検索フィルタ) が機能する

## B. 単発 annotation 動作 (各 capability)

- [ ] Tagger: `wd-vit-tagger-v3` で 1 画像 → tags が GUI に表示される
- [ ] Captioner: `BLIPLargeCaptioning` で 1 画像 → captions 表示
- [ ] Scorer: `cafe_aesthetic` で 1 画像 → scores 表示

## C. WebAPI 動作 (各 provider)

- [ ] Gemini: `gemini/gemini-flash-lite-latest` で 1 画像 → 出力確認
- [ ] OpenAI: `openai/gpt-4o-mini` で 1 画像 → 出力確認
- [ ] Anthropic: `anthropic/claude-haiku-4-5` で 1 画像 → 出力確認
- [ ] OpenRouter: `openrouter/anthropic/claude-haiku-4.5` で 1 画像 → 出力確認

## D. DB マイグレーション

- [ ] 直前リリースで作成された project DB を本リリースで開いて起動エラーなし
- [ ] `alembic upgrade head` がエラーなく完走
- [ ] 既存データが既存通り読める

## E. CLI 主要コマンド

- [ ] `lorairo-cli status` exit 0 / 表示崩れなし
- [ ] `lorairo-cli project create <name>` / `lorairo-cli project list`
- [ ] `lorairo-cli images register <dir> --project <name>`
- [ ] `lorairo-cli models list` / `lorairo-cli models list --type webapi`
- [ ] `lorairo-cli annotate run --project <name> --model <m>`
- [ ] `lorairo-cli export create --project <name> --output <dir> --tags <tag>` (export はフィルタ必須 / ADR 0019)

## F. プラットフォーム別動作

- [ ] Linux container: GUI offscreen / CLI 動作
- [ ] Windows (cp932 環境): #254 / #263 で対応した console 表示が崩れない
- [ ] WSL: パス解決 OK

## G. 設定ファイル変更

- [ ] `config/lorairo.toml` を新規環境 (sample 状態) からコピーしてアプリ起動
- [ ] API キー未設定状態でも GUI 起動はする (degraded mode)

---

詳細手順・運用ルールは [docs/release-checklist.md](../../docs/release-checklist.md) を参照。
失敗項目があれば `release-blocker` ラベル付き Issue を起票し、リリースを延期すること。
