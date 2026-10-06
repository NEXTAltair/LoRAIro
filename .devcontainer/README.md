# Container / Windows responsibilities

- Edit code and run headless tests in the Dev Container. Qt uses `offscreen`;
  no host X server or `DISPLAY` forwarding is needed.
- Run the interactive LoRAIro GUI on Windows. Container environment settings
  must not be copied into the Windows shell.
- The image intentionally contains only Qt's offscreen/OpenGL runtime. X11,
  XCB, GTK, audio, GUI fonts, and SQLite development headers are not part of
  the container contract.
- The named `lorairo-venv` volume masks the host `.venv` inside the container.
  Keep it: Windows and Linux virtual environments are not interchangeable.
- Container initialization must not delete `local_packages/**/.venv` from the
  bind-mounted host workspace. These may belong to Windows workflows.
- Ruff formatting, BDD, CI automation and existing UI code generation remain.
  Removing the Qt editing extension does not remove `.ui` files or their generator.
- Gemini CLI and autoDocstring are no longer installed by the container setup.

Before a rebuild, update the **host checkout**. A Dev Container bind-mounts that
checkout, so rebuilding an old checkout cannot supply newly added setup scripts:

```powershell
git pull --ff-only
```

The image itself installs Node 24 and the current stable Codex CLI. Codex is
installed as `vscode` under `/home/vscode/.local`, which is also the global npm
prefix. Update it from a container terminal without `sudo`:

```bash
npm install -g @openai/codex@latest
codex --version
```

Restart Codex after updating. Updates made inside a running container last until
that container is replaced. The default `CODEX_VERSION=latest` is resolved when
Docker executes the install layer; a cached layer can retain an older release.
Use **Dev Containers: Rebuild Container Without Cache** when rebuilding to get
the current release. Set `build.args.CODEX_VERSION` in `devcontainer.json` to an
exact release only when a pinned CLI is needed.

For an existing container built with the old root-owned installation, the same
user-owned prefix can be configured before rebuilding:

```bash
npm config set prefix /home/vscode/.local
export PATH="/home/vscode/.local/bin:$PATH"
npm install -g @openai/codex@latest
hash -r
codex --version
```

The rebuilt image supplies this prefix and PATH automatically.

Post-create only performs workspace setup: it changes
to `/workspaces/LoRAIro`, records all output in `.devcontainer/postCreate.log`,
runs `make setup` (including pinned harness restoration), and validates the
harness. It fails explicitly if `scripts/install_agent_harness.py` is absent
instead of silently configuring an old checkout. Existing globally
installed extensions or CLIs are not automatically uninstalled by this change.
No named volumes or Windows environments need to be deleted.

If post-create is interrupted, use a normal terminal inside the exact workspace:

```bash
cd /workspaces/LoRAIro
python -X utf8 scripts/install_agent_harness.py
python -X utf8 scripts/validate_harness.py
```

SSH/port 2222, GPU configuration, dependency upgrades and agent-kit integration
are outside this cleanup. `make setup` still restores external skills and can
fail on the separately tracked skill-lock mismatch; this change does not bypass it.

The ignored Codex project config currently needs separate Windows/container
environment handling. This cleanup does not change it: do not run `uv` from a
worktree until its actual shared environment is correctly configured.

Reference: [uv project environment configuration](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).
