---
type: Guide
title: 修改标签与检查描述文本
description: 区分数据库编辑和仅在导出时生效的调整。
sidebar:
  order: 6
---

## 先检查生成结果

选择图片，在详情面板检查标签、描述文本和评分。AI 结果不一定正确，请检查是否包含训练不需要的标签或与图片不符的表述。

当前描述文本显示为只读。不要假设存在可自由输入的描述文本编辑框。可通过标签菜单使用将标签移至描述文本的功能。

## 永久修改与导出调整

- 添加、替换或 reject 标签会影响数据库内容。
- 导出 overlay 中的「出力除外」（排除输出）只是导出时的临时调整。
- 「reject(DB)」不是临时排除。请检查影响范围，不要假设操作可以撤销。

模型可能不会返回 AI 标签各自的 confidence。因此，并非总能根据 confidence 自动清理噪声标签。

## 在命令行中先预览再应用

标签修改默认为 dry-run。请先不加 `--apply` 来确认目标。

```powershell
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor"
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor" --apply
uv run --no-sync lorairo-cli tags remove -p "my-project" --image-ids 42 --tags "bad_tag" --apply
uv run --no-sync lorairo-cli tags replace -p "my-project" --image-ids 42 --from "bad tag" --to "good_tag" --apply
```

移除以 soft-reject 方式处理，但这并不保证有通用的“撤销”操作。批量修改前请先备份。通过命令行修改后，请在图形界面重新搜索或重新加载，确认最新状态。
