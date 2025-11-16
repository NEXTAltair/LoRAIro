<!--
WARNING: Do not rename this file manually!
File name: lessons-00005.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

Legacy .venv_linux/.venv_windows handling was removed on 2025-10-20: all commands, Makefiles, and setup scripts now assume a single .venv managed by devcontainer volume mounts. Never reintroduce UV_PROJECT_ENVIRONMENT or OS-specific venv logic窶覗uv run already picks up .venv across Windows/Linux.