---
type: Contract
title: Configuration Window 仕様書
status: Accepted
timestamp: 2026-07-05
tags: [configuration, settings-ui]
depends_on: [pyside6]
---
# Configuration Window 仕様書

## 1. 概要

本ドキュメントは、設定画面 (`ConfigurationWindow`) の仕様を定義する。
実装: `src/lorairo/gui/window/configuration_window.py` (`QDialog` 派生)。
呼び出し元: `src/lorairo/gui/controllers/settings_controller.py`。

UI は **全て Python コードで構築する (Qt Designer 不使用)**。
`_build_ui()` が「基本設定」「詳細設定」の 2 タブ (`QTabWidget`) と
`QDialogButtonBox` (OK / Cancel) を組み立てる。

> 注: `src/lorairo/gui/designer/ConfigurationWindow.ui` とその生成物は旧世代の残骸で、
> どこからも import されていない (orphan)。本仕様の対象外。

## 2. 責務

- **表示:** 初期化時 (`__init__` → `_populate_from_config()`) に `ConfigurationService` から
  現在値を取得して各ウィジェットに反映する。
- **収集・保存:** OK ボタン押下時 (`_on_accepted`) に `_collect_settings()` で全フィールドを
  一括収集し、`ConfigurationService.update_setting(section, key, value)` をまとめて呼んだ後、
  `save_settings()` (引数なし、既定パスへ保存) を実行する。
  **フィールド編集ごとのリアルタイム反映は行わない。** 「名前を付けて保存」UI は無い
  (`save_settings(target_path)` はサービス層 API としては存在するが GUI からは使わない)。

## 3. 構成要素

### 基本設定タブ

| 要素 | ウィジェット | 備考 |
|---|---|---|
| API キー (OpenAI / Claude / Google / OpenRouter) | `lineEditOpenAiKey` / `lineEditClaudeKey` / `lineEditGoogleKey` / `lineEditOpenRouterKey` | マスク入力 (`EchoMode.Password`)。保存済み/未設定のステータスラベル付き。`focus_api_key_field()` で特定 provider 欄へ誘導・ハイライト (Issue #755、`stage_model_picker_dialog` から利用) |
| プロジェクト名 | `lineEditProjectName` | |
| ディレクトリ | `dirPickerDatabaseDir` / `dirPickerExportDir` / `dirPickerBatchResults` | |
| ログレベル | `comboBoxLogLevel` | ログ設定はレベル選択のみ (ログファイルパス設定 UI は無い) |

### 詳細設定タブ

| 要素 | ウィジェット | 備考 |
|---|---|---|
| アップスケーラー選択 | `comboBoxUpscaler` | 候補は `ConfigurationService.get_available_upscaler_names()`、既定は `get_default_upscaler_name()` |
| モデル経路優先 | `comboBoxRoutePreference` | WebAPI / ローカルの経路優先設定 (Issue #249) |
| WebAPI 追加プロンプト | `textEditPrompt` (`QPlainTextEdit`) | アノテーション実行時の追加プロンプト |

## 4. 依存関係

- `ConfigurationService`: 設定値の取得・更新・保存 (`update_setting(section, key, value)` /
  `save_settings()` / `get_upscaler_models()` 系)。

## 5. 関連ドキュメント

- 設定サービスの仕様: [configuration_service.md](../application/configuration_service.md)
