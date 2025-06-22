#!/bin/bash
# Start Xvfb (X Virtual Framebuffer) for headless GUI testing

# Kill any existing Xvfb processes
pkill Xvfb || true

# Start Xvfb on display :99
Xvfb :99 -screen 0 1024x768x24 &

# Wait a moment for Xvfb to start
sleep 2

# Verify Xvfb is running
if pgrep Xvfb > /dev/null; then
    echo "Xvfb started successfully on display :99"
    export DISPLAY=:99
else
    echo "Failed to start Xvfb"
    exit 1
fi