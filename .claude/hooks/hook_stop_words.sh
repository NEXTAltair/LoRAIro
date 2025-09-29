#!/bin/bash

# LoRAIro Project - Stop Words Hook
# NGワードチェックスクリプト(静音化・最小ログ)

# ログファイルは現状維持
LOG_DIR="/workspaces/LoRAIro/.claude/logs"
LOG_FILE="$LOG_DIR/hook_stop_words_debug.log"
mkdir -p "$LOG_DIR"

# セッションID(あれば採用)
SESSION_ID="${SESSION_ID:-${CLAUDE_SESSION_ID:-}}"

# 前段の冗長デバッグを削除し、最小限だけ記録
# - 開始時刻とセッションID
echo "Start $(date) session_id=${SESSION_ID:-none}" >> "$LOG_FILE"

# DEBUG: Hook入力データの調査
echo "=== DEBUG HOOK INPUT ===" >> "$LOG_FILE"
echo "STDIN available: $([[ -p /dev/stdin ]] && echo "YES" || echo "NO")" >> "$LOG_FILE"
echo "ARG1: ${1:-}" >> "$LOG_FILE"
echo "ARG count: $#" >> "$LOG_FILE"
echo "ENV CLAUDE_TOOL_RESPONSE: ${CLAUDE_TOOL_RESPONSE:-}" >> "$LOG_FILE"
echo "ENV CLAUDE_HOOK_DATA: ${CLAUDE_HOOK_DATA:-}" >> "$LOG_FILE"
echo "All ENV vars with CLAUDE:" >> "$LOG_FILE"
env | grep CLAUDE >> "$LOG_FILE" 2>/dev/null || echo "No CLAUDE env vars found" >> "$LOG_FILE"
echo "=========================" >> "$LOG_FILE"

# stdin からの入力をキャプチャ(引数フォールバック)
if [ -p /dev/stdin ]; then
    HOOK_DATA="$(cat)"
    echo "HOOK_DATA from stdin: ${HOOK_DATA}" >> "$LOG_FILE"
else
    HOOK_DATA="${1:-}"
    echo "HOOK_DATA from arg: ${HOOK_DATA}" >> "$LOG_FILE"
fi

RULES_FILE="$(dirname "$0")/rules/hook_stop_words_rules.json"

# jqが利用可能かチェック(致命のみ)
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Skipping stop words check."  # 既存仕様: STDOUTにも出す
    echo "error: jq not installed; skip" >> "$LOG_FILE"
    exit 0
fi

# ルールファイルが存在するかチェック(致命のみ)
if [ ! -f "$RULES_FILE" ]; then
    echo "Warning: Stop words rules file not found: $RULES_FILE"  # 既存仕様: STDOUTにも出す
    echo "error: rules file not found: $RULES_FILE" >> "$LOG_FILE"
    exit 0
fi

# 入力データからtool_response.stdoutを取得(公式payload)
TOOL_OUTPUT="$(echo "$HOOK_DATA" | jq -r '.tool_response.stdout // empty' 2>/dev/null)"
BYTES_COUNT="$(printf "%s" "$TOOL_OUTPUT" | wc -c | tr -d ' ')"

# サマリのみ(抽出バイト数)
echo "summary stdout_bytes=${BYTES_COUNT}" >> "$LOG_FILE"

# tool_output が無い場合は静かにスキップ(1行のみ)
if [ -z "$TOOL_OUTPUT" ]; then
    echo "skip: no tool_response.stdout" >> "$LOG_FILE"
    exit 0
fi

# ルール名取得(件数サマリのみ)
RULE_NAMES="$(jq -r 'keys[]' "$RULES_FILE" 2>/dev/null)"
RULE_COUNT="$(printf "%s\n" "$RULE_NAMES" | wc -l | tr -d ' ')"
echo "summary rules=${RULE_COUNT}" >> "$LOG_FILE"

FOUND_VIOLATIONS=""
FIRST_RULE=""
FIRST_KEYWORD=""

# ループ中の詳細(checking/not found など)は全て削除し、違反があった最初の1件だけ記録
while IFS= read -r rule_name; do
    [ -z "$rule_name" ] && continue

    KEYWORDS="$(jq -r ".\"$rule_name\".keywords[]" "$RULES_FILE" 2>/dev/null)"
    MESSAGE="$(jq -r ".\"$rule_name\".message" "$RULES_FILE" 2>/dev/null)"

    while IFS= read -r keyword; do
        [ -z "$keyword" ] && continue

        if printf "%s" "$TOOL_OUTPUT" | grep -i -q -- "$keyword"; then
            FOUND_VIOLATIONS="$FOUND_VIOLATIONS\n🚫 [$rule_name] キーワード「$keyword」検出\n   → $MESSAGE\n"
            if [ -z "$FIRST_RULE" ]; then
              FIRST_RULE="$rule_name"
              FIRST_KEYWORD="$keyword"
            fi
            break
        fi
    done <<< "$KEYWORDS"

done <<< "$RULE_NAMES"

if [ -n "$FOUND_VIOLATIONS" ]; then
    # 1行サマリ(違反あり、最初の1件のみ)
    echo "violations=1 first_rule='$FIRST_RULE' first_keyword='$FIRST_KEYWORD'" >> "$LOG_FILE"

    # 新仕様に対応したJSONを返してブロック
    cat << EOF
{
    "hookSpecificOutput": {
        "permissionDecision": "deny",
        "permissionDecisionReason": "🚫 NGワード規則違反が検出されました:\n$FOUND_VIOLATIONS\nLoRAIroプロジェクトでは指示されたことのみを正確に実行してください。"
    }
}
EOF
    exit 2
else
    echo "violations=0" >> "$LOG_FILE"
fi

exit 0
