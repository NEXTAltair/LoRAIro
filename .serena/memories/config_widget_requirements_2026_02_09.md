# Config Widget設計要件 - 全面見直し版 (2026-02-09)

## 現在の状況

### 既存実装
- **ConfigurationWindow** (`src/lorairo/gui/window/configuration_window.py`): モーダルダイアログ
- **SettingsController** (`src/lorairo/gui/controllers/settings_controller.py`): ダイアログ表示制御
- **ConfigurationService** (`src/lorairo/services/configuration_service.py`): 設定の読み書き
- **Qt Designer UI**: `src/lorairo/gui/designer/ConfigurationWindow.ui`

### 現在実装されているUI要素
1. **API KEY** (3項目)
   - OpenAI APIキー
   - Google Vision APIキー
   - Anthropic Claude APIキー

2. **HuggingFace設定** (3項目)
   - ユーザー名
   - リポジトリ名
   - トークン

3. **ディレクトリ設定** (3項目)
   - エクスポート先
   - バッチ結果ディレクトリ
   - データベースディレクトリ

4. **ログ設定** (2項目)
   - ログレベル (ComboBox: DEBUG, INFO, WARNING, ERROR)
   - ログファイルパス

## 必要な追加設定項目

### 1. 画像処理設定 (image_processing)
- `target_resolution` (int): 512, 768, 1024 から選択
- `realesrgan_upscale` (bool): 小さい画像のアップスケール有無
- `upscaler` (str): 使用するアップスケーラー名 (ComboBox)

### 2. 生成設定 (generation)
- `batch_jsonl` (bool): バッチ処理JSONL生成
- `start_batch` (bool): バッチ処理開始
- `single_image` (bool): 画像ごと処理

### 3. オプション設定 (options)
- `generate_meta_clean` (bool): メタデータ生成
- `cleanup_existing_tags` (bool): 既存タグクリーンアップ
- `join_existing_txt` (bool): 生成タグと既存タグの結合

### 4. プロンプト設定 (prompts)
- `additional` (str): 追加プロンプト (TextEdit)

### 5. Qt/GUI設定 (qt)
- `platform` (str): QT_QPA_PLATFORM (windows, xcb, wayland, offscreen等)
- `default_font` (str): デフォルトフォント名
- `font_size` (int): フォントサイズ
- `suppress_warnings` (bool): フォント警告抑制

### 6. アノテーション設定 (annotation) - ConfigurationServiceで対応中
- `default_model` (str): デフォルトアノテーションモデル
- 利用可能なモデルは `get_available_annotation_models()` から取得

## UIコンポーネント設計ガイドライン

### タブ構成（推奨）
```
[基本設定] [高度な設定] [開発者向け]
├─ 基本設定
│  ├─ API設定（API KEY 3個）
│  ├─ HuggingFace設定（3個）
│  └─ ディレクトリ設定（3個）
├─ 高度な設定
│  ├─ 画像処理設定（3個）
│  ├─ 生成設定（3個 - チェックボックス）
│  ├─ オプション設定（3個 - チェックボックス）
│  └─ プロンプト設定（テキストエディット）
└─ 開発者向け
   ├─ ログ設定（2個）
   ├─ Qt/GUI設定（4個）
   └─ アノテーション設定（1個）
```

### ウィジェット種別
- **テキスト入力**: API KEY、ユーザー名、リポジトリ名、フォント名
- **パス選択**: ディレクトリ、ファイルパス（DirectoryPickerWidget、FilePickerWidget使用）
- **数値入力**: font_size、target_resolution
- **チェックボックス**: boolean設定
- **ComboBox**: 選択肢がある項目（ログレベル、platform、upscaler、デフォルトモデル）
- **TextEdit**: 複数行テキスト（プロンプト）
- **スピンボックス**: 数値調整（font_size）

### 既存UIコンポーネント
- `DirectoryPickerWidget`: パス選択UI
- `FilePickerWidget`: ファイル選択UI
- `QLineEdit`: テキスト入力
- `QComboBox`: ドロップダウン
- `QCheckBox`: チェックボックス
- `QSpinBox`: 数値入力
- `QPlainTextEdit`: 複数行テキスト

## 注意点

1. **APIキーマスキング**
   - ConfigurationServiceで自動マスキング（4文字+***+4文字）
   - ログ出力時もマスキング

2. **設定保存**
   - ConfigurationService.save_settings()で自動保存
   - TOML形式で保存

3. **バリデーション**
   - ディレクトリの存在確認
   - APIキーが空でないこと
   - 数値の範囲チェック（font_size, resolution等）

4. **デフォルト値**
   - DEFAULT_CONFIGから読み込み
   - 設定ファイルがない場合は自動作成

5. **アップスケーラーモデル**
   - `get_upscaler_models()`から動的に取得
   - ComboBoxに自動反映

## 全面見直し必須項目

### ❓ 疑問点（ユーザー指摘）

1. **target_resolution**
   - 使用箇所: ImageProcessingService、db_manager
   - 疑問: ユーザーが実行時に選択する設定？それとも初期化時だけ？
   - 推奨: UI化するか、内部設定に変更するか検討必要

