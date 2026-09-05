---
type: Guide
title: Install on Windows
description: Create a Windows environment from source and start the GUI and CLI.
sidebar:
  order: 2
---

## Requirements

- Git, uv and Python 3.13. Python can be installed with uv.
- Free space for models and images.
- A compatible NVIDIA GPU and driver if you use the standard GPU inference environment.

These instructions install from source. The standard PyTorch source provides CUDA 13.2 builds. Check driver and GPU compatibility for your environment. Switching to a CPU build or another CUDA version requires dependency configuration and lockfile changes, not just a launch option.

## First-time setup

Run these commands in PowerShell. Quote paths that contain spaces.

```powershell
git clone https://github.com/NEXTAltair/LoRAIro.git
cd LoRAIro
git submodule update --init --recursive
uv python install 3.13
uv sync --python 3.13
uv run --no-sync lorairo
```

Installing dependencies requires network access and time. Do not update the environment with `uv sync` while the app is running.

## Subsequent launches

Run from the repository directory.

```powershell
uv run --no-sync lorairo
uv run --no-sync lorairo-cli --help
```

`--no-sync` prevents dependency updates at launch. After dependency changes, stop the app and tests before explicitly running `uv sync`.

## Resuming from a restored copy

You do not need to delete existing images, databases or settings to reinstall. First read [backup and recovery](../troubleshooting/). A `.venv` copied from another OS cannot be used unchanged. Keep Windows and container Linux Python environments separate.

If `UV_PROJECT_ENVIRONMENT` still points to an old container path such as `/workspaces/...`, correct it to the actual shared Windows environment. Do not create the old path just to suppress an error.

## Developing as well

See [development environment](../development/) for test and formatting tools and the role of Dev Containers.
