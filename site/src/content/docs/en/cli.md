---
type: Guide
title: Using the CLI
description: Inspect commands and handle JSONL output in PowerShell.
sidebar:
  order: 9
---

## Inspect commands

Run from the repository directory using the environment already created.

```powershell
uv run --no-sync lorairo-cli --help
uv run --no-sync lorairo-cli images --help
uv run --no-sync lorairo-cli export create --help
uv run --no-sync lorairo-cli --json list-commands
uv run --no-sync lorairo-cli --json describe "images update"
```

`list-commands` and `describe` let agents inspect available operations and arguments. If arguments from old instructions are not recognized, compare them with current `--help`.

## JSONL mode

Place `--json` before the command to emit one JSON object per stdout line. Logs and progress go to stderr. Check the final `result` or `error`. Exit codes are 0 for success, 2 for input or validation errors, and 1 for other errors.

The environment variable `LORAIRO_CLI_JSON=1` is also supported, but an explicit flag makes intent clearer for interactive use.

JSONL is not simply an image ID list. When extracting IDs from search output, inspect structures such as `kind` and exclude message rows.

## Task-based instructions

- [Create projects and register images](../projects/)
- [Search using a JSON file](../search/)
- [List models and run synchronous annotation](../annotation/)
- [Preview and apply tag edits](../editing/)
- [Export by image IDs](../export/)

The CLI uses the same project data as the GUI. Back up before bulk updates and avoid simultaneous writes from the GUI. Detailed developer contracts are in the [CLI reference](https://github.com/NEXTAltair/LoRAIro/blob/main/docs/cli.md).