2. **upscaler**
   - 使用箇所: ImageProcessingService、db_manager
   - 疑問: ユーザーが選択する必要がある？固定値でよい？
   - 推奨: UI化の必要性を再評価

3. **batch_jsonl, start_batch, single_image**
   - 疑問: これらは何のための設定か？UIでの選択が必要？
   - 推奨: 実装での使用状況確認後、設計決定

4. **generate_meta_clean, cleanup_existing_tags, join_existing_txt**
   - 疑問: これらの設定の実装での使用状況は？
   - 推奨: 使われていなければ削除

### 📊 設定項目の最終分類

**Tier 1: UI必須項目** - ユーザーが実行時に設定・変更する
- ✅ API KEY (3個) - OpenAI, Google Vision, Anthropic
- ✅ デフォルトアノテーションモデル
- ✅ ログレベル
- ✅ プロンプト設定（additional）
- ✅ プロジェクト名（database_project_name）
- ✅ ベースディレクトリ（database_base_dir）
- ✅ エクスポート先ディレクトリ（export_dir）
- ✅ バッチ結果ディレクトリ（batch_results_dir）

**Tier 2: UI検討中** - 優先度低
- ❓ Qt フォント設定（platform, default_font, font_size）
- ❓ Qt警告抑制設定（suppress_warnings）

**Tier 3: 削除対象 or 内部設定**
- ❌ HuggingFace設定全般（削除）
- ❌ target_resolution（固定値化検討）
- ❌ upscaler（固定値化検討）
- ❌ realesrgan_upscale（実装確認後に判断）
- ❌ realesrgan_model（deprecated？）
- ❌ generation設定全般（使用状況確認後）
- ❌ options設定全般（使用状況確認後）
- ✅ upscaler_models（ConfigurationService読み込み、TOML保持）
- ✅ preferred_resolutions（固定リスト、TOML保持）
- ✅ text_extensions（固定リスト、TOML保持）

### 🔍 確認すべき実装ポイント

1. **generation設定の使用**
   - batch_jsonl, start_batch, single_image はどこで使われている？

2. **options設定の使用**
   - generate_meta_clean, cleanup_existing_tags, join_existing_txt はどこで使われている？

3. **image_processing関連**
   - realesrgan_upscale の実装は？
   - realesrgan_model は不要では？

4. **prompts設定**
   - main と additional の違い
   - UIで管理すべき？

### 🎯 見直しの指針

- **ユーザーが実行時に変更する** → UI化必須
- **初期化時だけ設定** → UIオプション or TOML固定
- **使われていない** → 削除検討
- **内部的な固定値** → TOML不要、コード内定義

## 最終確定：ConfigWidget で管理する設定項目

### 8個のUI設定項目（確定）

**グループ1: API設定（3項目）**
1. `api.openai_key` - LineEdit（パスワード入力モード）
2. `api.google_key` - LineEdit（パスワード入力モード）
3. `api.claude_key` - LineEdit（パスワード入力モード）

**グループ2: ディレクトリ設定（4項目）**
4. `directories.database_base_dir` - DirectoryPicker
5. `directories.database_project_name` - LineEdit
6. `directories.export_dir` - DirectoryPicker
7. `directories.batch_results_dir` - DirectoryPicker

**グループ3: ログ設定（1項目）**
8. `log.level` - ComboBox (DEBUG, INFO, WARNING, ERROR)

**グループ4: プロンプト設定（1項目）**
9. `prompts.additional` - PlainTextEdit（複数行）

**グループ5: アノテーション設定（1項目）**
10. `annotation.default_model` - ComboBox（動的取得）

### UIレイアウト案（タブ形式）

```
┌─ 基本設定 ─ 高度な設定 ─┐
│                          │
│ 【基本設定タブ】          │
│ ━━━━━━━━━━━━━━━━━━   │
│ API設定                  │
│  □ OpenAI API Key        │
│  □ Google Vision Key     │
│  □ Anthropic Key        │
│                          │
│ ディレクトリ設定          │
│  □ Database Base Dir     │
│  □ Project Name          │
│  □ Export Dir            │
│  □ Batch Results Dir     │
│                          │
│ ログ設定                 │
│  □ Log Level: [INFO ▼]  │
│                          │
│ 【高度な設定タブ】        │
│ ━━━━━━━━━━━━━━━━━━   │
│ プロンプト設定           │
│  Additional Prompt:      │
│  ┌──────────────────┐   │
│  │ (複数行テキスト)  │   │
│  └──────────────────┘   │
│                          │
│ アノテーション設定        │
│  Default Model: [○○ ▼]  │
│                          │
│ [保存] [キャンセル] [OK]  │
└─────────────────────────┘
```

## 実装タスク

1. ✅ HuggingFace設定削除
2. ✅ target_resolution, upscaler削除判定
3. ⏳ generation/options設定の使用状況確認
4. ⏳ ConfigurationWindow実装 - 最終版（10項目UI化）
5. ⏳ UIバリデーション設計
6. ⏳ テストケース設計
