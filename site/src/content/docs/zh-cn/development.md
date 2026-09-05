---
type: Guide
title: 开发环境与无界面测试
description: 区分 Windows 运行、容器开发和共享 Python 环境。
sidebar:
  order: 10
---

## Windows 与容器的分工

在 Dev Container 中编辑代码，在 Windows 中运行图形界面。容器不显示 GUI，测试使用 Qt offscreen。Windows 与 Linux 不共享同一份 `.venv` 实体；各操作系统内的 main 和 worktree 共享该系统专用环境。

## 安装开发依赖

在 main 共享 checkout 中执行，需要 Python、Git 和 uv。

```powershell
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

Linux 中若没有 `python`，请使用 `python3`。此操作会更新共享环境，请在其他应用、测试和智能体未使用它时执行。Kit 的安装和配置单独管理。

## 常用开发命令

```powershell
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py test-all --dry-run
```

`test` 测试 LoRAIro 本体；`test-all` 按顺序以独立测试进程运行三个包。BDD 继续使用 pytest-bdd。`lint` 是只读检查；`format` 使用 Ruff 自动格式化并修复。常规任务不会自动同步依赖。

`test-runtime-local` 运行真实 GPU 模型，`test-runtime-webapi` 调用可能实际计费的 API。两者都需要显式执行，不包含在常规 `test-all` 中。

## worktree

不要在工作用 worktree 中创建专用 `.venv`。共享命令通过 Git 找到 main 环境，并使用目标 worktree 的源码。如果设置了 `UV_PROJECT_ENVIRONMENT`，它必须与该环境 main 共享 `.venv` 的绝对路径一致。

直接在 VS Code 中打开 worktree 时，通过“Python: Select Interpreter”选择 main 的共享解释器。启动 Windows GUI 时不要使用 offscreen。

详细命令约定见[开发任务说明](https://github.com/NEXTAltair/LoRAIro/blob/main/scripts/DEV_TASKS.md)。
