# LoRAIro ユーザーガイド

GitHub Pages: https://nextaltair.github.io/LoRAIro/

これは利用者向けのユーザーガイドであり、`docs/` にある開発者向け ADR や仕様書とは分離しています。Astro + Starlight により、静的ページ、検索機能、および日本語 / 英語 / 繁体字中国語 / 簡体字中国語のナビゲーションを提供します。既存の GitHub Pages URL を維持しつつ、従来の Sphinx `gh-pages` ブランチではなく GitHub Actions でデプロイします。

## Windows / Linux でのビルド

CI では Node.js 24 を使用します。Python、GPU、プロジェクト DB、API キー、Kit のインストールは不要です。

```text
cd site
npm ci
npm test
npm run build
npm run preview
```

執筆時は `npm run dev` を使用してください。検索インデックスは本番ビルド時に生成されます。アップロード対象は `site/dist` のみです。PR では両 OS で検証を行いますが公開はしません。`main` ブランチでは両 OS のビルド通過後に公開されます。

## 日本語原本の翻訳ワークフロー

1. `src/content/docs/ja/<page>.html` の完全な HTML ドキュメントを編集し、手順が現在のアプリコードと一致していることを確認します。HTML がガイドの正規ソースです。`h2`, `p`, `ol`, `table`, `thead`, `tbody`, `th`, `td`, `pre`/`code` などのセマンティック要素を使い、Markdown や MDX のガイド本文は追加しないでください。
2. 変更した HTML ドキュメントを、同じファイル名で `en`、`zh-tw`、`zh-cn` へ翻訳するようコーディングエージェントに依頼します。
3. 警告、数値、リンク、CLI 引数を日本語原本と照合してレビューします。`pre`/`code` の内容はそのまま維持してください。
   ガイドの表示言語と、GUI の翻訳やエクスポートされるタグの言語を混同しないでください。存在しない UI コントロールを創作してはいけません。
4. 各翻訳が完了したあとでのみ、ソースリビジョンを記録します。

   ```text
   node scripts/record-translations.mjs en export.html
   node scripts/record-translations.mjs zh-tw export.html
   node scripts/record-translations.mjs zh-cn export.html
   ```

5. テストとビルドを実行し、翻訳ファイルと `translations.json` をまとめてコミットします。

`check-translations.mjs` は、正規化したソースの SHA-256 ハッシュ、ページ集合、HTML の `pre`/`code` 例、および未翻訳コピーを比較します。`check-guide-html.mjs` は正規 HTML ドキュメント、セマンティックなテーブル、操作例プレースホルダーを検証します。Starlight の日本語フォールバックに頼らず、翻訳の欠落や陳腐化があれば失敗させます。ハッシュはソースリビジョンの追跡を示すものであり、翻訳の意味的な品質を保証するものではありません。エージェントによるレビューが引き続き必要です。鮮度エラーを消すためだけに記録コマンドを実行しないでください。CI から有料翻訳サービスは一切呼び出しません。

`check-build.mjs` は、`/LoRAIro/` ベース配下の全 40 ロケールページとローカル生成リンクを検証します。意図的に章を追加・削除する場合は、4 言語すべての更新とあわせて期待ページ数も更新してください。

## 公開方式の移行

PR の準備と承認が完了したら、このリポジトリの Pages ビルド種別を GitHub Actions に設定します。`main` からのデプロイ成功と 4 言語すべてのトップページの HTTP 応答を確認してから、古い `gh-pages` ブランチを廃止してください。過去のコミットは Git 履歴から復元できます。

## 操作例の画像プレースホルダー

`projects`、`search`、`annotation`、`editing`、`export` の各章には、該当する GUI 手順のすぐ横にローカライズされた `figure.guide-placeholder` を配置しています。スクリーンショット撮影前はリンク切れ画像のリクエストを発生させないよう、意図的に `img` 要素も `src` も含めていません。デフォルトの枠は 1280×720 (16:9) で、記事幅に収まります。

プレースホルダーを実画像へ置き換えるときは、`figure` と `figcaption` を残したまま内側の `div` を `img` に差し替え、ローカライズした代替テキストを設定してください。記述例は次のとおりです。

```html
<figure class="guide-placeholder" style="--guide-placeholder-ratio: 4 / 3">
  <img src="/LoRAIro/images/export-settings.png" alt="Export format and resolution settings">
  <figcaption>Export settings (1280×960)</figcaption>
</figure>
```

デフォルトの 16:9 が適さない場合は、`--guide-placeholder-ratio` に画像の意図した比率 (例: `4 / 3`) を指定します。実画像は `site/public/` 配下に追加して `/LoRAIro/` URL で参照し、トリミングされないよう `max-width: 100%` と `height: auto` を指定してください。4 言語すべての HTML ドキュメントとキャプション・代替テキストを更新し、翻訳をレビューしたうえで翻訳ハッシュを記録します。

参考資料: [Starlight i18n](https://starlight.astro.build/guides/i18n/), [Astro GitHub Pages deployment](https://docs.astro.build/en/guides/deploy/github/)
