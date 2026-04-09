# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# Base image includes Yarn APT repo which may fail signature check (EXPKEYSIG).
# We do not use Yarn in this project, so disable it to keep apt stable.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn*.list || true

# Prevent npm prefix config from breaking nvm-based Node feature
RUN rm -f /home/vscode/.npmrc /root/.npmrc || true

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=host.docker.internal:0
ENV QT_QPA_PLATFORM=xcb
ENV QT_X11_NO_MITSHM=1
ENV LIBGL_ALWAYS_INDIRECT=1
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

# Install all system dependencies in a single layer
# Note: build-essential, git, curl, wget, gnupg, procps, lsb-release are pre-installed in base image
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenGL libraries for headless GUI testing (Qt/PySide6)
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libegl1-mesa \
    libegl1-mesa-dev \
    libglib2.0-0 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxss1 \
    libgconf-2-4 \
    libnss3 \
    libxcursor1 \
    libxkbcommon0 \
    libgtk-3-0 \
    # XCB libraries for Qt6/X11 GUI (Issue #14)
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    # Japanese fonts for GUI (Issue #14)
    fonts-noto-cjk \
    # Database tools
    sqlite3 \
    libsqlite3-dev \
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

# Claude Code: native install with auto-update
RUN curl -fsSL https://claude.ai/install.sh | bash

# Set bash history persistence
RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc

CMD ["sleep", "infinity"]
