---
type: Guide
title: 在 Windows 安装
description: 从源码创建 Windows 环境，启动图形界面和命令行。
sidebar:
  order: 2
---

## 所需条件

- Git、uv、Python 3.13。可以通过 uv 安装 Python。
- 足够存放模型和图片的可用空间。
- 如果使用标准 GPU 推理环境，需要兼容的 NVIDIA GPU 和驱动程序。

本流程从源码安装。标准 PyTorch 下载源使用 CUDA 13.2 版本，请根据实际环境确认驱动和 GPU 兼容性。改用 CPU 版本或其他 CUDA 版本需要修改依赖配置和 lockfile，而不只是更改启动选项。

## 首次设置

在 PowerShell 中执行。路径含空格时请加引号。

```powershell
git clone https://github.com/NEXTAltair/LoRAIro.git
cd LoRAIro
git submodule update --init --recursive
uv python install 3.13
uv sync --python 3.13
uv run --no-sync lorairo
```

安装依赖需要联网并花费一定时间。应用运行期间不要通过 `uv sync` 更新环境。

## 后续启动

从仓库目录执行。

```powershell
uv run --no-sync lorairo
uv run --no-sync lorairo-cli --help
```

`--no-sync` 防止启动时更新依赖。依赖配置变更后，请先停止应用和测试，再显式运行 `uv sync`。

## 从恢复副本继续使用

无需删除现有图片、数据库和设置来重新安装。请先阅读[备份与恢复](../troubleshooting/)。从其他操作系统复制的 `.venv` 不能直接使用；请将 Windows 与容器内 Linux 的 Python 环境分开。

如果 `UV_PROJECT_ENVIRONMENT` 仍指向旧容器的 `/workspaces/...`，请改为 Windows 实际使用的共享环境。不要只为绕过错误而创建旧路径。

## 同时进行开发

测试和格式化工具的安装方式以及 Dev Container 的用途见[开发环境](../development/)。
