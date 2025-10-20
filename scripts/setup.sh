#!/bin/bash
# LoRAIro development environment setup script

echo "Setting up LoRAIro development environment..."

# Use default .venv directory (managed by devcontainer volume mount)
echo "Using default .venv directory"

# Sync dependencies
echo "Syncing dependencies with uv..."
uv sync --dev

if [ $? -eq 0 ]; then
    echo "✅ Environment setup complete!"
    echo ""
    echo "Virtual environment: .venv"
    echo "To run the application: uv run lorairo"
    echo "To run tests: uv run pytest"
else
    echo "❌ Setup failed!"
    exit 1
fi