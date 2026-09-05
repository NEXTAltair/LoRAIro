---
type: Guide
title: 设置、备份与故障排查
description: 保护敏感信息与项目，排查恢复时的问题。
sidebar:
  order: 8
---

## 设置

通过 GUI 的「設定」（Ctrl+,）查看设置。`config/lorairo.toml` 包含保存位置和 API 密钥等信息。不要公开 API 密钥、完整配置文件，或显示私人图片路径的截图。

主要设置包括 API 密钥、项目及导出和 Batch 结果位置、额外提示词、模型连接路由、数据库等待时间和日志级别。恢复时请检查是否残留原电脑的绝对路径。

## 备份

1. 结束 GUI、CLI、Batch 导入等会写入数据库的进程。
2. 将实际保存位置中的整个项目复制到其他位置，通常位于 `lorairo_data/`。
3. 除了 `image_database.db`，还应保存 `image_dataset/`、用户标签数据库（`user_tags.sqlite`）等内容。
4. 将 `config/lorairo.toml` 和必要的 Batch 结果作为敏感信息单独保存。

避免只复制正在使用的 SQLite 数据库文件。恢复时不要覆盖原始备份；请使用恢复副本检查图片、标签和设置。

## 启动或依赖错误

Windows 与 Linux 的 `.venv` 不同。不要直接使用从其他操作系统复制的环境，应在目标系统安装依赖。重建共享环境前，先停止使用中的应用、测试和智能体。

GUI 不显示时，请检查 Windows 是否设置了 `QT_QPA_PLATFORM=offscreen`。容器测试使用 offscreen 则是正常情况。

## 无法识别 GPU

```powershell
nvidia-smi
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
```

计划使用 GPU 却显示 false 时，请检查驱动、GPU 兼容性和 PyTorch 环境。删除应用数据无法解决 GPU 配置问题。

## 数据库冲突与外部连接

出现 `CONFLICT` 时，请等其他写入操作结束后再重试。不要同时从 GUI 和 CLI 写入。首次获取标签数据库失败时，请检查网络，必要时确认 Hugging Face 身份验证配置。

WebAPI 错误请检查身份验证、用量限制、模型支持和发送限制，先调查原因再重复操作。

## 报告问题

请提供操作步骤、操作系统、复现条件，以及一小段相关日志。主要日志为 `logs/lorairo.log`、`logs/image-annotator-lib.log`、`logs/lorairo-cli.log`。请隐藏 API 密钥、个人信息和不希望公开的图片路径。
