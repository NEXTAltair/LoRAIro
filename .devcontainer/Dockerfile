# Use an official Python runtime as a parent image
FROM python:3.12

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=offscreen

# Install system dependencies and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    bash \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
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

# Install SQLite3 and Git LFS
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    libsqlite3-dev \
    git-lfs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official method from docs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install xdg-utils for opening URLs in the default browser
RUN apt-get update && apt-get install -y --no-install-recommends \
    xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash vscode

# Create workspaces directory and set ownership
RUN mkdir -p /workspaces && chown vscode:vscode /workspaces

# Set the default shell to bash
SHELL ["/bin/bash", "-c"]

# Switch to vscode user
USER vscode
WORKDIR /workspaces

# Configure npm to use user directory for global packages
RUN mkdir -p ~/.npm-global && \
    npm config set prefix '~/.npm-global' && \
    echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc && \
    npm install -g @anthropic-ai/claude-code && \
    npm install -g @google/gemini-cli

CMD ["sleep", "infinity"]

