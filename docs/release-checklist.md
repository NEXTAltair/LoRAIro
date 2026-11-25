# リリース前 手動チェックリスト(Tier 4)

このチェックリストは、LoRAIro の 4 段階テスト構成における最終層です。GUI 操作、目視品質、UX、プラットフォーム差異、DB マイグレーションの実データ互換など、自動化が難しい領域をリリース前に開発者が確認します。

## 運用ルール

- **実行タイミング**: タグをプッシュする直前(`git tag vX.Y.Z` の前)に実施します。
- **担当**: リリース PR の作成者が担当します。
- **失敗時の対応**: `release-blocker` ラベル付きの Issue を起票し、リリースを延期します。
- **結果の記録**: 全項目を通過したら、リリース PR の本文に「リリース前チェックリスト全項目 ✓」と記載します。
- **Issue 起票**: リリースごとに `.github/ISSUE_TEMPLATE/release-checklist.md` から「`[Release vX.Y.Z] Pre-release Checklist`」Issue を起票し、本ファイルの写しとして使います。
- **リリースノート**: 手書きの `CHANGELOG.md` は廃止済みです(2026-07-05 に 71 日・895 コミットの乖離により維持不能と判断)。リリース時は Conventional Commits から自動生成します(GitHub Releases の auto-generated notes または `git-cliff`)。破壊的変更と廃止機能の正本(SSoT)は [DEPRECATIONS.md](DEPRECATIONS.md) を参照してください。

## 前提:自動テスト(Tier 1〜3)の完走

本チェックリストは自動テスト(Tier 1〜3)を**補完**する最終関門です。手動チェックを始める前に、以下の自動テストを完走させてください。

- 本体テスト:`uv run pytest`
- ローカルパッケージのテスト:`make test-all`
- Tier 1 Smoke(実機モデル軽量 E2E)、Tier 2 Real API(実 WebAPI)、Tier 3 CLI E2E(実行方法は [testing.md](testing.md) を参照してください)

> モデル ID(例:`openrouter/anthropic/claude-haiku-4.5`)は、チェック実施時点で利用可能な最新版へ読み替えて構いません。

---

## A. GUI 起動・主要画面の確認

- [ ] アプリを起動し、`MainWindow` が正常に表示されること
- [ ] 5 段階初期化のログがすべて INFO レベルで完走し、ERROR や WARNING の異常がないこと
- [ ] サムネイルを選択した際、詳細・タグ編集・検索フィルタの各ウィジェットが正常に機能すること

## B. 単発アノテーションの動作(各機能種別)

- [ ] Tagger:`wd-vit-tagger-v3` で 1 画像を処理し、タグが GUI に表示されること
- [ ] Captioner:`BLIPLargeCaptioning` で 1 画像を処理し、キャプションが表示されること
- [ ] Scorer:`cafe_aesthetic` で 1 画像を処理し、スコアが表示されること

## C. WebAPI の動作(各プロバイダ)

- [ ] Gemini:`gemini/gemini-flash-lite-latest` で 1 画像を処理し、出力を確認できること
- [ ] OpenAI:`openai/gpt-4o-mini` で 1 画像を処理し、出力を確認できること
- [ ] Anthropic:`anthropic/claude-haiku-4-5` で 1 画像を処理し、出力を確認できること
- [ ] OpenRouter:`openrouter/anthropic/claude-haiku-4.5` で 1 画像を処理し、出力を確認できること

## D. DB マイグレーション

- [ ] 直前リリースで作成したプロジェクト DB を本リリースで開き、起動エラーが起きないこと
- [ ] `alembic upgrade head` がエラーなく完走すること
- [ ] 既存データを従来どおり読み込めること

## E. CLI 主要コマンド

- [ ] `lorairo-cli status` が終了コード 0 で表示崩れなく動作すること(成功時は常に exit 0。ADR 0057)
- [ ] `lorairo-cli project create <name>` および `lorairo-cli project list` が動作すること
- [ ] `lorairo-cli images register <dir> --project <name>` が動作すること
- [ ] `lorairo-cli models list` および `lorairo-cli models list --type webapi` が動作すること
- [ ] `lorairo-cli annotate run --project <name> --model <m>` が動作すること
- [ ] `lorairo-cli export create --project <name> --output <dir> --tags <tag>` が動作すること(エクスポートはフィルタ必須。ADR 0019)
- [ ] 異常系の終了コードが仕様どおりであること(不正な引数などの入力・検証エラーは exit 2、その他の失敗は exit 1。ADR 0057)

## E2. CLI JSON モード・イントロスペクション(エージェント駆動)

- [ ] `lorairo-cli --json status` および `--json version` で、標準出力が純粋な JSONL の単一 `result` 行になり、ログ・進捗・装飾が標準エラー出力へ分離されること(ADR 0057、0058、Issue #662)
- [ ] 環境変数 `LORAIRO_CLI_JSON=1` でも同じ JSONL モードに切り替わること
- [ ] `lorairo-cli --json list-commands` が副作用なしで全コマンド(`version`、`status` を含む)を列挙すること(ADR 0059)
- [ ] `lorairo-cli --json describe "annotate run"`(compact)および `--schema json_schema` が、入力・出力・エラーのスキーマを返すこと(ADR 0059)

## F. プラットフォーム別の動作

- [ ] Linux コンテナ:GUI(offscreen)と CLI が動作すること
- [ ] Windows(cp932 環境):#254 および #263 で対応したコンソール表示が文字化けしないこと
- [ ] WSL:パス解決が正常に動作すること

## G. 設定ファイル変更

- [ ] `config/lorairo.toml` を新規環境(sample 状態)からコピーしてアプリを起動できること
- [ ] API キー未設定の状態でも GUI が起動すること(degraded mode)

---

## 関連 Issue

- [#276](https://github.com/NEXTAltair/LoRAIro/issues/276):テスト設計改善(親 Issue)
- [#277](https://github.com/NEXTAltair/LoRAIro/issues/277):Tier 1 Smoke(実機モデル軽量 E2E)
- [#278](https://github.com/NEXTAltair/LoRAIro/issues/278):Tier 2 Real API integration
- [#279](https://github.com/NEXTAltair/LoRAIro/issues/279):Tier 3 CLI End-to-End
- [#254](https://github.com/NEXTAltair/LoRAIro/issues/254) / [#263](https://github.com/NEXTAltair/LoRAIro/issues/263):cp932 文字化け対応(F. プラットフォーム別の根拠)
