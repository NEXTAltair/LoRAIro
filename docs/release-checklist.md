# リリース前 手動チェックリスト (Tier 4)

LoRAIro のテスト設計 4 段階構成の最終層。自動化が困難な領域 (GUI 操作、目視品質、UX、
プラットフォーム差異、DB マイグレーションの実データ互換) を、リリース前に開発者が人手で
確認するための手順。

## 運用ルール

- **実行タイミング**: タグ push 前 (`git tag vX.Y.Z` の直前)。
- **担当**: リリース PR の作成者。
- **失敗時**: `release-blocker` ラベル付き Issue を起票し、リリースを延期する。
- **チェック結果の記録**: 全項目を通過したら、リリース PR の description に
  「リリース前チェックリスト全項目 ✓」と記載する。
- **Issue 起票**: リリース毎に `.github/ISSUE_TEMPLATE/release-checklist.md` から
  「[Release vX.Y.Z] Pre-release Checklist」Issue を起票し、本ファイルの写しとして使う。

## 前提: 自動テスト (Tier 1〜3) の完走

本チェックリストは自動テスト Tier 1〜3 を **補完** する最終 gatekeeper。手動チェックに入る前に、
以下の自動テストを完走させておくこと。

- 本体テスト: `uv run pytest`
- local package テスト: `make test-all`
- Tier 1 Smoke (実機モデル軽量 E2E) / Tier 2 Real API (実 WebAPI) / Tier 3 CLI E2E
  — 実行方法は [testing.md](testing.md) を参照。

> モデル ID (例: `openrouter/anthropic/claude-haiku-4.5`) は、チェック実施時点で利用可能な
> 最新版に読み替えてよい。

---

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
- [ ] `lorairo-cli export create --project <name> --output <dir>`

## F. プラットフォーム別動作

- [ ] Linux container: GUI offscreen / CLI 動作
- [ ] Windows (cp932 環境): #254 / #263 で対応した console 表示が崩れない
- [ ] WSL: パス解決 OK

## G. 設定ファイル変更

- [ ] `config/lorairo.toml` を新規環境 (sample 状態) からコピーしてアプリ起動
- [ ] API キー未設定状態でも GUI 起動はする (degraded mode)

---

## 関連 Issue

- [#276](https://github.com/NEXTAltair/LoRAIro/issues/276): テスト設計改善 (umbrella)
- [#277](https://github.com/NEXTAltair/LoRAIro/issues/277): Tier 1 Smoke (実機モデル軽量 E2E)
- [#278](https://github.com/NEXTAltair/LoRAIro/issues/278): Tier 2 Real API integration
- [#279](https://github.com/NEXTAltair/LoRAIro/issues/279): Tier 3 CLI End-to-End
- [#254](https://github.com/NEXTAltair/LoRAIro/issues/254) / [#263](https://github.com/NEXTAltair/LoRAIro/issues/263): cp932 mojibake 対応 (F. プラットフォーム別の根拠)
