# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/devcontainers/python:dev-3.13-bookworm

# Base image includes Yarn APT repo which may fail signature check (EXPKEYSIG).
# We do not use Yarn in this project, so disable it to keep apt stable.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn*.list || true

# Prevent npm prefix config from breaking nvm-based Node feature
RUN rm -f /home/vscode/.npmrc /root/.npmrc || true

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
# Agent execution environment
ENV CLAUDE_WORKSPACE=/workspaces/LoRAIro
ENV CLAUDE_CACHE_DIR=/home/vscode/.claude/cache
ENV CLAUDE_STATE_DIR=/home/vscode/.claude/state
ENV PYTHONPATH=/workspaces/LoRAIro/src:/workspaces/LoRAIro/local_packages/image-annotator-lib/src:/workspaces/LoRAIro/local_packages/genai-tag-db-tools/src

# Configure sudo for vscode user (base image may have partial config)
RUN apt-get update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt-get -y install --no-install-recommends sudo && \
    mkdir -p /etc/sudoers.d && \
    echo "vscode ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/nopasswd && \
    chmod 0440 /etc/sudoers.d/nopasswd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Setup external APT repositories (Docker CLI, GitHub CLI)
# Note: curl, gnupg, lsb-release are pre-installed in buildpack-deps base image
RUN mkdir -p /etc/apt/keyrings /usr/share/keyrings && \
    # Docker CLI repository
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    # GitHub CLI repository
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# Install all system dependencies in a single layer
# Note: build-essential, git, curl, wget, gnupg, procps, lsb-release are pre-installed in base image
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Shell (zsh for oh-my-zsh)
    zsh \
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
    # Database tools
    sqlite3 \
    libsqlite3-dev \
    # Git LFS and JSON tools
    git-lfs \
    jq \
    # Docker CLI (from docker repo)
    docker-ce-cli \
    # GitHub CLI (from github repo)
    gh \
    # Utilities
    xdg-utils \
    rsync \
    # Secret storage (for CLI tools)
    libsecret-1-0 \
    libsecret-1-dev \
    # Agent dependencies
    parallel \
    netcat-openbsd \
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

# Create agent working directories
RUN mkdir -p /home/vscode/.claude/cache \
    && mkdir -p /home/vscode/.claude/state

# Setup zsh with oh-my-zsh for better development experience
RUN if [ ! -d "/home/vscode/.oh-my-zsh" ]; then \
    sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended; \
    fi && echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc

# Set bash history persistence
RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc

CMD ["sleep", "infinity"]
