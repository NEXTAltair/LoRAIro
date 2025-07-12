#!/bin/bash

# LoRAIro Project - Pre-Command Hook
# コマンド実行前チェック・自動フォーマットスクリプト

RULES_FILE="$(dirname "$0")/rules/hook_pre_commands_rules.json"
HOOK_DATA="${1:-/dev/stdin}"

# jqが利用可能かチェック
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Skipping pre-command checks."
    exit 0
fi

# ルールファイルが存在するかチェック
if [ ! -f "$RULES_FILE" ]; then
    echo "Warning: Pre-command rules file not found: $RULES_FILE"
    exit 0
fi

# 入力データからコマンドを取得
COMMAND=$(echo "$HOOK_DATA" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [ -z "$COMMAND" ]; then
    exit 0
fi

echo "🔍 Command check: $COMMAND"

# 1. ドキュメント優先チェック
DOC_FIRST_RULES=$(jq -c '.documentation_first_commands[]?' "$RULES_FILE")
while IFS= read -r rule; do
    if [ -n "$rule" ]; then
        PATTERN=$(echo "$rule" | jq -r '.pattern')
        REASON=$(echo "$rule" | jq -r '.reason')
        SUGGESTION=$(echo "$rule" | jq -r '.suggestion')
        
        if echo "$COMMAND" | grep -qE "$PATTERN"; then
            echo "📚 ドキュメント優先推奨:"
            echo "理由: $REASON"
            echo "提案: $SUGGESTION"
            echo ""
        fi
    fi
done <<< "$DOC_FIRST_RULES"

# 1.5. ライブラリ調査提案チェック
LIB_INVESTIGATION_RULES=$(jq -c '.library_investigation_suggestions[]?' "$RULES_FILE")
while IFS= read -r rule; do
    if [ -n "$rule" ]; then
        PATTERN=$(echo "$rule" | jq -r '.pattern')
        REASON=$(echo "$rule" | jq -r '.reason')
        SUGGESTION=$(echo "$rule" | jq -r '.suggestion')
        
        if echo "$COMMAND" | grep -qE "$PATTERN"; then
            echo "🔬 ライブラリ調査推奨:"
            echo "理由: $REASON"
            echo "提案: $SUGGESTION"
            echo ""
        fi
    fi
done <<< "$LIB_INVESTIGATION_RULES"

# 2. ブロックコマンドチェック
BLOCKED_RULES=$(jq -c '.blocked_commands[]?' "$RULES_FILE")
while IFS= read -r rule; do
    if [ -n "$rule" ]; then
        PATTERN=$(echo "$rule" | jq -r '.pattern')
        REASON=$(echo "$rule" | jq -r '.reason')
        SUGGESTION=$(echo "$rule" | jq -r '.suggestion')
        
        if echo "$COMMAND" | grep -qE "$PATTERN"; then
            echo "🚫 コマンドがブロックされました:"
            echo "理由: $REASON"
            echo "代替案: $SUGGESTION"
            exit 1
        fi
    fi
done <<< "$BLOCKED_RULES"

# 3. 自動フォーマットチェック
FORMAT_RULES=$(jq -c '.auto_format_commands[]?' "$RULES_FILE")
while IFS= read -r rule; do
    if [ -n "$rule" ]; then
        PATTERN=$(echo "$rule" | jq -r '.pattern')
        PRE_HOOK=$(echo "$rule" | jq -r '.pre_hook')
        DESCRIPTION=$(echo "$rule" | jq -r '.description')
        
        if echo "$COMMAND" | grep -qE "$PATTERN"; then
            echo "🛠️ 自動フォーマット実行: $DESCRIPTION"
            
            # $FILESを実際のファイルリストで置換 (git addの場合)
            if echo "$COMMAND" | grep -q "^git add"; then
                FILES=$(echo "$COMMAND" | sed 's/git add //' | tr ' ' '\n' | grep '\.py$' | tr '\n' ' ')
                ACTUAL_HOOK=$(echo "$PRE_HOOK" | sed "s/\$FILES/$FILES/g")
            else
                ACTUAL_HOOK="$PRE_HOOK"
            fi
            
            echo "実行コマンド: $ACTUAL_HOOK"
            eval "$ACTUAL_HOOK"
            
            if [ $? -eq 0 ]; then
                echo "✅ 自動フォーマット完了"
            else
                echo "❌ 自動フォーマット失敗"
                exit 1
            fi
        fi
    fi
done <<< "$FORMAT_RULES"

exit 0