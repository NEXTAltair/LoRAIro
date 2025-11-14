# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/devcontainers/python:dev-3.13-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV NPM_CONFIG_PREFIX=/home/vscode/.npm-global
ENV PATH=/home/vscode/.npm-global/bin:$PATH
# Agent execution environment
ENV CLAUDE_WORKSPACE=/workspaces/LoRAIro
ENV CLAUDE_CACHE_DIR=/home/vscode/.claude/cache
ENV CLAUDE_STATE_DIR=/home/vscode/.claude/state
ENV PYTHONPATH=/workspaces/LoRAIro/src:/workspaces/LoRAIro/local_packages/image-annotator-lib/src:/workspaces/LoRAIro/local_packages/genai-tag-db-tools/src

RUN apt-get update && \
    export DEBIAN_FRONTEND=noninteractive && \
    apt-get -y install --no-install-recommends sudo && \
    # 🔽 権限設定を追加 🔽
    # /etc/sudoers.d/ ディレクトリが存在しない場合は作成
    mkdir -p /etc/sudoers.d && \
    # vscode ユーザーがパスワードなしで sudo を実行できるように設定
    echo "vscode ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/nopasswd && \
    # 権限ファイルを安全に設定
    chmod 0440 /etc/sudoers.d/nopasswd

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    bash \
    zsh \
    ca-certificates \
    gnupg \
    procps \
    lsb-release \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install OpenGL libraries for headless GUI testing
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install SQLite3, Git LFS, and jq for Claude Code hooks
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    libsqlite3-dev \
    git-lfs \
    jq \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official method from docs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install xdg-utils for opening URLs in the default browser
RUN apt-get update && apt-get install -y --no-install-recommends \
    xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install rsync for efficient file syncing in Makefile
RUN apt-get update && apt-get install -y --no-install-recommends \
    rsync \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install agent dependencies: process monitoring, parallel execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    parallel \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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

# Configure npm to use user directory for global packages
RUN NPM_PREFIX=/home/vscode/.npm-global && \
    mkdir -p "$NPM_PREFIX" && \
    npm config set prefix "$NPM_PREFIX" && \
    chown -R vscode:vscode "$NPM_PREFIX" && \
    echo 'export PATH=/home/vscode/.npm-global/bin:$PATH' >> /home/vscode/.bashrc && \
    echo 'export PATH=/home/vscode/.npm-global/bin:$PATH' >> /home/vscode/.zshrc || true && \
    npm install -g @anthropic-ai/claude-code @google/gemini-cli byterover-cli

# Setup zsh with oh-my-zsh for better development experience
RUN if [ ! -d "/home/vscode/.oh-my-zsh" ]; then \
    sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended; \
    fi && echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc


# Set bash history persistence
RUN echo 'export HISTFILE=/home/vscode/.bash_history' >> ~/.bashrc \
    && echo 'export HISTSIZE=10000' >> ~/.bashrc \
    && echo 'export HISTFILESIZE=10000' >> ~/.bashrc

CMD ["sleep", "infinity"]
