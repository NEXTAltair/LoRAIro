---
type: Guide
title: 開發環境與無介面測試
description: 區分 Windows 執行、容器開發與共用 Python 環境。
sidebar:
  order: 10
---

## Windows 與容器的分工

在 Dev Container 編輯程式碼，在 Windows 執行圖形介面。容器不顯示 GUI，測試使用 Qt offscreen。Windows 與 Linux 不共用同一份 `.venv` 實體；各作業系統內的 main 與 worktree 共用該系統專用環境。

## 安裝開發相依套件

在 main 共用 checkout 執行，需要 Python、Git 與 uv。

```powershell
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

Linux 若沒有 `python`，請使用 `python3`。此操作會更新共用環境，請在其他應用程式、測試與代理程式未使用它時執行。Kit 的安裝及設定另外管理。

## 一般開發命令

```powershell
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py test-all --dry-run
```

`test` 測試 LoRAIro 本體；`test-all` 依序以各自獨立的測試程序執行三個套件。BDD 繼續使用 pytest-bdd。`lint` 為唯讀檢查；`format` 使用 Ruff 自動格式化及修正。一般工作不會自動同步相依套件。

`test-runtime-local` 執行真實 GPU 模型；`test-runtime-webapi` 呼叫可能實際計費的 API。兩者都需明確執行，不包含在一般 `test-all` 中。

## worktree

不要在工作用 worktree 建立專用 `.venv`。共用命令透過 Git 找到 main 環境，並使用目標 worktree 的原始碼。若設定了 `UV_PROJECT_ENVIRONMENT`，必須與該環境 main 共用 `.venv` 的絕對路徑一致。

直接在 VS Code 開啟 worktree 時，透過「Python: Select Interpreter」選取 main 的共用直譯器。啟動 Windows GUI 時不要使用 offscreen。

詳細命令契約請見[開發工作說明](https://github.com/NEXTAltair/LoRAIro/blob/main/scripts/DEV_TASKS.md)。
