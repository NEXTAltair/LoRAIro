---
type: Guide
title: 在 Windows 安裝
description: 從原始碼建立 Windows 環境，並啟動圖形介面與命令列。
sidebar:
  order: 2
---

## 需求

- Git、uv、Python 3.13；可透過 uv 安裝 Python。
- 足夠儲存模型與圖片的可用空間。
- 若使用標準 GPU 推論環境，需要相容的 NVIDIA GPU 與驅動程式。

本流程從原始碼安裝。標準 PyTorch 來源使用 CUDA 13.2 版本；請確認目前環境的 GPU 與驅動程式是否相容。改用 CPU 版或其他 CUDA 版，需要修改相依套件設定與 lockfile，不是只改啟動參數。

## 首次設定

在 PowerShell 執行。路徑含空格時請加上引號。

```powershell
git clone https://github.com/NEXTAltair/LoRAIro.git
cd LoRAIro
git submodule update --init --recursive
uv python install 3.13
uv sync --python 3.13
uv run --no-sync lorairo
```

安裝相依套件需要網路連線與時間。應用程式執行中，請勿用 `uv sync` 更新環境。

## 之後的啟動方式

從儲存庫目錄執行。

```powershell
uv run --no-sync lorairo
uv run --no-sync lorairo-cli --help
```

`--no-sync` 可避免啟動時更新相依套件。相依設定變更後，請先停止應用程式與測試，再明確執行 `uv sync`。

## 從復原副本繼續使用

不需要刪除既有圖片、資料庫與設定來重新安裝。請先閱讀[備份與復原](../troubleshooting/)。從其他作業系統複製的 `.venv` 不能直接使用；Windows 與容器內 Linux 的 Python 環境必須分開。

若 `UV_PROJECT_ENVIRONMENT` 仍指向舊容器的 `/workspaces/...`，請改成 Windows 實際使用的共用環境。不要只為避開錯誤而建立舊路徑。

## 同時進行開發

測試、格式化工具的安裝方式及 Dev Container 分工，請參閱[開發環境](../development/)。
