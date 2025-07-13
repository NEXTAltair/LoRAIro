#!/bin/bash

# LoRAIro Project - Stop Words Hook
# NGワードチェックスクリプト

# =========================== デバッグコード開始 ===========================
# ログディレクトリを確実に作成
LOG_DIR="/workspaces/LoRAIro/.claude/logs"
LOG_FILE="$LOG_DIR/hook_stop_words_debug.log"
mkdir -p "$LOG_DIR"

echo "=== Stop Words Hook Debug $(date) ===" >> "$LOG_FILE"
echo "Hook executed with args: $@" >> "$LOG_FILE"
echo "HOOK_DATA variable: $HOOK_DATA" >> "$LOG_FILE"

# stdin からの入力をキャプチャ
if [ -p /dev/stdin ]; then
    STDIN_DATA=$(cat)
    echo "STDIN data: $STDIN_DATA" >> "$LOG_FILE"
    # 後続処理で使うためにHOOK_DATAに代入
    HOOK_DATA="$STDIN_DATA"
else
    HOOK_DATA="${1:-}"
fi

echo "Final HOOK_DATA: $HOOK_DATA" >> "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"
# =========================== デバッグコード終了 ===========================

RULES_FILE="$(dirname "$0")/rules/hook_stop_words_rules.json"

# jqが利用可能かチェック
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Skipping stop words check." >> "$LOG_FILE"
    echo "Warning: jq is not installed. Skipping stop words check."
    exit 0
fi

# ルールファイルが存在するかチェック
if [ ! -f "$RULES_FILE" ]; then
    echo "Warning: Stop words rules file not found: $RULES_FILE" >> "$LOG_FILE"
    echo "Warning: Stop words rules file not found: $RULES_FILE"
    exit 0
fi

# 入力データからtool_outputを取得
TOOL_OUTPUT=$(echo "$HOOK_DATA" | jq -r '.tool_output // empty' 2>/dev/null)
echo "Extracted tool_output: $TOOL_OUTPUT" >> "$LOG_FILE"

if [ -z "$TOOL_OUTPUT" ]; then
    echo "No tool_output found, skipping stop words check" >> "$LOG_FILE"
    exit 0
fi

# ルール別NGワードチェック
RULE_NAMES=$(jq -r 'keys[]' "$RULES_FILE" 2>/dev/null)
FOUND_VIOLATIONS=""

echo "Starting stop words check..." >> "$LOG_FILE"

while IFS= read -r rule_name; do
    if [ -n "$rule_name" ]; then
        echo "Checking rule: $rule_name" >> "$LOG_FILE"

        KEYWORDS=$(jq -r ".\"$rule_name\".keywords[]" "$RULES_FILE" 2>/dev/null)
        MESSAGE=$(jq -r ".\"$rule_name\".message" "$RULES_FILE" 2>/dev/null)

        while IFS= read -r keyword; do
            if [ -n "$keyword" ]; then
                echo "  Checking keyword: $keyword" >> "$LOG_FILE"

                # 大文字小文字を区別しない検索を使用
                if echo "$TOOL_OUTPUT" | grep -i -q "$keyword"; then
                    echo "  VIOLATION FOUND: $keyword in $rule_name" >> "$LOG_FILE"
                    FOUND_VIOLATIONS="$FOUND_VIOLATIONS\n🚫 [$rule_name] キーワード「$keyword」検出\n   → $MESSAGE\n"
                    break
                fi
            fi
        done <<< "$KEYWORDS"
    fi
done <<< "$RULE_NAMES"

# NGワードが見つかった場合は警告をJSON形式で返す
if [ -n "$FOUND_VIOLATIONS" ]; then
    echo "Stop words violations found, returning block decision" >> "$LOG_FILE"

    # Claude Codeに対してJSON形式でフィードバックを返す
    cat << EOF
{
    "decision": "block",
    "reason": "🚫 NGワード規則違反が検出されました:\n$FOUND_VIOLATIONS\nLoRAIroプロジェクトでは指示されたことのみを正確に実行してください。"
}
EOF
    exit 2  # ツールの後処理をブロックしてClaude Codeにフィードバック
else
    echo "No stop words violations found" >> "$LOG_FILE"
fi

exit 0
