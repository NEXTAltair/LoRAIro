#!/bin/bash

# LoRAIro Project - Git Grep Enforcement Hook
# grep/rg コマンドを git grep --function-context に強制変換

# ログディレクトリを確実に作成
LOG_DIR="/workspaces/LoRAIro/.claude/logs"
LOG_FILE="$LOG_DIR/hook_git_grep_debug.log"
mkdir -p "$LOG_DIR"

echo "=== Git Grep Hook Debug $(date) ===" >> "$LOG_FILE"
echo "Hook executed with args: $@" >> "$LOG_FILE"
echo "HOOK_DATA variable: $HOOK_DATA" >> "$LOG_FILE"

# stdin からの入力をキャプチャ
if [ -p /dev/stdin ]; then
    STDIN_DATA=$(cat)
    echo "STDIN data: $STDIN_DATA" >> "$LOG_FILE"
    HOOK_DATA="$STDIN_DATA"
else
    HOOK_DATA="${1:-}"
fi

echo "Final HOOK_DATA: $HOOK_DATA" >> "$LOG_FILE"

# コマンド抽出
COMMAND=$(echo "$HOOK_DATA" | jq -r '.command // empty' 2>/dev/null)
if [ -z "$COMMAND" ]; then
    COMMAND="$HOOK_DATA"
fi

echo "Extracted command: $COMMAND" >> "$LOG_FILE"

# grep系コマンド以外は処理をスキップ
if ! echo "$COMMAND" | grep -qE "^(grep|rg|git\s+grep)"; then
    echo "SKIPPING: Not a grep-related command" >> "$LOG_FILE"
    cat << EOF
{
    "decision": "allow"
}
EOF
    exit 0
fi

echo "PROCESSING: grep-related command detected" >> "$LOG_FILE"

# grep コマンドをブロック
if echo "$COMMAND" | grep -qE "^grep\s+"; then
    echo "BLOCKING: grep command detected" >> "$LOG_FILE"
    cat << EOF
{
    "decision": "block",
    "reason": "🚫 grep の代わりに git grep --function-context を使ってください。\n\nより良い検索結果のため、関数コンテキスト付きの git grep を使用してください。"
}
EOF
    exit 2
fi

# rg (ripgrep) コマンドをブロック
if echo "$COMMAND" | grep -qE "^rg\s+"; then
    echo "BLOCKING: rg command detected" >> "$LOG_FILE"
    cat << EOF
{
    "decision": "block", 
    "reason": "🚫 rg の代わりに git grep --function-context を使ってください。\n\nGit管理ファイルの一貫性のある検索のため、git grep を使用してください。"
}
EOF
    exit 2
fi

# git grep でフラグなしをブロック
if echo "$COMMAND" | grep -qE "^git\s+grep\s+" && ! echo "$COMMAND" | grep -qE "(--function-context|--show-function|-W|-p)"; then
    echo "BLOCKING: git grep without context flags" >> "$LOG_FILE"
    cat << EOF
{
    "decision": "block",
    "reason": "🚫 git grep では --function-context または --show-function フラグを使ってください。\n\n関数コンテキスト付きでより読みやすい検索結果を得るため、以下のように実行してください:\ngit grep --function-context <pattern> [path]"
}
EOF
    exit 2
fi

echo "ALLOWING: Command passed all checks" >> "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"

# すべてのチェックをパスした場合は許可
cat << EOF
{
    "decision": "allow"
}
EOF