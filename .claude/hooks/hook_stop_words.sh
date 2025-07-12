#!/bin/bash

# LoRAIro Project - Stop Words Hook
# NGワードチェックスクリプト

RULES_FILE="$(dirname "$0")/rules/hook_stop_words_rules.json"
HOOK_DATA="${1:-/dev/stdin}"

# jqが利用可能かチェック
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Skipping stop words check."
    exit 0
fi

# ルールファイルが存在するかチェック
if [ ! -f "$RULES_FILE" ]; then
    echo "Warning: Stop words rules file not found: $RULES_FILE"
    exit 0
fi

# 入力データからtool_outputを取得
TOOL_OUTPUT=$(echo "$HOOK_DATA" | jq -r '.tool_output // empty' 2>/dev/null)

if [ -z "$TOOL_OUTPUT" ]; then
    exit 0
fi

# ルール別NGワードチェック
RULE_NAMES=$(jq -r 'keys[]' "$RULES_FILE")
FOUND_VIOLATIONS=""

while IFS= read -r rule_name; do
    KEYWORDS=$(jq -r ".\"$rule_name\".keywords[]" "$RULES_FILE")
    MESSAGE=$(jq -r ".\"$rule_name\".message" "$RULES_FILE")
    
    while IFS= read -r keyword; do
        if echo "$TOOL_OUTPUT" | grep -q "$keyword"; then
            FOUND_VIOLATIONS="$FOUND_VIOLATIONS\n🚫 [$rule_name] キーワード「$keyword」検出\n   → $MESSAGE\n"
            break
        fi
    done <<< "$KEYWORDS"
done <<< "$RULE_NAMES"

# NGワードが見つかった場合は警告
if [ -n "$FOUND_VIOLATIONS" ]; then
    echo "🚫 NGワード規則違反が検出されました:"
    echo -e "$FOUND_VIOLATIONS"
    echo "LoRAIroプロジェクトでは指示されたことのみを正確に実行してください。"
    exit 1
fi

exit 0