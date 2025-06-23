#!/bin/bash
# LoRAIro GUI実行スクリプト
# devcontainer環境でのGUI表示用

# X11フォワーディングの設定
export DISPLAY=${DISPLAY:-:0}

# PySide6のプラットフォーム設定（GUI用）
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb}

# X11ソケットの権限設定（必要に応じて）
if [ -S /tmp/.X11-unix/X0 ]; then
    xhost +local: 2>/dev/null || true
fi

# LoRAIroを実行
echo "Starting LoRAIro GUI..."
echo "DISPLAY: $DISPLAY"
echo "QT_QPA_PLATFORM: $QT_QPA_PLATFORM"

python -m lorairo.main