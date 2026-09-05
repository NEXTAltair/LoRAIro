# Copy only Node's runtime and global npm tools. Keeping Node in this stage makes
# its ownership, version, and use by Codex independent of Dev Container features.
FROM node:24-bookworm AS node-runtime

# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# Base image includes Yarn APT repo which may fail signature check (EXPKEYSIG).
# We do not use Yarn in this project, so disable it to keep apt stable.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn*.list || true

# Prevent an inherited npm prefix from changing the image-owned global location.
RUN rm -f /home/vscode/.npmrc /root/.npmrc || true

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Container tests are headless; interactive GUI execution belongs to Windows.
ENV QT_QPA_PLATFORM=offscreen
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
# Claude Code native install path
ENV PATH="/home/vscode/.local/bin:${PATH}"

# Configure sudo for vscode user (base image may have partial config)
RUN apt-get update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt-get -y install --no-install-recommends sudo && \
    mkdir -p /etc/sudoers.d && \
    echo "vscode ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/nopasswd && \
    chmod 0440 /etc/sudoers.d/nopasswd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Setup external APT repositories (GitHub CLI)
# Note: curl, gnupg, lsb-release are pre-installed in buildpack-deps base image
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# Install only headless-test and command-line dependencies in a single layer.
# The interactive Qt GUI runs on Windows; this image never needs X11, GTK,
# audio, font, or XCB platform packages.
# Note: build-essential, git, curl, wget, gnupg, procps, lsb-release are pre-installed in base image
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Qt/PySide6 offscreen platform and software-rendering runtime
    libegl1 \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon0 \
    libdbus-1-3 \
    # Database tools
    sqlite3 \
    # Git LFS and JSON tools
    git-lfs \
    jq \
    # GitHub CLI (from github repo)
    gh \
    # Utilities
    rsync \
    # Terminal multiplexer (required for Agent Teams)
    tmux \
    # Secret storage (for CLI tools credential management)
    libsecret-1-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official method from docs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Node is an image dependency, not a post-create dependency. Copying these
# narrow paths avoids overwriting Python's /usr/local tree with the Node image.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

# Keep rebuilds reproducible; update this reviewed version deliberately.
ARG CODEX_VERSION=0.153.4
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && node --version \
    && npm --version \
    && npm install --global --no-audit --no-fund "@openai/codex@${CODEX_VERSION}" \
    && codex --version

# Create workspaces directory and .venv with proper ownership
RUN mkdir -p /workspaces/LoRAIro/.venv && chown -R vscode:vscode /workspaces

# Set the default shell to bash
SHELL ["/bin/bash", "-c"]

# Switch to vscode user
USER vscode
WORKDIR /workspaces

# Create VS Code Server directories with proper permissions
RUN mkdir -p /home/vscode/.vscode-server/bin \
    && mkdir -p /home/vscode/.vscode-server/data \
    && mkdir -p /home/vscode/.vscode-server/extensions

# Claude Code: native installer; verify the executable during the image build.
RUN curl -fsSL https://claude.ai/install.sh | bash && claude --version

# Set bash history persistence
RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc

CMD ["sleep", "infinity"]
