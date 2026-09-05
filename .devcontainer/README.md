# Container / Windows responsibilities

- Edit code and run headless tests in the Dev Container. Qt uses `offscreen`;
  no host X server or `DISPLAY` forwarding is needed.
- Run the interactive LoRAIro GUI on Windows. Container environment settings
  must not be copied into the Windows shell.
- The named `lorairo-venv` volume masks the host `.venv` inside the container.
  Keep it: Windows and Linux virtual environments are not interchangeable.
- Container initialization must not delete `local_packages/**/.venv` from the
  bind-mounted host workspace. These may belong to Windows workflows.
- Ruff formatting, BDD, CI automation and existing UI code generation remain.
  Removing the Qt editing extension does not remove `.ui` files or their generator.
- Gemini CLI and autoDocstring are no longer installed by the container setup.

Rebuild the Dev Container to apply image environment changes. Existing globally
installed extensions or CLIs are not automatically uninstalled by this change.
No named volumes or Windows environments need to be deleted.

SSH/port 2222, GPU configuration, dependency upgrades and agent-kit integration
are outside this cleanup. `make setup` still restores external skills and can
fail on the separately tracked skill-lock mismatch; this change does not bypass it.

The ignored Codex project config currently needs separate Windows/container
environment handling. This cleanup does not change it: do not run `uv` from a
worktree until its actual shared environment is correctly configured.

Reference: [uv project environment configuration](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).
